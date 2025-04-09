"""
Test script for connecting to a Kick streamer's chat using Playwright with stealth mode.
This script demonstrates how to:
1. Create a persistent browser session with Playwright
2. Apply stealth mode to avoid detection
3. Use a proxy when Cloudflare protection is detected
4. Extract chat messages from the DOM
"""

import asyncio
import json
import logging
import os
import time
import sys
from datetime import datetime
from bs4 import BeautifulSoup

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Playwright imports
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_async

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Use proxy configuration from config.py
PROXY_CONFIG = config.pw_proxy_config

# Global variables
playwright_instance = None
browser_instance = None
context = None
page = None
last_processed_index = -1
polling_active = False


async def setup_playwright(use_proxy=False):
    """Initialize Playwright with a persistent browser session."""
    global playwright_instance, browser_instance, context, page

    try:
        logger.info("Initializing Playwright...")
        playwright_instance = await async_playwright().start()

        # Launch browser
        logger.info("Launching browser...")
        browser_instance = await playwright_instance.chromium.launch(  # Set to False for debugging
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )

        # Define user agent for better stealth
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36"

        # Create context with proxy if needed
        if use_proxy:
            logger.info(f"Creating browser context with proxy: {PROXY_CONFIG['server']} and user agent")
            context = await browser_instance.new_context(proxy=PROXY_CONFIG, user_agent=user_agent)
        else:
            logger.info(f"Creating browser context with user agent: {user_agent}")
            context = await browser_instance.new_context(user_agent=user_agent)

        # Create page and apply stealth
        logger.info(f"Creating new page and applying stealth with user agent: {user_agent}...")
        page = await context.new_page()
        await stealth_async(page)

        # Set up event listeners
        page.on("close", lambda: logger.warning("Page was closed!"))
        page.on("crash", lambda: logger.error("Page crashed!"))

        return True

    except Exception as e:
        logger.error(f"Error setting up Playwright: {str(e)}")
        await cleanup()
        return False


async def connect_to_kick_chat(channel_name, use_proxy=False):
    """Connect to a Kick streamer's chat."""
    global page, last_processed_index, polling_active

    if not channel_name:
        logger.error("No channel name provided")
        return False

    channel_name = channel_name.strip().lower()
    logger.info(f"Connecting to Kick chat for channel: {channel_name}")

    # Reset state
    last_processed_index = -1

    # Set up Playwright if not already done
    if not page or page.is_closed():
        success = await setup_playwright(use_proxy)
        if not success:
            return False

    # Navigate to the channel page
    chat_url = f"https://kick.com/{channel_name}"
    try:
        logger.info(f"Navigating to {chat_url}...")
        await page.goto(chat_url, wait_until="load", timeout=90000)
        logger.info("Waiting for page DOM content to be loaded...")
        await page.wait_for_load_state('domcontentloaded', timeout=60000)

        # Check if we need to handle Cloudflare protection
        if await check_for_cloudflare():
            if not use_proxy:
                logger.warning("Cloudflare protection detected, retrying with proxy...")
                await cleanup()
                return await connect_to_kick_chat(channel_name, use_proxy=True)
            else:
                logger.error("Cloudflare protection still detected even with proxy")
                return False

        # Wait for chat container to appear
        logger.info("Waiting for chat container...")
        try:
            await page.wait_for_selector("div#chatroom-messages", timeout=30000)
            logger.info("Chat container found!")
        except PlaywrightTimeoutError:
            logger.error("Could not find chat container")
            return False

        # Start polling for messages
        polling_active = True
        asyncio.create_task(poll_messages(channel_name))

        return True

    except Exception as e:
        logger.error(f"Error connecting to Kick chat: {str(e)}")
        return False


async def check_for_cloudflare():
    """Check if the page is showing Cloudflare protection."""
    try:
        # Look for common Cloudflare elements
        cloudflare_elements = await page.query_selector_all([
            "div.cf-browser-verification",
            "div.cf-error-code",
            "div.cf-captcha-container",
            "iframe[src*='cloudflare']"
        ])

        if cloudflare_elements:
            logger.warning("Cloudflare protection detected")
            return True

        # Check for title containing Cloudflare
        title = await page.title()
        if "cloudflare" in title.lower() or "attention required" in title.lower():
            logger.warning(f"Cloudflare protection detected in title: {title}")
            return True

        return False

    except Exception as e:
        logger.error(f"Error checking for Cloudflare: {str(e)}")
        return False


async def poll_messages(channel_name):
    """Continuously poll for new chat messages."""
    global last_processed_index, polling_active

    logger.info(f"Starting to poll messages for channel: {channel_name}")
    message_selector = "div#chatroom-messages > div.relative > div[data-index]"

    while polling_active:
        try:
            if page.is_closed():
                logger.warning("Page is closed. Stopping polling.")
                polling_active = False
                break

            message_elements = await page.query_selector_all(message_selector)
            if not message_elements:
                await asyncio.sleep(1)
                continue

            new_messages_found = False
            max_index_in_batch = last_processed_index

            for element in message_elements:
                # Get the data-index attribute
                index_str = await element.get_attribute("data-index")
                if not index_str:
                    continue

                try:
                    index = int(index_str)
                    if index > last_processed_index:
                        new_messages_found = True
                        max_index_in_batch = max(max_index_in_batch, index)

                        # Get the HTML content of the message
                        html = await element.evaluate("el => el.outerHTML")

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

            await asyncio.sleep(0.8)

        except Exception as e:
            logger.error(f"Error polling messages: {str(e)}")
            await asyncio.sleep(1)

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


async def cleanup():
    """Clean up Playwright resources."""
    global playwright_instance, browser_instance, context, page, polling_active

    logger.info("Cleaning up resources...")
    polling_active = False

    try:
        if page and not page.is_closed():
            logger.info("Closing page...")
            await page.close()

        if context:
            logger.info("Closing context...")
            await context.close()

        if browser_instance and browser_instance.is_connected():
            logger.info("Closing browser...")
            await browser_instance.close()

        if playwright_instance:
            logger.info("Closing Playwright...")
            await playwright_instance.stop()

    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")

    page = None
    context = None
    browser_instance = None
    playwright_instance = None


async def main():
    """Main function to run the test."""
    channel_name = input("Enter Kick channel name: ")

    try:
        connected = await connect_to_kick_chat(channel_name)
        if connected:
            logger.info(f"Successfully connected to {channel_name}'s chat")
            logger.info("Press Ctrl+C to exit")

            # Keep the script running
            while polling_active:
                await asyncio.sleep(1)
        else:
            logger.error(f"Failed to connect to {channel_name}'s chat")

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, exiting...")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")

    finally:
        await cleanup()


if __name__ == "__main__":
    asyncio.run(main())
