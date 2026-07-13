"""Gmail API client wrapper."""

import time
import random
from functools import wraps
from typing import Any, Dict, Iterator, List
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.credentials import Credentials


class APIError(Exception):
    """Raised when Gmail API calls fail."""
    pass


class QuotaExceededError(APIError):
    """Raised when API quota is exceeded."""
    pass


def retry_with_backoff(max_retries=5, initial_delay=1):
    """Decorator for retrying API calls with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except HttpError as e:
                    if e.resp.status == 429 or e.resp.status >= 500:
                        if attempt == max_retries - 1:
                            raise
                        delay = initial_delay * (2 ** attempt) + random.uniform(0, 1)
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator


class RateLimiter:
    """Rate limiter to prevent exceeding API quotas."""
    
    def __init__(self, calls_per_second=1):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0
    
    def wait_if_needed(self):
        """Wait if necessary to maintain rate limit."""
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


class GmailClient:
    """Thin wrapper over Gmail API calls."""
    
    def __init__(self, credentials: Credentials):
        """Initialize Gmail API service."""
        self.service = build('gmail', 'v1', credentials=credentials)
        self.read_limiter = RateLimiter(calls_per_second=50)
        self.write_limiter = RateLimiter(calls_per_second=1)
    
    @retry_with_backoff()
    def search_thread_ids(self, query: str) -> Iterator[str]:
        """
        Search for thread IDs matching query.
        
        Args:
            query: Gmail search query string
            
        Yields:
            Thread IDs matching the query
            
        Raises:
            QuotaExceededError: If API quota is exceeded
            APIError: For other API failures
        """
        try:
            page_token = None
            while True:
                response = self.service.users().threads().list(
                    userId='me',
                    q=query,
                    pageToken=page_token
                ).execute()
                
                for thread in response.get('threads', []):
                    yield thread['id']
                
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
        except HttpError as e:
            if e.resp.status == 403:
                raise QuotaExceededError("API quota exceeded. Please try again later.")
            raise APIError(f"API error: {str(e)}")
        except Exception as e:
            raise APIError(f"Network error: {str(e)}")
    
    @retry_with_backoff()
    def get_message_headers(self, message_id: str, headers=['From']) -> Dict[str, Any]:
        """
        Get message headers.
        
        Args:
            message_id: ID of the message
            headers: List of header names to retrieve
            
        Returns:
            Dictionary of header names and values
            
        Raises:
            APIError: If API call fails
        """
        try:
            response = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='metadata',
                metadataHeaders=headers
            ).execute()
            
            result = {}
            for header in response.get('payload', {}).get('headers', []):
                if header['name'] in headers:
                    result[header['name']] = header['value']
            
            return result
        except Exception as e:
            raise APIError(f"Failed to get message headers: {str(e)}")
    
    @retry_with_backoff()
    def batch_trash_messages(self, message_ids: List[str]) -> None:
        """
        Move messages to trash in batch.
        
        Args:
            message_ids: List of message IDs to trash
            
        Raises:
            APIError: If API call fails
        """
        self.write_limiter.wait_if_needed()
        
        try:
            self.service.users().messages().batchModify(
                userId='me',
                body={
                    'ids': message_ids,
                    'addLabelIds': ['TRASH']
                }
            ).execute()
        except Exception as e:
            raise APIError(f"Failed to trash messages: {str(e)}")
    
    @retry_with_backoff()
    def _get_thread_data(self, thread_id: str) -> Dict[str, Any]:
        """
        Get full thread data from Gmail API.
        
        Args:
            thread_id: Thread ID
            
        Returns:
            Thread data dict with messages and their headers
        """
        self.read_limiter.wait_if_needed()
        return self.service.users().threads().get(
            userId='me',
            id=thread_id,
            format='metadata',
            metadataHeaders=['From', 'To', 'Subject']
        ).execute()
    
    def _extract_message_ids(self, thread_data: Dict[str, Any]) -> List[str]:
        """Extract message IDs from thread data."""
        return [m['id'] for m in thread_data.get('messages', [])]
    
    def _extract_from_headers(self, thread_data: Dict[str, Any]) -> List[str]:
        """Extract From headers from thread data."""
        senders = []
        for message in thread_data.get('messages', []):
            for header in message.get('payload', {}).get('headers', []):
                if header['name'] == 'From':
                    senders.append(header['value'])
                    break
        return senders
    
    def list_message_ids_for_threads(self, thread_ids: List[str]) -> List[str]:
        """
        Expand thread IDs to constituent message IDs.
        
        Args:
            thread_ids: List of thread IDs
            
        Returns:
            List of message IDs
            
        Raises:
            APIError: If API call fails
        """
        all_message_ids = []
        
        for thread_id in thread_ids:
            try:
                data = self._get_thread_data(thread_id)
                all_message_ids.extend(self._extract_message_ids(data))
            except Exception as e:
                raise APIError(f"Failed to list message IDs for threads: {str(e)}")
        
        return all_message_ids
    
    def get_thread_senders(self, thread_ids: List[str]) -> List[str]:
        """
        Expand thread IDs and extract From headers.
        
        Args:
            thread_ids: List of thread IDs
            
        Returns:
            List of From header values (one per message)
            
        Raises:
            APIError: If API call fails
        """
        senders = []
        
        for thread_id in thread_ids:
            try:
                data = self._get_thread_data(thread_id)
                senders.extend(self._extract_from_headers(data))
            except Exception as e:
                raise APIError(f"Failed to get thread senders: {str(e)}")
        
        return senders