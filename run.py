# run.py
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn
uvicorn.run("app:app", host="0.0.0.0", port=8000)
