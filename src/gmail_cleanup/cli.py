"""Command-line interface for Gmail Cleanup."""

import argparse
import sys
from .config import load_config, validate_config
from .auth import get_credentials, AuthError
from .client import GmailClient, APIError
from .actions import (
    delete_non_starred,
    delete_non_important,
    delete_non_starred_and_non_important,
    delete_all,
    delete_by_time,
    extract_senders,
    delete_by_sender,
)
from . import setup_logging


def setup_report_subcommand(subparsers):
    """Add the 'report' subcommand parser."""
    parser = subparsers.add_parser('report', help='Report sender domains with email counts')
    parser.set_defaults(func=handle_report)


def setup_clean_subcommand(subparsers):
    """Add the 'clean' subcommand parser."""
    parser = subparsers.add_parser('clean', help='Clean up Gmail inbox')
    
    # Mode argument
    parser.add_argument(
        '--mode',
        choices=[
            'non_starred', 'non_important', 'non_starred_and_non_important',
            'all', 'by_time', 'by_sender'
        ],
        required=True,
        help='Cleanup mode'
    )
    
    # Time threshold (for by_time mode)
    parser.add_argument('--time', dest='time_threshold', help='Time threshold (e.g. 7d, 1y)')
    
    # Sender list (for by_sender mode)
    parser.add_argument(
        '--senders',
        help='Comma-separated list of senders/domains'
    )
    
    # Dry-run control
    dry_run_group = parser.add_mutually_exclusive_group()
    dry_run_group.add_argument(
        '--dry-run',
        action='store_true',
        dest='dry_run',
        help='Report only, no deletion'
    )
    dry_run_group.add_argument(
        '--no-dry-run',
        action='store_false',
        dest='dry_run',
        help='Actually perform deletion'
    )
    parser.set_defaults(dry_run=True)
    
    parser.set_defaults(func=handle_clean)


def build_cli_parser():
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description='Clean up your Gmail inbox'
    )
    
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to config file (default: config.yaml)'
    )
    
    parser.add_argument(
        '--credentials',
        dest='credentials_path',
        help='Path to credentials.json'
    )
    
    parser.add_argument(
        '--token',
        dest='token_path',
        help='Path to token.json'
    )
    
    subparsers = parser.add_subparsers(dest='subcommand', required=True)
    setup_report_subcommand(subparsers)
    setup_clean_subcommand(subparsers)
    
    return parser


def handle_report(args):
    """Handle the report subcommand."""
    config = load_config(args.config, {
        'credentials_path': args.credentials_path,
        'token_path': args.token_path,
    })
    validate_config(config)
    
    try:
        creds = get_credentials(config['credentials_path'], config['token_path'])
        client = GmailClient(creds)
        
        print("Extracting sender domains...")
        senders = extract_senders(client)
        
        print(f"\n{'Domain':<40} {'Count':<10}")
        print('-' * 50)
        for domain, count in senders:
            print(f"{domain:<40} {count:<10}")
        print(f"\nTotal unique domains: {len(senders)}")
        
    except AuthError as e:
        print(f"Authentication error: {e}", file=sys.stderr)
        sys.exit(1)
    except APIError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_clean(args):
    """Handle the clean subcommand."""
    # Parse sender list if provided
    sender_list = args.senders.split(',') if args.senders else []
    
    config = load_config(args.config, {
        'mode': args.mode,
        'dry_run': args.dry_run,
        'time_threshold': args.time_threshold,
        'sender_list': sender_list,
        'credentials_path': args.credentials_path,
        'token_path': args.token_path,
    })
    validate_config(config)
    
    try:
        creds = get_credentials(config['credentials_path'], config['token_path'])
        client = GmailClient(creds)
        
        mode_actions = {
            'non_starred': lambda: delete_non_starred(client, config['dry_run']),
            'non_important': lambda: delete_non_important(client, config['dry_run']),
            'non_starred_and_non_important': lambda: delete_non_starred_and_non_important(client, config['dry_run']),
            'all': lambda: delete_all(client, config['dry_run']),
            'by_time': lambda: delete_by_time(client, config['time_threshold'], config['dry_run']),
            'by_sender': lambda: delete_by_sender(client, config['sender_list'], config['dry_run']),
        }
        
        action = mode_actions.get(config['mode'])
        if not action:
            print(f"Unknown mode: {config['mode']}", file=sys.stderr)
            sys.exit(1)
        
        count = action()
        
        if config['dry_run']:
            print(f"[DRY RUN] {count} threads would be trashed")
        else:
            print(f"Trashed {count} threads")
        
    except AuthError as e:
        print(f"Authentication error: {e}", file=sys.stderr)
        sys.exit(1)
    except APIError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entrypoint."""
    setup_logging()
    parser = build_cli_parser()
    args = parser.parse_args()
    
    # Set default dry_run to True, but respect CLI flag
    if not hasattr(args, 'dry_run'):
        args.dry_run = True
    
    args.func(args)


if __name__ == '__main__':
    main()