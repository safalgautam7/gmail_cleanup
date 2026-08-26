"""Business logic for Gmail cleanup operations."""

import json
import logging
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple
from itertools import islice
from .client import GmailClient
from .queries import build_query

logger = logging.getLogger(__name__)


def _load_state(state_path: str) -> Optional[Dict[str, Any]]:
    """Load report state from disk."""
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load state from {state_path}: {e}")
        return None


def _save_state(state_path: str, state: Dict[str, Any]) -> None:
    """Atomically save report state to disk."""
    dir_name = os.path.dirname(state_path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f)
        os.replace(tmp_path, state_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def batched(iterable, n):
    """Batch data into tuples of length n. The last batch may be shorter."""
    iterator = iter(iterable)
    while batch := list(islice(iterator, n)):
        yield batch


def _execute_deletion(client: GmailClient, query: str, dry_run: bool) -> int:
    """
    Execute deletion based on query.
    
    Args:
        client: GmailClient instance
        query: Gmail search query
        dry_run: If True, only report matches without deleting
        
    Returns:
        Number of threads that matched the query
    """
    # Optimized for large email volumes with streaming and batching
    thread_count = 0
    message_count = 0
    
    for thread_ids_batch in batched(client.search_thread_ids(query), 1000):
        thread_count += len(thread_ids_batch)
        
        if dry_run:
            logger.info(f"[DRY RUN] {len(thread_ids_batch)} threads match: {query}")
            continue
            
        message_ids = client.list_message_ids_for_threads(thread_ids_batch)
        message_count += len(message_ids)
        
        for message_chunk in batched(message_ids, 1000):
            client.batch_trash_messages(list(message_chunk))
    
    if not dry_run:
        logger.info(f"Trashed {thread_count} threads ({message_count} messages): {query}")
    
    return thread_count


def delete_non_starred(client: GmailClient, dry_run: bool) -> int:
    """Delete all emails except starred ones."""
    query = build_query('non_starred')
    return _execute_deletion(client, query, dry_run)


def delete_non_important(client: GmailClient, dry_run: bool) -> int:
    """Delete all emails except important ones."""
    query = build_query('non_important')
    return _execute_deletion(client, query, dry_run)


def delete_non_starred_and_non_important(client: GmailClient, dry_run: bool) -> int:
    """Delete all emails except starred or important ones."""
    query = build_query('non_starred_and_non_important')
    return _execute_deletion(client, query, dry_run)


def delete_all(client: GmailClient, dry_run: bool) -> int:
    """Delete all emails."""
    query = build_query('all')
    return _execute_deletion(client, query, dry_run)


def delete_by_time(client: GmailClient, threshold: str, dry_run: bool) -> int:
    """Delete emails older than threshold."""
    query = build_query('by_time', time_threshold=threshold)
    return _execute_deletion(client, query, dry_run)


def _extract_domain(from_header: str) -> str:
    """Extract domain from an email From header."""
    if '@' not in from_header:
        return from_header
    domain = from_header.split('@')[-1].split('>')[0].strip()
    return domain


def extract_senders(
    client: GmailClient,
    fresh: bool = False,
    state_path: str = '.report_state.json',
    stop_after_batches: int = 0,
) -> List[Tuple[str, int]]:
    """
    Extract unique senders/domains with counts.
    
    Args:
        client: GmailClient instance
        fresh: If True, start fresh ignoring any existing state file
        state_path: Path to checkpoint state file
        stop_after_batches: If >0, stop after this many batches (for testing)
        
    Returns:
        List of (domain, count) tuples sorted by count descending
    """
    query = build_query('report')
    sender_counts: Dict[str, int] = {}
    total_processed = 0
    processed_ids: Set[str] = set()
    batch_count = 0

    if not fresh:
        state = _load_state(state_path)
        if state:
            sender_counts = state.get('sender_counts', {})
            total_processed = state.get('total_processed', 0)
            processed_ids = set(state.get('processed_thread_ids', []))
            print(f"Resumed from {total_processed} threads ({len(processed_ids)} already processed)", file=sys.stderr)
        else:
            print("Starting fresh.", file=sys.stderr)
    else:
        print("Starting fresh (--fresh).", file=sys.stderr)

    interrupted = False
    for thread_ids_batch in batched(client.search_thread_ids(query), 50):
        new_ids = [tid for tid in thread_ids_batch if tid not in processed_ids]
        batch_count += 1

        if not new_ids:
            total_processed += len(thread_ids_batch)
            processed_ids.update(thread_ids_batch)
            continue

        senders = client.get_thread_senders(new_ids)

        for from_header in senders:
            domain = _extract_domain(from_header)
            sender_counts[domain] = sender_counts.get(domain, 0) + 1

        processed_ids.update(new_ids)
        total_processed += len(thread_ids_batch)

        _save_state(state_path, {
            'version': 1,
            'query': query,
            'sender_counts': sender_counts,
            'total_processed': total_processed,
            'processed_thread_ids': list(processed_ids),
        })

        print(f"Processed {total_processed} threads ({len(new_ids)} new in this batch)...", file=sys.stderr)

        if stop_after_batches > 0 and batch_count >= stop_after_batches:
            print(f"Stopped after {batch_count} batches for testing. Resume with --resume.", file=sys.stderr)
            interrupted = True
            break

    if not interrupted:
        print(f"Done! Processed {total_processed} threads.", file=sys.stderr)

    return sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)


def delete_by_sender(client: GmailClient, senders: List[str], dry_run: bool) -> int:
    """Delete emails from specified senders."""
    total_deleted = 0
    
    for sender in senders:
        query = build_query('by_sender', sender=sender)
        total_deleted += _execute_deletion(client, query, dry_run)
    
    return total_deleted