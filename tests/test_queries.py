"""Tests for queries.py."""

import pytest
from gmail_cleanup.queries import build_query


class TestBuildQuery:
    def test_non_starred_query(self):
        query = build_query('non_starred')
        assert query == '-is:starred -in:sent -in:drafts -in:trash -in:spam'
    
    def test_non_important_query(self):
        query = build_query('non_important')
        assert query == '-is:important -in:sent -in:drafts -in:trash -in:spam'
    
    def test_non_starred_and_non_important_query(self):
        query = build_query('non_starred_and_non_important')
        assert query == '-is:starred -is:important -in:sent -in:drafts -in:trash -in:spam'
    
    def test_all_query(self):
        query = build_query('all')
        assert query == '-in:sent -in:drafts -in:trash'
    
    def test_report_query(self):
        query = build_query('report')
        assert query == '-in:trash -in:spam'
    
    def test_by_time_query(self):
        query = build_query('by_time', time_threshold='30d')
        assert query == 'older_than:30d -in:trash -in:drafts'
    
    def test_by_time_query_year(self):
        query = build_query('by_time', time_threshold='1y')
        assert query == 'older_than:1y -in:trash -in:drafts'
    
    def test_by_time_query_month(self):
        query = build_query('by_time', time_threshold='6m')
        assert query == 'older_than:6m -in:trash -in:drafts'
    
    def test_by_sender_query(self):
        query = build_query('by_sender', sender='example.com')
        assert query == 'from:example.com -in:trash'
    
    def test_by_sender_query_email(self):
        query = build_query('by_sender', sender='noreply@example.com')
        assert query == 'from:noreply@example.com -in:trash'
    
    def test_unknown_mode(self):
        with pytest.raises(ValueError, match='Unknown mode'):
            build_query('invalid_mode')
    
    def test_by_time_missing_threshold(self):
        with pytest.raises(ValueError, match='time_threshold is required'):
            build_query('by_time')
    
    def test_by_time_invalid_threshold(self):
        with pytest.raises(ValueError, match='Invalid time threshold'):
            build_query('by_time', time_threshold='invalid')
    
    def test_by_time_invalid_threshold_format(self):
        with pytest.raises(ValueError, match='Invalid time threshold'):
            build_query('by_time', time_threshold='30dd')
    
    def test_by_sender_missing_sender(self):
        with pytest.raises(ValueError, match='sender is required'):
            build_query('by_sender')