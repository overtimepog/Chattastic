import time
import datetime
import json
import asyncio
import os
from queue import Queue
import config # Assuming you have config.py with KICK_TOKEN_FILE
import globals # Assuming you have globals.py with manager
import logging
import httpx # Using httpx for API calls now

# Set up logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Example basic config
logger = logging.getLogger(__name__)

# Import Playwright’s asynchronous API and stealth module
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from playwright_stealth import stealth_async

# --- Globals ---
# Playwright instances for the persistent browser used for scraping
playwright_instance = None
browser_instance = None
driver_page = None # Renamed from 'driver' to avoid confusion with selenium terminology

# Thread-safe queue and polling control
message_queue = Queue()
last_processed_index = -1
polling_active = False
polling_task = None
streaming_task = None
# --- Globals End ---

def load_kick_tokens():
    """Load Kick authentication tokens from file."""
    if os.path.exists(config.KICK_TOKEN_FILE):
        try:
            with open(config.KICK_TOKEN_FILE, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {config.KICK_TOKEN_FILE}. File might be corrupted.")
            return None
    logger.warning(f"Token file not found at {config.KICK_TOKEN_FILE}")
    return None

# --- API Calls using HTTPX (More Efficient) ---
async def get_kick_channel_id_api(username):
    """Get Kick channel ID using httpx for efficiency."""
    api_url = f"https://kick.com/api/v2/channels/{username}"
    try:
        async with httpx.AsyncClient() as client:
            # Add headers if necessary, e.g., User-Agent
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'}
            response = await client.get(api_url, headers=headers, timeout=10.0)
            response.raise_for_status() # Raise exception for bad status codes
            data = response.json()
            channel_id = data.get("id")
            if not channel_id:
                logger.warning(f"Channel ID not found in API response for username: {username}")
                return None
            logger.info(f"Found channel ID via API for {username}: {channel_id}")
            return str(channel_id)
    except httpx.HTTPStatusError as e:
        # Check for Cloudflare challenge (403 with specific text)
        if e.response.status_code == 403 and "Just a moment..." in e.response.text:
            logger.warning(f"Cloudflare challenge detected for {username}. Waiting 2 seconds...")
            time.sleep(2) # Wait for 2 seconds
        # Log the original error regardless
        logger.error(f"API request failed for {username} with status {e.response.status_code}: {e.response.text[:500]}...") # Log truncated text
        return None
    except httpx.RequestError as e:
        logger.error(f"API request error for {username}: {str(e)}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Failed to parse API JSON response for {username}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting channel ID via API for {username}: {str(e)}")
        return None

async def get_latest_subscriber_api(channel_id):
    """Get the latest Kick subscriber using httpx."""
    api_url = f"https://kick.com/api/v2/channels/{channel_id}/subscribers/last"
    try:
        async with httpx.AsyncClient() as client:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'}
            response = await client.get(api_url, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            if "data" in data:
                return data["data"]
            else:
                logger.warning(f"No subscriber data found in API response for channel: {channel_id}")
                return None
    except httpx.HTTPStatusError as e:
        logger.error(f"API request failed for latest sub (channel {channel_id}) with status {e.response.status_code}: {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"API request error for latest sub (channel {channel_id}): {str(e)}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Failed to parse API JSON response for latest sub (channel {channel_id})")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting latest sub via API (channel {channel_id}): {str(e)}")
        return None
# --- End API Calls ---

def parse_time(time_str):
    """Convert a Kick chat timestamp string (e.g., '08:22 PM') to a more usable format or keep as string."""
    # Kick timestamps are relative to the viewer's timezone and don't include date.
    # For now, just return the string. You could try parsing it if needed, but date info is missing.
    return time_str.strip()

async def wait_for_selector_with_retry(page, selector, max_retries=5, delay=5, timeout_per_try=60000):
    """
    Attempt to wait for a selector with retries and longer timeouts.
    Args:
        page: The Playwright page object.
        selector: The CSS selector to wait for.
        max_retries: Maximum number of attempts.
        delay: Delay in seconds between retries.
        timeout_per_try: Timeout in milliseconds for each attempt.
    Returns:
        The ElementHandle if found.
    Raises:
        PlaywrightTimeoutError: If the selector is not found after all retries.
    """
    attempt = 1
    last_exception = None
    while attempt <= max_retries:
        try:
            logger.info(f"Attempt {attempt}: Waiting for selector '{selector}' with timeout {timeout_per_try}ms...")
            element = await page.wait_for_selector(selector, timeout=timeout_per_try, state="visible")
            logger.info(f"Selector '{selector}' found and visible.")
            return element # Return the handle if successful
        except PlaywrightTimeoutError as e:
            logger.warning(f"Attempt {attempt}: Timeout waiting for selector '{selector}'. Retrying in {delay} seconds...")
            last_exception = e
            await asyncio.sleep(delay)
            attempt += 1
        except PlaywrightError as e: # Catch other potential playwright errors
             logger.error(f"Attempt {attempt}: Playwright error waiting for selector '{selector}': {str(e)}")
             last_exception = e
             # Decide if retry is appropriate for this error, e.g., context closed
             if "closed" in str(e).lower():
                  raise e # Don't retry if context/page is closed
             await asyncio.sleep(delay)
             attempt += 1

    logger.error(f"Failed to locate selector '{selector}' after {max_retries} attempts.")
    raise last_exception or PlaywrightTimeoutError(f"Selector '{selector}' not found after {max_retries} attempts.")


async def poll_messages(channel_name):
    """
    Continuously poll for new chat messages by scraping the channel's page.
    Uses the persistent `driver_page`.
    """
    global last_processed_index, polling_active, driver_page
    if not driver_page or driver_page.is_closed():
        logger.error("Polling cannot start: Playwright page is not initialized or closed.")
        polling_active = False
        return

    logger.info(f"Starting Kick chat DOM polling for channel: {channel_name}")

    # Main polling loop
    while polling_active:
        try:
            if driver_page.is_closed():
                 logger.warning("Polling loop detected page is closed. Stopping.")
                 polling_active = False
                 break

            # More specific selector for messages within the container
            message_selector = "div#chatroom-messages > div.relative > div[data-index]"
            message_elements = await driver_page.query_selector_all(message_selector)

            new_messages_found = False
            max_index_in_batch = last_processed_index

            for element in message_elements:
                index_str = await element.get_attribute("data-index")
                if not index_str: continue
                try:
                    index = int(index_str)
                except ValueError: continue

                if index > last_processed_index:
                    new_messages_found = True
                    max_index_in_batch = max(max_index_in_batch, index) # Track highest index in this batch

                    # --- Extract Message Details ---
                    timestamp_text = "N/A"
                    username_text = "System" # Default for system messages
                    message_text = ""
                    is_reply = False

                    try:
                        # Check if it's a reply message structure first
                        reply_header = await element.query_selector("div.text-white/40")
                        if reply_header:
                            is_reply = True
                            #logger.debug(f"Skipping reply message structure for now (Index: {index})")
                            # If you want to parse replies, add specific logic here
                            # For now, we primarily target non-reply messages

                        # Timestamp (Specific selector)
                        ts_el = await element.query_selector("span.text-neutral.pr-1.font-semibold:not([style*='display: none'])") # Added :not style check just in case
                        if ts_el:
                            timestamp_text = parse_time(await ts_el.inner_text())

                        # Username (Specific selector)
                        usr_el = await element.query_selector(":scope > div.inline-flex button.inline.font-bold") # :scope ensures it's a direct child interaction
                        if usr_el:
                             username_text = (await usr_el.get_attribute("title") or await usr_el.inner_text()).strip() # Use title attr first

                        # Message Content (More specific selector)
                        # This targets the span containing the message, attempting to exclude the timestamp/username parts
                        msg_content_el = await element.query_selector(":scope > span.font-normal.leading-\\[1\\.55\\]")
                        if msg_content_el:
                            # inner_text() is usually good but might include hidden elements or alt text.
                            # evaluate might be more robust if complex HTML/emotes are issues.
                            message_text = await msg_content_el.inner_text()
                            # Basic cleanup (optional)
                            message_text = ' '.join(message_text.split()) # Normalize whitespace

                        # Handle system messages (like BotRix level ups) - often lack user button
                        if username_text == "System" and not msg_content_el:
                             # Maybe the whole message is in a different structure
                             full_msg_text = await element.inner_text()
                             if ":" in full_msg_text: # Basic check
                                  parts = full_msg_text.split(':', 1)
                                  potential_user_part = parts[0].split(']')[-1].strip() # Try to get user after timestamp
                                  if potential_user_part: username_text = potential_user_part
                                  message_text = parts[1].strip()
                             else:
                                  message_text = full_msg_text # Fallback

                        # Filter out empty messages or messages we couldn't parse well
                        if not message_text and username_text == "System":
                             logger.debug(f"Skipping message index {index} - likely unparsed system/event message.")
                             continue # Don't queue empty/system messages we failed to parse

                        # Create and queue the message
                        msg = {
                            "data_index": index,
                            "timestamp": timestamp_text,
                            "sender": username_text,
                            "content": message_text.strip(),
                            "is_reply": is_reply,
                        }
                        message_queue.put(msg)
                        # logger.info(f"Queueing message: Index {index} - {username_text}")


                    except Exception as parse_err:
                        logger.error(f"Error parsing message at index {index}: {str(parse_err)}")
                        # Optionally log the outerHTML of the problematic element for debugging
                        # try:
                        #     outer_html = await element.evaluate("el => el.outerHTML")
                        #     logger.debug(f"Problematic element HTML: {outer_html[:500]}...") # Log first 500 chars
                        # except Exception as html_err:
                        #     logger.error(f"Could not get HTML of problematic element: {html_err}")


            # Update last_processed_index *after* processing the entire batch
            if new_messages_found:
                last_processed_index = max_index_in_batch
                logger.info(f"Processed messages up to index {last_processed_index}")

            # Polling interval
            await asyncio.sleep(0.75) # Slightly longer sleep

        except PlaywrightError as e:
            if "closed" in str(e).lower():
                 logger.error(f"Playwright connection closed during polling: {str(e)}")
                 polling_active = False # Stop polling if the browser/page context is lost
                 break
            else:
                 logger.error(f"Unhandled Playwright error during DOM polling: {str(e)}")
                 await asyncio.sleep(5) # Wait longer after generic errors
        except Exception as e:
            logger.error(f"Generic error during DOM message polling: {str(e)}")
            await asyncio.sleep(5) # Wait longer after generic errors

    logger.info(f"Stopped Kick chat DOM polling for channel: {channel_name}")


async def stream_messages(channel_name):
    """Process messages from the queue and broadcast them."""
    global polling_active
    logger.info(f"Starting Kick chat message streaming for channel: {channel_name}")
    while polling_active or not message_queue.empty(): # Process remaining messages after polling stops
        try:
            if not message_queue.empty():
                msg = message_queue.get()
                # Log the raw message being processed
                # logger.debug(f"Streaming message: {msg}")

                sender = msg.get("sender", "Unknown")
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", "N/A")

                # Basic validation
                if not sender or sender == "System" and not content: # Skip potentially bad parses
                    logger.debug(f"Skipping message streaming for index {msg.get('data_index')} due to missing sender/content.")
                    continue

                message_data = {
                    "type": "kick_chat_message",
                    "data": {
                        "channel": channel_name,
                        "user": sender,
                        "text": content,
                        "timestamp": timestamp
                    }
                }
                await globals.manager.broadcast(json.dumps(message_data))

                # Add to config history (optional)
                # Consider thread safety if config is accessed elsewhere concurrently
                config.kick_chat_messages.append(message_data["data"])
                if len(config.kick_chat_messages) > 100:
                    config.kick_chat_messages = config.kick_chat_messages[-100:]

                message_queue.task_done() # Mark task as done for the queue
            else:
                # If polling stopped and queue is empty, exit
                if not polling_active:
                    break
                await asyncio.sleep(0.2) # Small sleep when queue is empty but polling active
        except Exception as e:
            logger.error(f"Error streaming message: {str(e)}")
            await asyncio.sleep(0.5) # Wait a bit after an error

    logger.info(f"Stopped Kick chat message streaming for channel: {channel_name}")

async def connect_kick_chat(channel_name):
    """Connect to Kick chat: Initialize browser, navigate, and start polling/streaming."""
    global driver_page, browser_instance, playwright_instance, polling_active, last_processed_index
    global polling_task, streaming_task # Keep track of tasks

    if not channel_name or channel_name.isspace():
        logger.warning("Connect Kick chat request missing channel name.")
        await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": "Please enter a Kick channel name."}}))
        return False

    channel_name = channel_name.strip().lower()
    logger.info(f"Attempting to connect to Kick chat for channel: {channel_name}")

    # --- Disconnect if already connected ---
    if config.kick_chat_connected:
        logger.info(f"Disconnecting previous Kick chat ({config.kick_channel_name}) before connecting to {channel_name}.")
        await disconnect_kick_chat()
        await asyncio.sleep(2) # Give ample time for cleanup

    # --- Reset state ---
    last_processed_index = -1
    config.kick_chat_messages.clear()
    while not message_queue.empty():
        try: message_queue.get_nowait()
        except: pass

    # --- Get Channel ID (Using efficient API call) ---
    logger.info(f"Getting channel ID for: {channel_name} via API")
    channel_id = await get_kick_channel_id_api(channel_name)
    if not channel_id:
        logger.warning(f"Could not find Kick channel via API: {channel_name}")
        await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": f"Could not find Kick channel: {channel_name}"}}))
        return False

    # --- Initialize Playwright (Only if not already running) ---
    try:
        if not playwright_instance:
            logger.info("Initializing Playwright...")
            playwright_instance = await async_playwright().start()
        if not browser_instance or not browser_instance.is_connected():
             logger.info("Launching new browser instance...")
             # Consider adding user agent options, proxy, etc. if needed
             browser_instance = await playwright_instance.chromium.launch(
                 headless=True, # Set to False for debugging
                 args=['--no-sandbox', '--disable-setuid-sandbox'] # Common args for docker/linux
             )
        if not driver_page or driver_page.is_closed():
            logger.info("Opening new browser page...")
            driver_page = await browser_instance.new_page()
            logger.info("Applying stealth...")
            await stealth_async(driver_page)

        # --- Navigate and Wait ---
        chat_url = f"https://kick.com/{channel_name}"
        logger.info(f"Navigating to {chat_url}...")
        # Increased navigation timeout
        await driver_page.goto(chat_url, wait_until="load", timeout=90000) # 90 seconds for initial load

        # Wait specifically for the message container, with retries
        logger.info("Waiting for chat messages container to be visible...")
        await wait_for_selector_with_retry(driver_page, "#chatroom-messages", timeout_per_try=60000) # 60s per try
        logger.info("Chat messages container found.")
        # Optionally wait for the input wrapper too, as another sign of readiness
        # await wait_for_selector_with_retry(driver_page, "#chat-input-wrapper", timeout_per_try=30000)
        # logger.info("Chat input wrapper found.")

        # --- Start Polling and Streaming ---
        polling_active = True
        config.kick_channel_id = channel_id
        config.kick_channel_name = channel_name

        logger.info("Creating polling and streaming tasks...")
        polling_task = asyncio.create_task(poll_messages(channel_name))
        streaming_task = asyncio.create_task(stream_messages(channel_name))

        config.kick_chat_connected = True
        config.kick_chat_stream = {"channel_id": channel_id, "channel_name": channel_name}

        await globals.manager.broadcast(json.dumps({"type": "kick_chat_connected", "data": {"channel": channel_name}}))
        logger.info(f"Successfully connected to Kick chat: {channel_name}")
        return True

    except PlaywrightTimeoutError as e:
         logger.error(f"Connection failed: Timeout waiting for critical element on {channel_name}'s page. {e}")
         await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": f"Failed to load Kick channel page for {channel_name} (timeout). Is the channel live or does the page load correctly?"}}))
         await disconnect_kick_chat() # Attempt cleanup
         return False
    except PlaywrightError as e:
         logger.error(f"Connection failed: Playwright error connecting to {channel_name}: {str(e)}")
         await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": f"Playwright error connecting to Kick: {str(e)}"}}))
         await disconnect_kick_chat()
         return False
    except Exception as e:
        logger.exception(f"Unexpected error connecting to Kick chat for {channel_name}: {str(e)}") # Use exception for full traceback
        await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": f"Failed to connect to Kick chat: {str(e)}"}}))
        await disconnect_kick_chat() # Ensure cleanup on any error
        return False

async def disconnect_kick_chat():
    """Disconnect from Kick chat, stop tasks, and clean up Playwright resources."""
    global driver_page, browser_instance, playwright_instance, polling_active
    global polling_task, streaming_task

    if not config.kick_chat_connected and not polling_active:
        logger.info("No active Kick chat connection or tasks to disconnect.")
        # Still attempt cleanup just in case resources linger
    else:
         logger.info(f"Disconnecting from Kick chat: {config.kick_channel_name or 'Unknown'}")

    polling_active = False # Signal loops to stop

    # --- Cancel running tasks ---
    if polling_task and not polling_task.done():
        polling_task.cancel()
        logger.info("Polling task cancellation requested.")
    if streaming_task and not streaming_task.done():
        streaming_task.cancel()
        logger.info("Streaming task cancellation requested.")

    # Wait briefly for tasks to acknowledge cancellation
    await asyncio.sleep(1)

    # --- Cleanup Playwright ---
    # We keep the browser instance alive usually, but close the page
    try:
        if driver_page and not driver_page.is_closed():
            logger.info("Closing Playwright page...")
            await driver_page.close()
            driver_page = None
            logger.info("Playwright page closed.")
        # Decide if you want to close the whole browser on disconnect
        # If you expect frequent connect/disconnect, maybe keep the browser running.
        # If disconnect means the app is stopping or changing focus entirely, close it.
        # Example: Close browser on disconnect
        # if browser_instance and browser_instance.is_connected():
        #     logger.info("Closing Playwright browser...")
        #     await browser_instance.close()
        #     browser_instance = None
        #     logger.info("Playwright browser closed.")
        # if playwright_instance:
        #      logger.info("Stopping Playwright...")
        #      await playwright_instance.stop()
        #      playwright_instance = None
        #      logger.info("Playwright stopped.")

    except Exception as e:
        logger.error(f"Error during Playwright cleanup: {str(e)}")
    finally:
        # Ensure globals are reset even if cleanup fails
        driver_page = None
        # Reset browser/playwright if you decided to close them above
        # browser_instance = None
        # playwright_instance = None

    # --- Reset Config and Globals ---
    disconnected_channel = config.kick_channel_name or "Unknown"
    config.kick_chat_connected = False
    config.kick_chat_stream = None
    config.kick_channel_id = None
    config.kick_channel_name = None
    while not message_queue.empty():
        try: message_queue.get_nowait()
        except: break
    logger.info("Message queue cleared.")

    # --- Notify Clients ---
    try:
        await globals.manager.broadcast(json.dumps({
            "type": "kick_chat_disconnected",
            "data": {"channel": disconnected_channel}
        }))
    except Exception as broadcast_err:
         logger.error(f"Error broadcasting disconnect message: {broadcast_err}")

    logger.info(f"Successfully disconnected from Kick chat: {disconnected_channel}")
    return True

# Example of how you might shut down gracefully on application exit
async def shutdown_playwright():
    global browser_instance, playwright_instance
    logger.info("Shutting down Playwright resources...")
    if browser_instance and browser_instance.is_connected():
        try:
            await browser_instance.close()
            logger.info("Browser instance closed.")
        except Exception as e:
            logger.error(f"Error closing browser instance: {e}")
    if playwright_instance:
         try:
              await playwright_instance.stop()
              logger.info("Playwright instance stopped.")
         except Exception as e:
              logger.error(f"Error stopping playwright instance: {e}")
    browser_instance = None
    playwright_instance = None

# Remember to call shutdown_playwright() when your application exits,
# e.g., using a signal handler or an `atexit` registration.