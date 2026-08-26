"""Tests for actions.py."""

import json
import pytest
from unittest.mock import MagicMock
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
    _load_state,
    _save_state,
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
        
        delete_non_starred(mock_client, dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert '-is:starred' in query_arg
    
    def test_delete_non_important(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        delete_non_important(mock_client, dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert '-is:important' in query_arg
    
    def test_delete_non_starred_and_non_important(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        delete_non_starred_and_non_important(mock_client, dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert '-is:starred' in query_arg
        assert '-is:important' in query_arg
    
    def test_delete_all(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        delete_all(mock_client, dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert '-in:sent' in query_arg
    
    def test_delete_by_time(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        delete_by_time(mock_client, '30d', dry_run=True)
        
        mock_client.search_thread_ids.assert_called_once()
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert 'older_than:30d' in query_arg
    
    def test_delete_by_sender(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        delete_by_sender(mock_client, ['example.com'], dry_run=True)
        
        assert mock_client.search_thread_ids.call_count == 1
        query_arg = mock_client.search_thread_ids.call_args[0][0]
        assert 'from:example.com' in query_arg
    
    def test_delete_by_multiple_senders(self, mock_client):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        
        delete_by_sender(mock_client, ['a.com', 'b.com'], dry_run=True)
        
        assert mock_client.search_thread_ids.call_count == 2


class TestExtractSenders:
    def test_extract_senders(self, mock_client, tmp_path):
        fixture = load_fixture('threads_list')
        mock_client.search_thread_ids.return_value = iter(
            [t['id'] for t in fixture['threads']]
        )
        mock_client.get_thread_senders.return_value = ['user@example.com', 'user@example.com', 'other@example.com']
        
        result = extract_senders(mock_client, state_path=str(tmp_path / 'state.json'))
        
        assert result[0] == ('example.com', 3)
    
    def test_extract_senders_domain_extraction(self, mock_client, tmp_path):
        mock_client.search_thread_ids.return_value = iter(['thread_1'])
        mock_client.get_thread_senders.return_value = ['User Name <user@domain.com>']
        
        result = extract_senders(mock_client, state_path=str(tmp_path / 'state.json'))
        
        assert len(result) == 1
        assert result[0][0] == 'domain.com'
        assert result[0][1] == 1
    
    def test_extract_senders_empty(self, mock_client, tmp_path):
        mock_client.search_thread_ids.return_value = iter([])
        
        result = extract_senders(mock_client, state_path=str(tmp_path / 'state.json'))
        
        assert result == []


class TestLoadState:
    def test_load_state_returns_none_when_no_file(self, tmp_path):
        result = _load_state(str(tmp_path / 'nonexistent.json'))
        assert result is None

    def test_load_state_returns_dict_from_valid_file(self, tmp_path):
        state_path = tmp_path / 'state.json'
        state_data = {
            'version': 1,
            'sender_counts': {'gmail.com': 100},
            'total_processed': 500,
            'processed_thread_ids': ['t1', 't2'],
        }
        state_path.write_text(json.dumps(state_data))

        result = _load_state(str(state_path))

        assert result == state_data

    def test_load_state_returns_none_on_corrupted_file(self, tmp_path):
        state_path = tmp_path / 'state.json'
        state_path.write_text('not valid json {{{')

        result = _load_state(str(state_path))

        assert result is None


class TestSaveState:
    def test_save_state_creates_file(self, tmp_path):
        state_path = str(tmp_path / 'state.json')
        state_data = {'version': 1, 'sender_counts': {'a.com': 5}}

        _save_state(state_path, state_data)

        with open(state_path) as f:
            assert json.load(f) == state_data

    def test_save_state_overwrites_existing(self, tmp_path):
        state_path = str(tmp_path / 'state.json')
        _save_state(state_path, {'version': 1, 'count': 1})
        _save_state(state_path, {'version': 1, 'count': 2})

        with open(state_path) as f:
            assert json.load(f)['count'] == 2

    def test_save_state_no_tmp_file_left_on_success(self, tmp_path):
        state_path = str(tmp_path / 'state.json')
        _save_state(state_path, {'data': 1})

        tmp_files = list(tmp_path.glob('*.tmp'))
        assert tmp_files == []


class TestExtractSendersResume:
    def test_fresh_run_creates_state_file(self, mock_client, tmp_path):
        mock_client.search_thread_ids.return_value = iter(['t1', 't2', 't3'])
        mock_client.get_thread_senders.return_value = ['a@test.com', 'b@test.com', 'c@test.com']
        state_path = str(tmp_path / 'state.json')

        extract_senders(mock_client, state_path=state_path)

        assert Path(state_path).exists()
        with open(state_path) as f:
            state = json.load(f)
        assert state['total_processed'] == 3
        assert set(state['processed_thread_ids']) == {'t1', 't2', 't3'}
        assert state['sender_counts'] == {'test.com': 3}

    def test_resume_loads_existing_state(self, mock_client, tmp_path):
        existing_state = {
            'version': 1,
            'query': '-in:trash -in:spam',
            'sender_counts': {'old.com': 10},
            'total_processed': 50,
            'processed_thread_ids': [f'old_{i}' for i in range(50)],
        }
        state_path = tmp_path / 'state.json'
        state_path.write_text(json.dumps(existing_state))

        new_ids = [f'old_{i}' for i in range(50)] + ['new_1', 'new_2']
        mock_client.search_thread_ids.return_value = iter(new_ids)
        mock_client.get_thread_senders.return_value = ['new@test.com']

        result = extract_senders(mock_client, state_path=str(state_path))

        mock_client.get_thread_senders.assert_called_once()
        called_ids = mock_client.get_thread_senders.call_args[0][0]
        assert called_ids == ['new_1', 'new_2']

        result_dict = dict(result)
        assert result_dict['old.com'] == 10
        assert result_dict['test.com'] == 1

    def test_auto_resume_without_state_file_starts_fresh(self, mock_client, tmp_path):
        mock_client.search_thread_ids.return_value = iter(['t1'])
        mock_client.get_thread_senders.return_value = ['a@test.com']
        state_path = str(tmp_path / 'nonexistent.json')

        result = extract_senders(mock_client, state_path=state_path)

        assert dict(result) == {'test.com': 1}

    def test_fresh_flag_ignores_existing_state(self, mock_client, tmp_path):
        existing_state = {
            'version': 1,
            'query': '-in:trash -in:spam',
            'sender_counts': {'old.com': 10},
            'total_processed': 50,
            'processed_thread_ids': [f'old_{i}' for i in range(50)],
        }
        state_path = tmp_path / 'state.json'
        state_path.write_text(json.dumps(existing_state))

        mock_client.search_thread_ids.return_value = iter(['t1'])
        mock_client.get_thread_senders.return_value = ['a@test.com']

        result = extract_senders(mock_client, fresh=True, state_path=str(state_path))

        result_dict = dict(result)
        assert 'old.com' not in result_dict
        assert result_dict['test.com'] == 1

    def test_stop_after_batches_exits_early(self, mock_client, tmp_path):
        all_ids = [f't{i}' for i in range(200)]
        mock_client.search_thread_ids.return_value = iter(all_ids)
        mock_client.get_thread_senders.return_value = ['a@test.com'] * 50
        state_path = str(tmp_path / 'state.json')

        result = extract_senders(
            mock_client,
            state_path=state_path,
            stop_after_batches=2,
        )

        result_dict = dict(result)
        assert result_dict['test.com'] == 100

        with open(state_path) as f:
            state = json.load(f)
        assert state['total_processed'] == 100
        assert len(state['processed_thread_ids']) == 100

    def test_resume_skips_already_processed_threads(self, mock_client, tmp_path):
        existing_state = {
            'version': 1,
            'query': '-in:trash -in:spam',
            'sender_counts': {'processed.com': 5},
            'total_processed': 10,
            'processed_thread_ids': ['p1', 'p2', 'p3', 'p4', 'p5',
                                     'p6', 'p7', 'p8', 'p9', 'p10'],
        }
        state_path = tmp_path / 'state.json'
        state_path.write_text(json.dumps(existing_state))

        all_ids = ['p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9', 'p10',
                   'n1', 'n2', 'n3', 'n4', 'n5']
        mock_client.search_thread_ids.return_value = iter(all_ids)
        mock_client.get_thread_senders.return_value = ['new@test.com'] * 5

        result = extract_senders(mock_client, state_path=str(state_path))

        mock_client.get_thread_senders.assert_called_once()
        called_ids = mock_client.get_thread_senders.call_args[0][0]
        assert called_ids == ['n1', 'n2', 'n3', 'n4', 'n5']

        result_dict = dict(result)
        assert result_dict['processed.com'] == 5
        assert result_dict['test.com'] == 5