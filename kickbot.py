import time
import datetime
import requests
import threading
import json # Added for potential parsing errors
from utils.ui_utils import clear_error_message_after_delay
import selenium
import undetected_chromedriver as uc
from datetime import timedelta

# --- Class-based approach for better management ---
import asyncio
import kick
import sys
def get_latest_stream_video_id(username):
    # Start an undetected ChromeDriver session
    #create options to do it headless
    options = uc.ChromeOptions() # Run in headless mode
    driver = uc.Chrome(options=options)
    try:
        # Open the Kick channel API endpoint for the given username
        driver.get(f"https://kick.com/api/v2/channels/{username}/videos/latest")
        time.sleep(5)  # Wait for the page to load fully

        # Extract all data from the body text
        body_text = driver.find_element("tag name", "body").text
        
        # Parse the JSON data found in the page source
        data = json.loads(body_text)
        print(f"{data}")
        video_id = data.get("data", {}).get("video", {}).get("id")
        video_id = str(video_id) if video_id else None
        if not video_id:
            print(f"Video ID not found for username: {username}")
            return None
        return video_id
    except Exception as e:
        print("Error:", e)
        return None
    finally:
        driver.quit()
        
from kickapi import KickAPI
# Create an instance of KickAPI
kick_api = KickAPI()

# Fetch channel data by username
channel = kick_api.channel("ameliavii")
stream_video_id = get_latest_stream_video_id("ameliavii")
if stream_video_id is None:
    print("Failed to retrieve video ID.")
    sys.exit(1)

# Fetch video data
video = kick_api.video(stream_video_id)

while True:
    # Convert to datetime object and format in the desired way
    original_date_obj = datetime.strptime(video.start_time, '%Y-%m-%d %H:%M:%S')
    formatted_date_str = original_date_obj.strftime('%Y-%m-%dT%H:%M:%S.000Z')

    # Fetch chat data for the video's channel and the specific date
    chat = kick_api.chat(video.channel.id, formatted_date_str)

    # Iterate over messages and print sender's username and text
    for message in chat.messages:
        print("{}: {}".format(message.sender.username, message.text))

    # Update start_time for the next iteration and pause for 5 seconds
    video.start_time = (original_date_obj + timedelta(seconds=5)).strftime('%Y-%m-%d %H:%M:%S')
    time.sleep(5)

        

