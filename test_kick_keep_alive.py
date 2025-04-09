import asyncio
import logging
from api.kick import connect_kick_chat, disconnect_kick_chat, shutdown_selenium_driver

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test():
    try:
        print('Connecting to Kick chat...')
        # Connect to a popular Kick streamer
        channel_name = input("Enter Kick channel name (e.g., xqc): ").strip() or "xqc"
        
        connected = await connect_kick_chat(channel_name)
        
        if connected:
            print(f'Connected to {channel_name}! Running for 5 minutes to test keep-alive...')
            print('Browser should be resized to 1/4 size in the bottom right corner')
            print('Keep-alive thread should be active with:')
            print('- Alert popups every 15 seconds')
            print('- Page refresh every 60 seconds')
            print('- Continuous JavaScript activity')
            print('Press Ctrl+C to stop the test early')
            
            # Run for 5 minutes to test keep-alive
            try:
                await asyncio.sleep(300)  # 5 minutes
            except KeyboardInterrupt:
                print("Test interrupted by user")
            
            print('Disconnecting...')
            await disconnect_kick_chat()
            await shutdown_selenium_driver()
            print('Test completed successfully!')
        else:
            print(f'Failed to connect to {channel_name}')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    # Initialize globals and config for testing
    import globals
    import config
    
    # Initialize dummy globals manager if needed for testing broadcast
    class DummyManager:
        async def broadcast(self, msg): 
            print(f"BROADCAST: {msg}")
    
    globals.manager = DummyManager()
    globals.kick_emotes = {}
    
    # Initialize config attributes
    config.kick_chat_connected = False
    config.kick_chat_stream = None
    config.kick_channel_id = None
    config.kick_channel_name = None
    config.kick_chat_messages = []
    config.entered_users = []
    
    # Run the test
    asyncio.run(test())
