"""OAuth2 authentication for Gmail API."""

import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


class AuthError(Exception):
    """Raised when authentication fails."""
    pass


def get_credentials(credentials_path: str, token_path: str) -> Credentials:
    """
    Load credentials from token file if available, otherwise run OAuth flow.
    
    Args:
        credentials_path: Path to credentials.json file
        token_path: Path to store/load token.json file
        
    Returns:
        Google API credentials object
        
    Raises:
        AuthError: If authentication fails
    """
    creds = None
    
    # Check if token file exists
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path)
        except Exception as e:
            raise AuthError(f"Failed to load token from {token_path}: {str(e)}")
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                raise AuthError(f"Failed to refresh credentials: {str(e)}")
        else:
            if not os.path.exists(credentials_path):
                raise AuthError(
                    f"Credentials file not found at {credentials_path}. "
                    "Please follow the Google Cloud setup steps in README.md"
                )
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, 
                    ['https://www.googleapis.com/auth/gmail.modify']
                )
                creds = flow.run_local_server(port=0)
            except Exception as e:
                raise AuthError(f"OAuth flow failed: {str(e)}")
        
        # Save the credentials for the next run
        try:
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        except Exception as e:
            raise AuthError(f"Failed to save token to {token_path}: {str(e)}")
    
    return creds