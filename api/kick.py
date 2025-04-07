import time
import datetime
import json
import asyncio
import os
from queue import Queue
import config
import globals
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Import Playwright’s asynchronous API
from playwright.async_api import async_playwright

# Global variables for Playwright, browser, and page (driver)
playwright_instance = None
browser_instance = None
driver = None  # This will refer to our page object

# Thread-safe queue and other globals
message_queue = Queue()
last_processed_time = None
polling_active = False  # When True, polling loop runs

def load_kick_tokens():
    """Load Kick authentication tokens from file."""
    if os.path.exists(config.KICK_TOKEN_FILE):
        try:
            with open(config.KICK_TOKEN_FILE, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {config.KICK_TOKEN_FILE}. File might be corrupted.")
            return None
    return None

async def get_kick_channel_id(username, access_token=None):
    """Get Kick channel ID from username using headless browser with Playwright (async)."""
    global playwright_instance, browser_instance
    try:
        playwright_instance = await async_playwright().start()
        browser_instance = await playwright_instance.chromium.launch()
        page = await browser_instance.new_page()
        await page.goto(f"https://kick.com/api/v2/channels/{username}", wait_until="load")
        # Ensure the body is loaded; Playwright waits for load automatically,
        # but we explicitly wait for the "body" selector.
        await page.wait_for_selector("body")
        body_text = await page.inner_text("body")
        if not body_text:
            logger.warning(f"No response body found for username: {username}")
            return None
        else:
            print("BODY: ", body_text)
        try:
            data = json.loads(body_text)
            print("DATA: ", data)
            channel_id = data.get("id")
            if not channel_id:
                logger.warning(f"Channel ID not found for username: {username}")
                return None
            logger.info(f"Found channel ID for {username}: {channel_id}")
            return str(channel_id)
        except json.JSONDecodeError:
            logger.error("Failed to parse channel data JSON")
            return None
    except Exception as e:
        logger.error(f"Error getting channel ID: {str(e)}")
        return None
    finally:
        # Clean up the temporary browser instance
        if browser_instance:
            await browser_instance.close()
        if playwright_instance:
            await playwright_instance.stop()

async def get_latest_subscriber(channel_id):
    """Get the latest Kick subscriber for a channel using Playwright (async)."""
    global playwright_instance, browser_instance
    try:
        playwright_instance = await async_playwright().start()
        browser_instance = await playwright_instance.chromium.launch(headless=True)
        page = await browser_instance.new_page()
        await page.goto(f"https://kick.com/api/v2/channels/{channel_id}/subscribers/last", wait_until="load")
        await page.wait_for_selector("body")
        body_text = await page.inner_text("body")
        data = json.loads(body_text)
        if "data" in data:
            return data["data"]
        else:
            logger.warning(f"No subscriber data found for channel: {channel_id}")
            return None
    except Exception as e:
        logger.error(f"Error getting latest subscriber: {str(e)}")
        return None
    finally:
        if browser_instance:
            await browser_instance.close()
        if playwright_instance:
            await playwright_instance.stop()

def parse_time(time_str):
    """Convert an ISO8601 string to a datetime object."""
    try:
        return datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        logger.error(f"Time parsing error: {str(e)}")
        return None

async def poll_messages(channel_id, channel_name):
    """Continuously poll for new messages in the Kick chat using Playwright (async version)."""
    global last_processed_time, polling_active, driver

    logger.info(f"Starting Kick chat polling for channel: {channel_name} (ID: {channel_id})")

    messages_url = f"https://kick.com/api/v2/channels/{channel_id}/messages"

    # Initial load to set baseline timestamp
    try:
        await driver.goto(messages_url, wait_until="load")
        await driver.wait_for_selector("body")
        await asyncio.sleep(1)
        body_text = await driver.inner_text("body")
        data = json.loads(body_text)
        messages = data.get("data", {}).get("messages", [])
        if messages:
            messages.sort(key=lambda m: parse_time(m.get("created_at", "")))
            last_processed_time = parse_time(messages[-1].get("created_at", ""))
        else:
            last_processed_time = datetime.datetime.utcnow()
        logger.info(f"Baseline timestamp set to: {last_processed_time}")
    except Exception as e:
        logger.error(f"Error during initial chat load: {str(e)}")
        last_processed_time = datetime.datetime.utcnow()

    # Polling loop
    while polling_active:
        try:
            await driver.goto(messages_url, wait_until="load")
            await driver.wait_for_selector("body")
            await asyncio.sleep(0.5)
            body_text = await driver.inner_text("body")
            data = json.loads(body_text)
            messages = data.get("data", {}).get("messages", [])
            if not messages:
                await asyncio.sleep(1)
                continue
            messages.sort(key=lambda m: parse_time(m.get("created_at", "")))
            new_messages = []
            for msg in messages:
                msg_time = parse_time(msg.get("created_at", ""))
                if msg_time and (last_processed_time is None or msg_time > last_processed_time):
                    new_messages.append(msg)
            if new_messages:
                last_processed_time = parse_time(new_messages[-1].get("created_at", ""))
                for msg in new_messages:
                    message_queue.put(msg)
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error during message polling: {str(e)}")
            await asyncio.sleep(2)
    logger.info(f"Stopped Kick chat polling for channel: {channel_name}")

async def stream_messages(channel_name):
    """Process messages from the queue and broadcast them to clients."""
    global polling_active
    logger.info(f"Starting Kick chat message streaming for channel: {channel_name}")
    while polling_active:
        try:
            if not message_queue.empty():
                msg = message_queue.get()
                sender = msg.get("sender", {}).get("username", "Unknown")
                content = msg.get("content", "")
                created_at = msg.get("created_at", "")
                message_data = {
                    "type": "kick_chat_message",
                    "data": {
                        "channel": channel_name,
                        "user": sender,
                        "text": content,
                        "timestamp": created_at
                    }
                }
                await globals.manager.broadcast(json.dumps(message_data))
                config.kick_chat_messages.append(message_data["data"])
                if len(config.kick_chat_messages) > 100:
                    config.kick_chat_messages = config.kick_chat_messages[-100:]
                await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"Error streaming message: {str(e)}")
            await asyncio.sleep(0.5)
    logger.info(f"Stopped Kick chat message streaming for channel: {channel_name}")

async def connect_kick_chat(channel_name):
    """Connect to Kick chat for the specified channel using Playwright (async)."""
    global driver, browser_instance, playwright_instance, polling_active
    if not channel_name or channel_name.isspace():
        logger.warning("Connect Kick chat request missing channel name.")
        await globals.manager.broadcast(json.dumps({
            "type": "error",
            "data": {"message": "Please enter a Kick channel name to connect."}
        }))
        return False

    channel_name = channel_name.strip().lower()

    if config.kick_chat_connected:
        logger.warning(f"Already connected to Kick chat: {config.kick_channel_name}")
        await globals.manager.broadcast(json.dumps({
            "type": "info",
            "data": {"message": f"Already connected to Kick chat: {config.kick_channel_name}"}
        }))
        return False

    tokens = load_kick_tokens()
    if not tokens or 'access_token' not in tokens:
        logger.warning("Kick authentication tokens are missing or invalid.")
        await globals.manager.broadcast(json.dumps({
            "type": "error",
            "data": {"message": "Please authenticate with Kick first."}
        }))
        return False

    logger.info(f"Getting channel ID for: {channel_name}")
    channel_id = await get_kick_channel_id(channel_name, tokens.get('access_token'))
    if not channel_id:
        logger.warning(f"Could not find Kick channel: {channel_name}")
        await globals.manager.broadcast(json.dumps({
            "type": "error",
            "data": {"message": f"Could not find Kick channel: {channel_name}"}
        }))
        return False

    try:
        # Initialize persistent Playwright browser and page for ongoing polling
        playwright_instance = await async_playwright().start()
        browser_instance = await playwright_instance.chromium.launch(headless=True)
        driver = await browser_instance.new_page()

        polling_active = True
        config.kick_channel_id = channel_id
        config.kick_channel_name = channel_name

        # Create asyncio tasks for polling and streaming concurrently
        asyncio.create_task(poll_messages(channel_id, channel_name))
        asyncio.create_task(stream_messages(channel_name))

        config.kick_chat_connected = True
        config.kick_chat_stream = {"channel_id": channel_id, "channel_name": channel_name}

        await globals.manager.broadcast(json.dumps({
            "type": "kick_chat_connected",
            "data": {"channel": channel_name}
        }))
        logger.info(f"Successfully connected to Kick chat: {channel_name}")
        return True
    except Exception as e:
        logger.error(f"Error connecting to Kick chat: {str(e)}")
        await globals.manager.broadcast(json.dumps({
            "type": "error",
            "data": {"message": f"Failed to connect to Kick chat: {str(e)}"}
        }))
        await disconnect_kick_chat()
        return False

async def disconnect_kick_chat():
    """Disconnect from Kick chat, shutting down the Playwright browser (async)."""
    global driver, browser_instance, playwright_instance, polling_active
    if not config.kick_chat_connected:
        logger.info("No active Kick chat connection to disconnect.")
        return True

    logger.info(f"Disconnecting from Kick chat: {config.kick_channel_name}")
    polling_active = False  # This will stop the polling and streaming loops

    try:
        if driver:
            await driver.close()
        if browser_instance:
            await browser_instance.close()
        if playwright_instance:
            await playwright_instance.stop()
    except Exception as e:
        logger.error(f"Error closing browser: {str(e)}")

    config.kick_chat_connected = False
    config.kick_chat_stream = None

    while not message_queue.empty():
        message_queue.get()

    await globals.manager.broadcast(json.dumps({
        "type": "kick_chat_disconnected",
        "data": {"channel": config.kick_channel_name}
    }))

    config.kick_channel_id = None
    config.kick_channel_name = None
    logger.info("Successfully disconnected from Kick chat")
    return True
