"""Build Gmail search-operator strings."""

import re
from typing import Dict, Any


def build_query(mode: str, **kwargs) -> str:
    """
    Build Gmail search query for the specified mode.
    
    Args:
        mode: Query mode
        **kwargs: Additional parameters (time_threshold, sender, etc.)
        
    Returns:
        Gmail search query string
        
    Raises:
        ValueError: If mode is invalid or parameters are incorrect
    """
    queries = {
        'non_starred': '-is:starred -in:sent -in:drafts -in:trash -in:spam',
        'non_important': '-is:important -in:sent -in:drafts -in:trash -in:spam',
        'non_starred_and_non_important': '-is:starred -is:important -in:sent -in:drafts -in:trash -in:spam',
        'all': '-in:sent -in:drafts -in:trash',
        'report': '-in:trash -in:spam'
    }
    
    if mode in queries:
        return queries[mode]
    
    if mode == 'by_time':
        threshold = kwargs.get('time_threshold')
        if not threshold:
            raise ValueError("time_threshold is required for by_time mode")
        
        # Validate threshold format (e.g., 30d, 1y, 6m)
        if not re.match(r'^\d+[dmy]$', threshold):
            raise ValueError(f"Invalid time threshold format: {threshold}")
        
        return f'older_than:{threshold} -in:trash -in:drafts'
    
    if mode == 'by_sender':
        sender = kwargs.get('sender')
        if not sender:
            raise ValueError("sender is required for by_sender mode")
        
        return f'from:{sender} -in:trash'
    
    raise ValueError(f"Unknown mode: {mode}")