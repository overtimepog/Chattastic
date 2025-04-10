"""
Settings management module for Chattastic.

This module handles loading and saving settings to the host machine's Chattastic folder
instead of inside the Docker container.
"""

import os
import json
import logging
import shutil
from typing import Dict, Any, Optional
from pathlib import Path

# Set up logging
logger = logging.getLogger(__name__)

# Constants
SETTINGS_FILE = "chattastic_settings.json"
HOST_SETTINGS_DIR = "/host_settings"  # Mount point for host settings directory
EXPORT_DIR = "exports"  # Directory for exported settings
DEFAULT_SETTINGS = {
    "obs_source": {
        "width": 800,
        "height": 600,
        "bottom_margin": 10
    },
    "overlay": {
        "text_color": "#ffffff",
        "background_color": "rgba(0, 0, 0, 0.5)",
        "font_size": 16,
        "padding": 10,
        "gap": 5,
        "border_radius": 5,
        "flow_direction": "upwards"
    },
    "random_overlay": {
        "message_duration": 5,
        "animation_duration": 500,
        "max_messages": 10,
        "debug_mode": False
    },
    "screenshot": {
        "interval": 1.0
    },
    "ui": {
        "dark_mode": True
    }
}

# Global settings cache
_settings_cache = None


def is_docker() -> bool:
    """Check if we're running inside a Docker container."""
    return os.path.exists('/.dockerenv') or os.path.isfile('/proc/1/cgroup') and any('docker' in line for line in open('/proc/1/cgroup'))


def get_settings_path() -> str:
    """
    Get the path to the settings file.

    If running in Docker, use the mounted host directory.
    Otherwise, use the current directory.
    """
    if is_docker() and os.path.exists(HOST_SETTINGS_DIR):
        return os.path.join(HOST_SETTINGS_DIR, SETTINGS_FILE)
    return SETTINGS_FILE


def load_settings() -> Dict[str, Any]:
    """
    Load settings from the settings file.

    If the file doesn't exist, create it with default settings.
    """
    global _settings_cache

    # Return cached settings if available
    if _settings_cache is not None:
        return _settings_cache

    settings_path = get_settings_path()

    # If settings file doesn't exist, create it with defaults
    if not os.path.exists(settings_path):
        logger.info(f"Settings file not found at {settings_path}. Creating with defaults.")
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

    try:
        with open(settings_path, 'r') as file:
            settings = json.load(file)
            logger.info(f"Settings loaded from {settings_path}")

            # Merge with defaults to ensure all keys exist
            merged_settings = DEFAULT_SETTINGS.copy()
            _deep_update(merged_settings, settings)

            # Cache the settings
            _settings_cache = merged_settings
            return merged_settings
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {settings_path}. File might be corrupted.")
        # Backup the corrupted file
        backup_path = f"{settings_path}.bak"
        try:
            shutil.copy2(settings_path, backup_path)
            logger.info(f"Backed up corrupted settings file to {backup_path}")
        except Exception as e:
            logger.error(f"Failed to backup corrupted settings file: {e}")

        # Create a new file with defaults
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    except Exception as e:
        logger.error(f"Error loading settings from {settings_path}: {e}")
        return DEFAULT_SETTINGS


def save_settings(settings: Dict[str, Any]) -> bool:
    """
    Save settings to the settings file.

    Args:
        settings: The settings to save

    Returns:
        bool: True if successful, False otherwise
    """
    global _settings_cache

    settings_path = get_settings_path()

    # Ensure the directory exists
    os.makedirs(os.path.dirname(settings_path) if os.path.dirname(settings_path) else '.', exist_ok=True)

    try:
        # Merge with defaults to ensure all keys exist
        merged_settings = DEFAULT_SETTINGS.copy()
        _deep_update(merged_settings, settings)

        with open(settings_path, 'w') as file:
            json.dump(merged_settings, file, indent=2)

        logger.info(f"Settings saved to {settings_path}")

        # Update the cache
        _settings_cache = merged_settings
        return True
    except Exception as e:
        logger.error(f"Error saving settings to {settings_path}: {e}")
        return False


def update_settings(new_settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update settings with new values and save to file.

    Args:
        new_settings: The new settings to apply

    Returns:
        Dict[str, Any]: The updated settings
    """
    current_settings = load_settings()
    _deep_update(current_settings, new_settings)
    save_settings(current_settings)
    return current_settings


def get_setting(key_path: str, default: Any = None) -> Any:
    """
    Get a specific setting by key path.

    Args:
        key_path: Dot-separated path to the setting (e.g., 'obs_source.width')
        default: Default value to return if the setting doesn't exist

    Returns:
        The setting value or default if not found
    """
    settings = load_settings()
    keys = key_path.split('.')

    # Navigate through the nested dictionary
    current = settings
    for key in keys:
        if key not in current:
            return default
        current = current[key]

    return current


def set_setting(key_path: str, value: Any) -> bool:
    """
    Set a specific setting by key path.

    Args:
        key_path: Dot-separated path to the setting (e.g., 'obs_source.width')
        value: The value to set

    Returns:
        bool: True if successful, False otherwise
    """
    settings = load_settings()
    keys = key_path.split('.')

    # Navigate through the nested dictionary
    current = settings
    for i, key in enumerate(keys[:-1]):
        if key not in current:
            current[key] = {}
        current = current[key]

    # Set the value
    current[keys[-1]] = value

    return save_settings(settings)


def migrate_tokens_to_settings():
    """
    Migrate existing token files to the settings system.
    """
    import config

    settings = load_settings()
    settings.setdefault('auth', {})

    # Migrate Twitch tokens
    if os.path.exists(config.TOKEN_FILE):
        try:
            with open(config.TOKEN_FILE, 'r') as file:
                twitch_tokens = json.load(file)
                if 'access_token' in twitch_tokens and 'refresh_token' in twitch_tokens:
                    settings['auth']['twitch'] = twitch_tokens
                    logger.info("Migrated Twitch tokens to settings")
        except Exception as e:
            logger.error(f"Error migrating Twitch tokens: {e}")

    # Migrate Kick tokens
    if os.path.exists(config.KICK_TOKEN_FILE):
        try:
            with open(config.KICK_TOKEN_FILE, 'r') as file:
                kick_tokens = json.load(file)
                if 'access_token' in kick_tokens:
                    settings['auth']['kick'] = kick_tokens
                    logger.info("Migrated Kick tokens to settings")
        except Exception as e:
            logger.error(f"Error migrating Kick tokens: {e}")

    save_settings(settings)


def _deep_update(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    """
    Deep update a nested dictionary.

    Args:
        target: The dictionary to update
        source: The dictionary with updates
    """
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def export_settings(filename: str = None) -> Dict[str, Any]:
    """
    Export settings to a separate file in the exports directory.

    Args:
        filename: Optional custom filename (without extension)

    Returns:
        Dict[str, Any]: The exported settings
    """
    # Load current settings
    settings = load_settings()

    # Create exports directory if it doesn't exist
    export_dir = os.path.join(os.path.dirname(get_settings_path()), EXPORT_DIR)
    os.makedirs(export_dir, exist_ok=True)

    # Generate filename if not provided
    if not filename:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chattastic_settings_{timestamp}"

    # Ensure .json extension
    if not filename.endswith(".json"):
        filename += ".json"

    export_path = os.path.join(export_dir, filename)

    try:
        with open(export_path, 'w') as file:
            json.dump(settings, file, indent=2)
        logger.info(f"Settings exported to {export_path}")
        return {
            "success": True,
            "path": export_path,
            "settings": settings
        }
    except Exception as e:
        logger.error(f"Error exporting settings to {export_path}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def import_settings(filepath: str) -> Dict[str, Any]:
    """
    Import settings from a file.

    Args:
        filepath: Path to the settings file to import

    Returns:
        Dict[str, Any]: Result of the import operation
    """
    if not os.path.exists(filepath):
        logger.error(f"Import file not found: {filepath}")
        return {
            "success": False,
            "error": f"File not found: {filepath}"
        }

    try:
        with open(filepath, 'r') as file:
            imported_settings = json.load(file)

        # Validate imported settings
        if not isinstance(imported_settings, dict):
            logger.error(f"Invalid settings format in {filepath}")
            return {
                "success": False,
                "error": "Invalid settings format"
            }

        # Save the imported settings
        save_settings(imported_settings)
        logger.info(f"Settings imported from {filepath}")

        return {
            "success": True,
            "settings": imported_settings
        }
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {filepath}")
        return {
            "success": False,
            "error": "Invalid JSON format"
        }
    except Exception as e:
        logger.error(f"Error importing settings from {filepath}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def get_settings_location() -> Dict[str, Any]:
    """
    Get information about where settings are being stored.

    Returns:
        Dict[str, Any]: Information about settings location
    """
    settings_path = get_settings_path()
    in_docker = is_docker()
    using_host_dir = in_docker and os.path.exists(HOST_SETTINGS_DIR)

    return {
        "path": settings_path,
        "in_docker": in_docker,
        "using_host_dir": using_host_dir,
        "is_persistent": using_host_dir or not in_docker
    }


def initialize():
    """
    Initialize the settings module.

    This should be called during application startup.
    """
    logger.info("Initializing settings module...")
    settings = load_settings()
    migrate_tokens_to_settings()

    # Log settings location information
    location_info = get_settings_location()
    if location_info["is_persistent"]:
        logger.info(f"Settings are being stored persistently at {location_info['path']}")
    else:
        logger.warning(f"Settings are NOT persistent! They are stored at {location_info['path']} inside the container.")

    logger.info("Settings module initialized")
    return settings
