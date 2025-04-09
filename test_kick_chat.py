import asyncio
import logging
from api.kick import connect_kick_chat, disconnect_kick_chat, shutdown_selenium_driver

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test():
    try:
        print('Connecting to Kick chat...')
        connected = await connect_kick_chat('xqc')  # Using a popular Kick streamer
        
        if connected:
            print('Connected! Running for 30 seconds...')
            print('Browser should be resized to 1/4 size and keep-alive thread should be active')
            await asyncio.sleep(30)
            
            print('Disconnecting...')
            await disconnect_kick_chat()
            await shutdown_selenium_driver()
            print('Done!')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    asyncio.run(test())
