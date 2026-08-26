"""Business logic for Gmail cleanup operations."""

import logging
from typing import List, Tuple
from itertools import islice
from .client import GmailClient
from .queries import build_query

logger = logging.getLogger(__name__)


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


def extract_senders(client: GmailClient) -> List[Tuple[str, int]]:
    """
    Extract unique senders/domains with counts.
    
    Returns:
        List of (domain, count) tuples sorted by count descending
    """
    query = build_query('report')
    sender_counts = {}
    total_processed = 0
    
    for thread_ids_batch in batched(client.search_thread_ids(query), 50):
        batch_size = len(thread_ids_batch)
        
        # Extract From headers directly from thread metadata in batch requests
        senders = client.get_thread_senders(list(thread_ids_batch))
        
        for from_header in senders:
            domain = _extract_domain(from_header)
            sender_counts[domain] = sender_counts.get(domain, 0) + 1
        
        total_processed += batch_size
        logger.info(f"Processed {total_processed} threads so far...")
    
    return sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)


def delete_by_sender(client: GmailClient, senders: List[str], dry_run: bool) -> int:
    """Delete emails from specified senders."""
    total_deleted = 0
    
    for sender in senders:
        query = build_query('by_sender', sender=sender)
        total_deleted += _execute_deletion(client, query, dry_run)
    
    return total_deleted