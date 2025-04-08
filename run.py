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
uvicorn.run("app:app", host="0.0.0.0", port=8000)
