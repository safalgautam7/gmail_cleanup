"""Gmail Cleanup - A CLI tool to clean up your Gmail inbox."""

import logging
import sys


def setup_logging():
    """Configure logging: console + cleanup.log audit trail."""
    root_logger = logging.getLogger()
    
    # Avoid adding duplicate handlers
    if root_logger.hasHandlers():
        return
    
    root_logger.setLevel(logging.INFO)
    
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root_logger.addHandler(console)
    
    # File handler for audit trail
    file_handler = logging.FileHandler('cleanup.log')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)