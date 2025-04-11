# run.py
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


#create a folder named emote_cache in the same directory as this file
import os
if not os.path.exists("emote_cache"):
    os.makedirs("emote_cache")
    print("Created emote_cache directory")
else:
    print("emote_cache directory already exists")

import uvicorn
import logging

# Configure Uvicorn's logger to filter out screenshot requests
class ScreenshotFilter(logging.Filter):
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

# Run the application
uvicorn.run("app:app", host="0.0.0.0", port=8000, access_log=True)
