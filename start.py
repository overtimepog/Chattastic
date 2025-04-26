#!/usr/bin/env python3
"""
Docker Desktop Viewer - Main Entry Point

This script starts the Docker Desktop Viewer application.
It configures the event loop policy for Windows and sets up logging filters.
"""

import sys
import os
import asyncio
import logging
import uvicorn

# Configure event loop policy for Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Create necessary directories
if not os.path.exists("static/screenshots"):
    os.makedirs("static/screenshots", exist_ok=True)
    print("Created screenshots directory")

if not os.path.exists("debug_screenshots"):
    os.makedirs("debug_screenshots", exist_ok=True)
    print("Created debug_screenshots directory")

# Configure Uvicorn's logger to filter out screenshot requests
class ScreenshotFilter(logging.Filter):
    """Filter to remove screenshot API requests from logs to reduce noise."""
    def filter(self, record):
        # Filter out screenshot API requests
        return not (
            hasattr(record, 'args') and
            len(record.args) >= 3 and
            isinstance(record.args[2], str) and
            '/api/screenshot' in record.args[2]
        )

# Apply the filter to Uvicorn's access logger
logging.getLogger("uvicorn.access").addFilter(ScreenshotFilter())

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    print("Starting Docker Desktop Viewer...")
    # Run the application
    uvicorn.run("app:app", host="0.0.0.0", port=8000, access_log=True)
