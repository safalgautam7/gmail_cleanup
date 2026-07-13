"""Tests for actions.py."""

import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from gmail_cleanup.client import GmailClient
from gmail_cleanup.actions import (
    delete_non_starred,
    delete_non_important,
    delete_non_starred_and_non_important,
    delete_all,
    delete_by_time,
    extract_senders,
    delete_by_sender,
    _execute_deletion,
)


FIXTURES_PATH = Path(__file__).parent / 'fixtures' / 'mock_responses.json'


def load_fixture(name):
    """Load mock API response from fixtures."""
    with open(FIXTURES_PATH) as f:
        fixtures = json.load(f)
    return fixtures[name]


@pytest.fixture
def mock_client():
    """Create a mocked GmailClient."""
    client = MagicMock(spec=GmailClient)
    return client


class TestExecuteDeletion:
    def test_dry_run_does_not_trash(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        _execute_deletion(mock_client, '-is:starred -in:sent -in:drafts -in:trash -in:spam', dry_run=True)
        
        mock_client.batch_trash_messages.assert_not_called()
    
    def test_dry_run_returns_count(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1', 'thread_2'])
        
        result = _execute_deletion(mock_client, 'test_query', dry_run=True)
        
        assert result == 2
    
    def test_execution_trashes_messages(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1', 'thread_2'])
        mock_client.list_message_ids_for_threads.return_value = ['msg_1', 'msg_2']
        
        _execute_deletion(mock_client, 'test_query', dry_run=False)
        
        mock_client.batch_trash_messages.assert_called_once()
        assert mock_client.batch_trash_messages.call_args[0][0] == ['msg_1', 'msg_2']
    
    def test_no_threads_returns_zero(self, mock_client):
        mock_client.search_thread_ids.return_value = iter([])
        
        result = _execute_deletion(mock_client, 'test_query', dry_run=False)
        
        assert result == 0
        mock_client.batch_trash_messages.assert_not_called()


class TestDeleteModes:
    def test_delete_non_starred(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        result = delete_non_starred(mock_client, dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert '-is:starred' in query_arg
    
    def test_delete_non_important(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        result = delete_non_important(mock_client, dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert '-is:important' in query_arg
    
    def test_delete_non_starred_and_non_important(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        result = delete_non_starred_and_non_important(mock_client, dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert '-is:starred' in query_arg
        assert '-is:important' in query_arg
    
    def test_delete_all(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        result = delete_all(mock_client, dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert '-in:sent' in query_arg
    
    def test_delete_by_time(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        result = delete_by_time(mock_client, '30d', dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert 'older_than:30d' in query_arg
    
    def test_delete_by_sender(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        result = delete_by_sender(mock_client, ['example.com'], dry_run=True)
        
        assert mock_client.search_thread_ids.call_count == 1
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert 'from:example.com' in query_arg
    
    def test_delete_by_multiple_senders(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        result = delete_by_sender(mock_client, ['a.com', 'b.com'], dry_run=True)
        
        assert mock_client.search_thread_ids.call_count == 2


class TestExtractSenders:
    def test_extract_senders(self, mock_client):
        fixture = load_fixture('threads_list')
        mock_client.search_thread_ids.return_value = iter(
            [t['id'] for t in fixture['threads']]
        )
        mock_client.get_thread_senders.return_value = ['user@example.com', 'user@example.com', 'other@example.com']
        
        result = extract_senders(mock_client)
        
        assert result[0] == ('example.com', 3)
    
    def test_extract_senders_domain_extraction(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        mock_client.get_thread_senders.return_value = ['User Name <user@domain.com>']
        
        result = extract_senders(mock_client)
        
        assert len(result) == 1
        assert result[0][0] == 'domain.com'
        assert result[0][1] == 1
    
    def test_extract_senders_empty(self, mock_client):
        mock_client.search_thread_ids.return_value = iter([])
        
        result = extract_senders(mock_client)
        
        assert result == []