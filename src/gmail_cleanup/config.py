"""Load and validate configuration."""

import re
import yaml
from typing import Dict, Any


def load_yaml(path: str) -> Dict[str, Any]:
    """Load YAML file."""
    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        raise ValueError(f"Failed to load config file {path}: {str(e)}")


def load_config(config_path: str, cli_overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load configuration with CLI overrides.
    
    Config Precedence Rules (highest to lowest):
    1. CLI flags always override config file values when explicitly set
    2. Safety-critical flags (--dry-run) default to True even if not specified in CLI or config
    3. Config file provides defaults for non-safety settings
    4. Missing values in config fall back to internal defaults
    
    Args:
        config_path: Path to config file
        cli_overrides: Dictionary of CLI flag values
        
    Returns:
        Configuration dictionary
    """
    config = load_yaml(config_path)
    
    # CLI overrides take precedence
    for key, value in cli_overrides.items():
        if value is not None:  # Only override if CLI flag was explicitly set
            config[key] = value
    
    # Safety default: dry_run defaults to True unless explicitly set to False
    if 'dry_run' not in config or config['dry_run'] is None:
        config['dry_run'] = True
    
    # Set defaults for other values if not present
    if 'mode' not in config:
        config['mode'] = 'report'
    if 'time_threshold' not in config:
        config['time_threshold'] = '30d'
    if 'sender_list' not in config:
        config['sender_list'] = []
    if 'credentials_path' not in config:
        config['credentials_path'] = 'credentials.json'
    if 'token_path' not in config:
        config['token_path'] = 'token.json'
    
    validate_config(config)
    return config


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate configuration.
    
    Args:
        config: Configuration dictionary
        
    Raises:
        ValueError: If configuration is invalid
    """
    valid_modes = [
        'report', 'non_starred', 'non_important', 
        'non_starred_and_non_important', 'all', 
        'by_time', 'by_sender'
    ]
    
    if config['mode'] not in valid_modes:
        raise ValueError(f"Invalid mode: {config['mode']}. Must be one of {valid_modes}")
    
    # Validate time_threshold format if mode is by_time
    if config['mode'] == 'by_time' and 'time_threshold' in config:
        if not re.match(r'^\d+[dmy]$', config['time_threshold']):
            raise ValueError(f"Invalid time threshold format: {config['time_threshold']}")