"""
Test script for connecting to a Kick streamer's chat using undetected_chromedriver with Selenium.
This script demonstrates how to:
1. Create a persistent browser session with undetected_chromedriver
2. Use Selenium for browser automation
3. Use a proxy when Cloudflare protection is detected
4. Extract chat messages from the DOM
"""

import time
import json
import logging
import os
import sys
import re
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Import undetected_chromedriver
try:
    import undetected_chromedriver as uc
except ImportError:
    print("undetected_chromedriver not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "undetected-chromedriver"])
    import undetected_chromedriver as uc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Use proxy configuration from config.py
PROXY_URL = config.proxy_server

# Global variables
driver = None
last_processed_index = -1
polling_active = False


def setup_driver(use_proxy=False, proxy_url=None):
    """Initialize undetected_chromedriver with a persistent browser session."""
    global driver

    try:
        logger.info("Setting up undetected_chromedriver...")
        options = uc.ChromeOptions()

        # Add arguments for stability and performance
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")

        # Set up proxy if needed
        if use_proxy:
            if not proxy_url:
                proxy_url = PROXY_URL

            logger.info(f"Using proxy: {proxy_url}")
            options.add_argument(f'--proxy-server={proxy_url}')

        # Create a data directory for persistence
        user_data_dir = os.path.join(os.getcwd(), "chrome_data")
        os.makedirs(user_data_dir, exist_ok=True)

        # Initialize the driver with persistence
        driver = uc.Chrome(
            options=options,
            user_data_dir=user_data_dir,
        )

        # Set window size
        driver.set_window_size(1280, 800)
        driver.minimize_window() # Minimize the window to avoid detection

        return True

    except Exception as e:
        logger.error(f"Error setting up undetected_chromedriver: {str(e)}")
        cleanup()
        return False


def connect_to_kick_chat(channel_name, use_proxy=False):
    """Connect to a Kick streamer's chat."""
    global driver, last_processed_index, polling_active

    if not channel_name:
        logger.error("No channel name provided")
        return False

    channel_name = channel_name.strip().lower()
    logger.info(f"Connecting to Kick chat for channel: {channel_name}")

    # Reset state
    last_processed_index = -1

    # Set up driver if not already done
    if not driver:
        success = setup_driver(use_proxy)
        if not success:
            return False

    # Navigate to the channel page
    chat_url = f"https://kick.com/{channel_name}"
    try:
        logger.info(f"Navigating to {chat_url}...")
        driver.get(chat_url)

        # Wait for page to load
        logger.info("Waiting for page to load...")
        time.sleep(5)

        # Check if we need to handle Cloudflare protection
        if check_for_cloudflare():
            if not use_proxy:
                logger.warning("Cloudflare protection detected, retrying with proxy...")
                cleanup()
                return connect_to_kick_chat(channel_name, use_proxy=True)
            else:
                logger.error("Cloudflare protection still detected even with proxy")
                return False

        # Wait for chat container to appear
        logger.info("Waiting for chat container...")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, "chatroom-messages"))
            )
            logger.info("Chat container found!")
        except TimeoutException:
            logger.error("Could not find chat container")
            return False

        # Start polling for messages
        polling_active = True
        import threading
        polling_thread = threading.Thread(target=poll_messages, args=(channel_name,))
        polling_thread.daemon = True
        polling_thread.start()

        return True

    except Exception as e:
        logger.error(f"Error connecting to Kick chat: {str(e)}")
        return False


def check_for_cloudflare():
    """Check if the page is showing Cloudflare protection."""
    try:
        # Look for common Cloudflare elements
        cloudflare_elements = driver.find_elements(By.CSS_SELECTOR,
            "div.cf-browser-verification, div.cf-error-code, div.cf-captcha-container, iframe[src*='cloudflare']"
        )

        if cloudflare_elements:
            logger.warning("Cloudflare protection detected")
            return True

        # Check for title containing Cloudflare
        title = driver.title
        if "cloudflare" in title.lower() or "attention required" in title.lower():
            logger.warning(f"Cloudflare protection detected in title: {title}")
            return True

        return False

    except Exception as e:
        logger.error(f"Error checking for Cloudflare: {str(e)}")
        return False


def poll_messages(channel_name):
    """Continuously poll for new chat messages."""
    global last_processed_index, polling_active

    logger.info(f"Starting to poll messages for channel: {channel_name}")
    message_selector = "div#chatroom-messages > div.relative > div[data-index]"

    while polling_active:
        try:
            message_elements = driver.find_elements(By.CSS_SELECTOR, message_selector)
            if not message_elements:
                time.sleep(1)
                continue

            new_messages_found = False
            max_index_in_batch = last_processed_index

            for element in message_elements:
                # Get the data-index attribute
                index_str = element.get_attribute("data-index")
                if not index_str:
                    continue

                try:
                    index = int(index_str)
                    if index > last_processed_index:
                        new_messages_found = True
                        max_index_in_batch = max(max_index_in_batch, index)

                        # Get the HTML content of the message
                        html = element.get_attribute("outerHTML")

                        # Parse the message
                        message = parse_message(html, index)
                        if message:
                            # Print the message
                            print(f"[{message['timestamp']}] {message['sender']}: {message['content']}")

                            # Here you could store messages in a queue or process them further
                except ValueError:
                    logger.warning(f"Invalid data-index: {index_str}")
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")

            # Update the last processed index
            if new_messages_found:
                last_processed_index = max_index_in_batch
                logger.info(f"Processed messages up to index {last_processed_index}")

            time.sleep(0.8)

        except Exception as e:
            logger.error(f"Error polling messages: {str(e)}")
            time.sleep(1)

    logger.info("Message polling stopped")


def parse_message(html, index):
    """Parse a chat message from HTML."""
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # Extract username
        username_element = soup.select_one("span.chat-entry-username")
        username_text = username_element.text.strip() if username_element else "Unknown"

        # Extract message content
        message_element = soup.select_one("div.chat-entry-content")
        message_text = message_element.text.strip() if message_element else ""

        # Extract timestamp
        timestamp_element = soup.select_one("div.chat-entry-timestamp")
        timestamp_text = timestamp_element.text.strip() if timestamp_element else datetime.now().strftime("%H:%M")

        # Extract emotes
        emotes_list = []
        emote_elements = soup.select("img.chat-emote")
        for emote in emote_elements:
            emote_name = emote.get("alt", "")
            emote_url = emote.get("src", "")
            if emote_name and emote_url:
                emotes_list.append({"name": emote_name, "url": emote_url})

        # Remove unwanted square brackets after emojis
        message_text = re.sub(r'\[\]', '', message_text)

        return {
            "data_index": index,
            "timestamp": timestamp_text,
            "sender": username_text,
            "content": message_text,
            "emotes": emotes_list
        }

    except Exception as e:
        logger.error(f"Error parsing message at index {index}: {str(e)}")
        return None


def cleanup():
    """Clean up driver resources."""
    global driver, polling_active

    logger.info("Cleaning up resources...")
    polling_active = False

    try:
        if driver:
            logger.info("Closing driver...")
            driver.quit()

    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")

    driver = None


def main():
    """Main function to run the test."""
    channel_name = input("Enter Kick channel name: ")

    try:
        connected = connect_to_kick_chat(channel_name)
        if connected:
            logger.info(f"Successfully connected to {channel_name}'s chat")
            logger.info("Press Ctrl+C to exit")

            # Keep the script running
            while polling_active:
                time.sleep(1)
        else:
            logger.error(f"Failed to connect to {channel_name}'s chat")

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, exiting...")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")

    finally:
        cleanup()


if __name__ == "__main__":
    main()
