"""Gmail API client wrapper."""

import time
import random
from functools import wraps
from typing import Any, Dict, Iterator, List, Optional
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
                    pageToken=page_token,
                    fields='nextPageToken,threads/id'
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
    def get_message_headers(
        self, message_id: str, headers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
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
        if headers is None:
            headers = ['From']

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
    def _get_thread_data(
        self, thread_id: str, headers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get thread metadata from Gmail API.
        
        Args:
            thread_id: Thread ID
            headers: Header names to retrieve
            
        Returns:
            Thread data dict with messages and requested headers
        """
        if headers is None:
            headers = ['From']

        self.read_limiter.wait_if_needed()
        return self._thread_get_request(thread_id, headers).execute()

    def _thread_get_request(self, thread_id: str, headers: List[str]):
        fields = 'messages/id'
        request = {
            'userId': 'me',
            'id': thread_id,
            'format': 'metadata',
            'fields': fields,
        }
        if headers:
            request['metadataHeaders'] = headers
            request['fields'] = 'messages(id,payload/headers(name,value))'

        return self.service.users().threads().get(**request)

    @retry_with_backoff()
    def _get_threads_data_batch(
        self, thread_ids: List[str], headers: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get thread metadata for multiple threads using a Gmail batch request.

        Batch requests reduce HTTP round trips, though each subrequest still
        counts against Gmail API quota.
        """
        if not thread_ids:
            return []
        if headers is None:
            headers = ['From']

        all_responses: Dict[str, Dict[str, Any]] = {}
        batch_size = 100

        for start in range(0, len(thread_ids), batch_size):
            thread_ids_batch = thread_ids[start:start + batch_size]
            responses: Dict[str, Dict[str, Any]] = {}
            errors: Dict[str, Exception] = {}

            def callback(request_id, response, exception):
                if exception is not None:
                    errors[request_id] = exception
                else:
                    responses[request_id] = response

            batch = self.service.new_batch_http_request(callback=callback)
            for thread_id in thread_ids_batch:
                self.read_limiter.wait_if_needed()
                batch.add(
                    self._thread_get_request(thread_id, headers),
                    request_id=thread_id,
                )

            batch.execute()

            if errors:
                thread_id, error = next(iter(errors.items()))
                if isinstance(error, HttpError):
                    raise error
                raise APIError(f"Failed to get thread {thread_id}: {str(error)}")

            all_responses.update(responses)

        return [
            all_responses[thread_id]
            for thread_id in thread_ids
            if thread_id in all_responses
        ]
    
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
        
        try:
            for data in self._get_threads_data_batch(thread_ids, headers=[]):
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
        
        try:
            for data in self._get_threads_data_batch(thread_ids, headers=['From']):
                senders.extend(self._extract_from_headers(data))
        except Exception as e:
            raise APIError(f"Failed to get thread senders: {str(e)}")
        
        return senders