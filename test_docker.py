"""
Test script for running Chattastic in Docker with Xvfb.
This script will:
1. Connect to a Kick chat channel
2. Run for a specified duration
3. Disconnect and clean up
"""

import asyncio
import logging
import os
import sys
from api.kick import connect_kick_chat, disconnect_kick_chat, shutdown_selenium_driver

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a dummy manager for testing in Docker
class DummyManager:
    async def broadcast(self, msg):
        print(f"BROADCAST: {msg}")

# Import globals and set the manager
import globals
globals.manager = DummyManager()

async def test_docker():
    try:
        # Check if running in Docker
        in_docker = os.path.exists('/.dockerenv')
        logger.info(f"Running in Docker: {in_docker}")
        
        # Get channel name from command line or use default
        if len(sys.argv) > 1:
            channel_name = sys.argv[1]
        else:
            channel_name = input("Enter Kick channel name (e.g., xqc): ").strip() or "xqc"
        
        # Get duration from command line or use default
        if len(sys.argv) > 2:
            duration = int(sys.argv[2])
        else:
            duration = 60  # Default 60 seconds
        
        logger.info(f"Connecting to Kick chat for channel: {channel_name}")
        logger.info(f"Will run for {duration} seconds")
        
        # Connect to Kick chat
        connected = await connect_kick_chat(channel_name)
        
        if connected:
            logger.info(f"Connected! Running for {duration} seconds...")
            logger.info("Browser should be running with keep-alive thread active")
            
            # Wait for specified duration
            await asyncio.sleep(duration)
            
            # Disconnect
            logger.info("Disconnecting...")
            await disconnect_kick_chat()
            await shutdown_selenium_driver()
            logger.info("Done!")
        else:
            logger.error("Failed to connect to Kick chat")
    
    except Exception as e:
        logger.exception(f"Error in test_docker: {e}")
        # Ensure cleanup
        try:
            await disconnect_kick_chat()
            await shutdown_selenium_driver()
        except Exception as cleanup_err:
            logger.error(f"Error during cleanup: {cleanup_err}")

if __name__ == "__main__":
    asyncio.run(test_docker())
