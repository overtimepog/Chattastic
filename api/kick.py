import time
import datetime
import requests
import threading
import json # Added for potential parsing errors
from utils.ui_utils import clear_error_message_after_delay
import selenium
import undetected_chromedriver as uc

# --- Class-based approach for better management ---
import asyncio
import kick
import sys

# Set the correct event loop policy for Windows
if sys.platform.startswith('win'):
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Create the Kick client but don't run it yet
global Kickclient
Kickclient = kick.Client()

class KickChatStream():
    def __init__(self, channel_id, access_token, streamer):
        self.channel_id = channel_id
        self.access_token = access_token
        self.client = Kickclient
        self.running = False
        self.streamer = streamer
        
    @Kickclient.event 
    async def on_message(message):
        print(f"Message from {message.author}: {message.content}")
    
    @Kickclient.event 
    async def on_ready(self):
        print(f"Connected to Kick chat as {self.client.user.name}")
        print(f"Streamer: {self.streamer}")
        
    async def connect(self):
        if not self.running:
            self.running = True
            await self.client.start(channel_id=self.channel_id, access_token=self.access_token)
            user = await self.client.fetch_user(f"{self.streamer}")
            await user.chatroom.connect()
        

import os
import dearpygui.dearpygui as dpg
import config

def load_kick_tokens():
    """Load Kick authentication tokens from file"""
    if os.path.exists(config.KICK_TOKEN_FILE):
        try:
            with open(config.KICK_TOKEN_FILE, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {config.KICK_TOKEN_FILE}. File might be corrupted.")
            return None
    return None

#https://api.kick.com/public/v1/users

def get_kick_channel_id(username, access_token):
    # Start an undetected ChromeDriver session
    #create options to do it headless
    options = uc.ChromeOptions() # Run in headless mode
    driver = uc.Chrome(options=options)
    try:
        # Open the Kick channel API endpoint for the given username
        driver.get(f"https://kick.com/api/v2/channels/{username}")
        time.sleep(5)  # Wait for the page to load fully

        # Extract all data from the body text
        body_text = driver.find_element("tag name", "body").text
        
        # Parse the JSON data found in the page source
        data = json.loads(body_text)
        
        # Retrieve the channel ID from the parsed JSON
        channel_id = data.get("id")
        channel_id = str(channel_id) if channel_id else None
        if not channel_id:
            print(f"Channel ID not found for username: {username}")
            return None
        return channel_id
    except Exception as e:
        print("Error:", e)
        return None
    finally:
        driver.quit()

def start_kick_button_callback():
    """Handle the Connect Kick Chat button click"""
    print("Connect Kick Chat Clicked")
    
    # 1. Validate inputs and authentication
    channel_name_input = dpg.get_value("user_data")
    print("Channel name input:", channel_name_input)
    if not channel_name_input or channel_name_input.isspace():
        dpg.set_value("error_display", "Error: Enter channel name to connect chat.")
        dpg.configure_item("error_display", color=[255, 0, 0])
        
        # We need to import this function since it's in a different module
        clear_error_message_after_delay(5)
        return
    
    # 2. Check if authenticated with Kick
    tokens = load_kick_tokens()
    if not tokens or 'access_token' not in tokens:
        print("Kick authentication tokens are missing or invalid.")
        dpg.set_value("error_display", "Error: Please authenticate with Kick first.")
        dpg.configure_item("error_display", color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return
    
    access_token = tokens['access_token']
    
    # 3. Get channel ID from username
    channel_name = channel_name_input.strip().lower()
    channel_id = get_kick_channel_id(channel_name, access_token)
    if not channel_id:
        dpg.set_value("error_display", f"Error: Could not find Kick channel: {channel_name}")
        dpg.configure_item("error_display", color=[255, 0, 0])
        
        clear_error_message_after_delay(5)
        return
    
    # 4. Start the Kick chat stream
    async def start_kick_chat_stream():
        channel_id = channel_id
        access_token = access_token
        channel_name = channel_name
        
        # Create and connect the Kick chat stream
        kick_chat_stream = KickChatStream(channel_id, access_token, channel_name)
        
        await kick_chat_stream.connect()
        dpg.set_value("error_display", f"Connected to Kick chat: {channel_name}")
        dpg.configure_item("error_display", color=[0, 255, 0])
        clear_error_message_after_delay(5)
    
    start_kick_chat_stream_thread = threading.Thread(target=start_kick_chat_stream, daemon=True)
    start_kick_chat_stream_thread.start()

