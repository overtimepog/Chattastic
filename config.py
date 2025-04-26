import os
import logging

"""
Configuration module for the application.
Contains logging configuration and application settings.
"""

# Set logging level to WARNING to reduce console output
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

# Disable noisy debug logs
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Set screenshot module to INFO level to reduce debug logs
logging.getLogger('api.screenshot').setLevel(logging.INFO)

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Application settings
APP_NAME = "Docker Desktop Viewer"
APP_VERSION = "1.0.0"

# Screenshot settings
SCREENSHOT_INTERVAL = 1.0  # Default screenshot interval in seconds

# Create necessary directories
static_screenshots_dir = os.path.join("static", "screenshots")
if not os.path.exists(static_screenshots_dir):
    os.makedirs(static_screenshots_dir, exist_ok=True)
