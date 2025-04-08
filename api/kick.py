import time
import datetime
import json
import asyncio
import os
from queue import Queue
# Assuming config.py and globals.py exist and are configured
import config
import globals # Import globals to access kick_emotes
import logging

# Set up logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Example basic config
logger = logging.getLogger(__name__)

# Import Playwright’s asynchronous API and stealth module
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from playwright_stealth import stealth_async

# --- Globals ---
# Persistent Playwright instances for scraping the live chat DOM
playwright_instance_persistent = None
browser_instance_persistent = None
driver_page = None # Page object for ongoing chat polling

# Thread-safe queue and polling control
message_queue = Queue()
last_processed_index = -1
polling_active = False
polling_task = None
streaming_task = None
# --- Globals End ---

def load_kick_tokens():
    """Load Kick authentication tokens from file."""
    token_path = getattr(config, 'KICK_TOKEN_FILE', 'kick_tokens.json') # Use default if not in config
    if os.path.exists(token_path):
        try:
            with open(token_path, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {token_path}. File might be corrupted.")
            return None
    logger.warning(f"Token file not found at {token_path}")
    return None

# --- Playwright-based API Calls (Necessary due to Cloudflare) ---

async def get_all_username_emotes(username):
    """
    Download all emote images for a given username from Kick using only Playwright and Playwright stealth.
    
    Steps:
      1. Navigate to https://kick.com/emotes/{username} and extract JSON data.
      2. For every emote in the JSON, construct the image URL.
      3. Use Playwright’s request API to fetch the image and save it in a folder named "emote_cache/{username}_emotes".
      4. Populate globals.kick_emotes with {"emoteName": "/emotes/{username}_emotes/filename.jpg"}
    """
    logger.info(f"Starting to get emotes for username: {username}")

    # Clear previous emotes for this user from the global dict
    # This assumes emotes are user-specific and we want fresh data
    # A more complex approach might merge or only update, but clearing is simpler for now.
    # We need to iterate and remove keys associated with this user's path prefix.
    emote_path_prefix = f"/emotes/{username}_emotes/"
    keys_to_remove = [k for k, v in globals.kick_emotes.items() if v.startswith(emote_path_prefix)]
    for key in keys_to_remove:
        del globals.kick_emotes[key]
    logger.info(f"Cleared previous emotes for {username} from globals.kick_emotes")

    temp_playwright = None
    temp_browser = None
    temp_page = None
    try:
        # Start a temporary Playwright instance
        temp_playwright = await async_playwright().start()
        temp_browser = await temp_playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        temp_page = await temp_browser.new_page()
        
        # Apply stealth to the page before navigation
        await stealth_async(temp_page)
        
        # Navigate to the emotes page
        emotes_url = f"https://kick.com/emotes/{username}"
        logger.info(f"Navigating to {emotes_url}")
        await temp_page.goto(emotes_url, wait_until="load", timeout=60000)
        await temp_page.wait_for_timeout(5000)  # Wait a bit for any JS processing
        
        # Extract the JSON response from the body text
        body_text = await temp_page.inner_text("body")
        try:
            data = json.loads(body_text)
        except json.JSONDecodeError as json_err:
            logger.error(f"JSON decoding failed for {username} emotes page: {json_err}")
            return None

        # Define base cache directory and user-specific directory
        base_emote_dir = "emote_cache"
        download_dir = os.path.join(base_emote_dir, f"{username}_emotes")
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
            logger.info(f"Created directory '{download_dir}' for saving emotes.")
        else:
            logger.info(f"Using existing directory '{download_dir}' for saving emotes.")

        # For each entry containing an "emotes" key, fetch and save the image
        emotes_found_count = 0
        for entry in data:
            if "emotes" in entry:
                for emote in entry["emotes"]:
                    emote_id = emote.get("id")
                    emote_name = emote.get("name") # Get the actual name
                    if not emote_id or not emote_name:
                        logger.warning(f"Skipping emote due to missing ID or name: {emote}")
                        continue
                    # Construct the fullsize image URL
                    image_url = f"https://files.kick.com/emotes/{emote_id}/fullsize"
                    logger.info(f"Downloading emote '{emote_name}' from {image_url}")
                    try:
                        # Use Playwright's request API to fetch the image
                        response = await temp_page.request.get(image_url)
                        if response.ok:
                            image_bytes = await response.body()
                            # Determine file extension (basic check, could be improved)
                            content_type = response.headers.get('content-type', '').lower()
                            if 'image/png' in content_type:
                                file_ext = ".png"
                            elif 'image/gif' in content_type:
                                file_ext = ".gif"
                            else: # Default to jpg
                                file_ext = ".jpg"

                            # Use the actual emote name for the filename, sanitized
                            safe_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in emote_name).strip()
                            file_name = f"{safe_name}{file_ext}"
                            file_path = os.path.join(download_dir, file_name)

                            with open(file_path, "wb") as f:
                                f.write(image_bytes)
                            logger.info(f"Saved emote '{emote_name}' image to {file_path}")

                            # Store the mapping in globals using the web-accessible path
                            web_path = f"/emotes/{username}_emotes/{file_name}"
                            globals.kick_emotes[emote_name] = web_path
                            emotes_found_count += 1
                        else:
                            logger.error(f"Failed to download image for emote '{emote_name}'. HTTP status: {response.status}")
                    except Exception as download_err:
                        logger.error(f"Error downloading or saving emote '{emote_name}': {str(download_err)}")

        logger.info(f"Finished downloading {emotes_found_count} emotes for username: {username}")
        logger.debug(f"Current globals.kick_emotes: {globals.kick_emotes}") # Log the result for debugging
        return True

    except PlaywrightTimeoutError as e:
        logger.error(f"Timeout while loading emotes page for {username}: {str(e)}")
    except PlaywrightError as e:
        logger.error(f"Playwright error while getting emotes for {username}: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error in get_all_username_emotes for {username}: {str(e)}")
    finally:
        # Clean up temporary Playwright resources
        if temp_page:
            try:
                await temp_page.close()
            except Exception as e_pg:
                logger.debug(f"Error closing temporary page: {e_pg}")
        if temp_browser:
            try:
                await temp_browser.close()
            except Exception as e_br:
                logger.debug(f"Error closing temporary browser: {e_br}")
        if temp_playwright:
            try:
                await temp_playwright.stop()
            except Exception as e_pw:
                logger.debug(f"Error stopping temporary playwright instance: {e_pw}")
    return None

    
async def get_kick_channel_id(username):
    """Get Kick channel ID using a TEMPORARY Playwright instance with stealth to handle Cloudflare."""
    logger.info(f"Attempting to get channel ID for '{username}' using Playwright + Stealth...")
    temp_playwright = None
    temp_browser = None
    temp_page = None
    api_url = f"https://kick.com/api/v2/channels/{username}"

    try:
        temp_playwright = await async_playwright().start()
        # Launch temporary browser for this specific task
        temp_browser = await temp_playwright.chromium.launch(
             headless=True, # Keep headless unless debugging
             args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        temp_page = await temp_browser.new_page()

        # *** Apply stealth BEFORE navigation ***
        await stealth_async(temp_page)
        logger.info(f"Stealth applied to temporary page for {username} ID lookup.")

        await temp_page.goto(api_url, wait_until="load", timeout=60000) # 60s timeout for navigation

        # Wait needed for potential Cloudflare JS execution or redirects
        await temp_page.wait_for_timeout(5000) # Wait 5 seconds for JS challenges

        # Check final URL in case of redirects
        final_url = temp_page.url
        if final_url != api_url and "challenges.cloudflare.com" in final_url:
             logger.error(f"Cloudflare challenge persisted for {username} at {api_url}. Failed to bypass.")
             return None

        # Attempt to get page content
        content = await temp_page.content() # Get full HTML/content

        # Look for JSON within the content (sometimes it's in <pre> or body directly)
        body_text = await temp_page.inner_text("body") # More reliable for API endpoints
        if not body_text:
             logger.warning(f"No response body content found for username: {username} at {api_url}")
             # Log content for debugging if needed
             # logger.debug(f"Full page content for {username}:\n{content[:500]}...")
             return None

        # Check if it's the Cloudflare challenge page HTML
        if "<title>Just a moment...</title>" in content or "challenges.cloudflare.com" in content:
            logger.warning(f"Cloudflare challenge detected for {username} at {api_url} even after stealth.")
            # Optionally add more sophisticated waiting/interaction here if needed
            return None

        logger.debug(f"Raw body text for {username} channel ID: {body_text[:200]}...") # Log beginning of response

        try:
            data = json.loads(body_text)
            channel_id = data.get("id")
            if not channel_id:
             logger.warning(f"Channel ID key 'id' not found in JSON for username: {username}. Data: {data}")
             return None
            logger.info(f"Found channel ID via Playwright for {username}: {channel_id}")
            return str(channel_id)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from response body for {username}. Body was: {body_text[:500]}...")
            return None

    except PlaywrightTimeoutError as e:
        logger.error(f"Playwright timeout getting channel ID for {username}: {str(e)}")
        return None
    except PlaywrightError as e:
        logger.error(f"Playwright error getting channel ID for {username}: {str(e)}")
        if "Target closed" in str(e):
            logger.error("Browser context might have been closed unexpectedly.")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting channel ID for {username}: {str(e)}") # Use exception for traceback
        return None
    finally:
        # *** Ensure temporary resources are closed ***
        if temp_page:
            try: await temp_page.close()
            except Exception as e_pg: logger.debug(f"Minor error closing temp page: {e_pg}")
        if temp_browser:
            try: await temp_browser.close()
            except Exception as e_br: logger.debug(f"Minor error closing temp browser: {e_br}")
        if temp_playwright: # Only stop if we started it here (should always be true in this func)
             try: await temp_playwright.stop()
             except Exception as e_pw: logger.debug(f"Minor error stopping temp playwright: {e_pw}")


async def get_latest_subscriber(channel_id):
    """Get the latest Kick subscriber using a TEMPORARY Playwright instance with stealth."""
    logger.info(f"Attempting to get latest subscriber for channel ID {channel_id} using Playwright + Stealth...")
    temp_playwright = None
    temp_browser = None
    temp_page = None
    api_url = f"https://kick.com/api/v2/channels/{channel_id}/subscribers/last"

    try:
        temp_playwright = await async_playwright().start()
        temp_browser = await temp_playwright.chromium.launch(
             headless=True,
             args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        temp_page = await temp_browser.new_page()
        await stealth_async(temp_page) # Apply stealth before navigating
        logger.info(f"Stealth applied to temporary page for latest subscriber lookup (Channel {channel_id}).")

        await temp_page.goto(api_url, wait_until="load", timeout=60000)
        await temp_page.wait_for_timeout(3000) # Short wait for potential JS

        content = await temp_page.content()
        if "<title>Just a moment...</title>" in content or "challenges.cloudflare.com" in content:
            logger.warning(f"Cloudflare challenge detected for latest subscriber API (Channel {channel_id}).")
            return None

        body_text = await temp_page.inner_text("body")
        if not body_text:
             logger.warning(f"No response body content found for latest subscriber API (Channel {channel_id})")
             return None

        try:
            data = json.loads(body_text)
            if "data" in data and data["data"]: # Check if data exists and is not empty/null
                logger.info(f"Found latest subscriber data for channel {channel_id}")
                return data["data"]
            else:
             logger.warning(f"No subscriber 'data' key found in JSON response for channel: {channel_id}. Data: {data}")
             return None
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON for latest subscriber (Channel {channel_id}). Body was: {body_text[:500]}...")
            return None

    except PlaywrightTimeoutError as e:
        logger.error(f"Playwright timeout getting latest subscriber for {channel_id}: {str(e)}")
        return None
    except PlaywrightError as e:
        logger.error(f"Playwright error getting latest subscriber for {channel_id}: {str(e)}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting latest subscriber for {channel_id}: {str(e)}")
        return None
    finally:
        # Ensure temporary resources are closed
        if temp_page:
            try: await temp_page.close()
            except Exception as e_pg: logger.debug(f"Minor error closing temp page: {e_pg}")
        if temp_browser:
            try: await temp_browser.close()
            except Exception as e_br: logger.debug(f"Minor error closing temp browser: {e_br}")
        if temp_playwright:
            try: await temp_playwright.stop()
            except Exception as e_pw: logger.debug(f"Minor error stopping temp playwright: {e_pw}")
# --- End Playwright-based API Calls ---


def parse_kick_timestamp(time_str):
    """Placeholder for parsing Kick's chat timestamp (e.g., '08:22 PM') if needed."""
    return time_str.strip() # Currently returns as string


async def wait_for_selector_with_retry(page, selector, max_retries=5, delay=5, timeout_per_try=60000):
    """Attempts to wait for a selector with retries and longer timeouts."""
    # (Implementation remains the same as the previous good version)
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
             if "closed" in str(e).lower(): raise e # Don't retry if context/page is closed
             await asyncio.sleep(delay)
             attempt += 1

    logger.error(f"Failed to locate selector '{selector}' after {max_retries} attempts.")
    raise last_exception or PlaywrightTimeoutError(f"Selector '{selector}' not found after {max_retries} attempts.")


async def poll_messages(channel_name):
    """Continuously poll for new chat messages using the persistent driver_page."""
    # (Implementation remains largely the same as the previous good version,
    # ensure selectors match the target HTML structure)
    global last_processed_index, polling_active, driver_page
    if not driver_page or driver_page.is_closed():
        logger.error("Polling cannot start: Persistent Playwright page is not initialized or closed.")
        polling_active = False
        return

    logger.info(f"Starting Kick chat DOM polling for channel: {channel_name}")
    message_selector = "div#chatroom-messages > div.relative > div[data-index]" # Selector for message wrappers

    while polling_active:
        try:
            if driver_page.is_closed():
                 logger.warning("Polling loop detected page is closed. Stopping.")
                 polling_active = False
                 break

            message_elements = await driver_page.query_selector_all(message_selector)
            if not message_elements:
                # logger.debug("No message elements found in current poll cycle.")
                await asyncio.sleep(1) # Wait a bit longer if nothing is found
                continue

            new_messages_found_in_batch = False
            max_index_in_batch = last_processed_index

            for element in message_elements:
                index_str = await element.get_attribute("data-index")
                if not index_str: continue
                try:
                    index = int(index_str)
                except ValueError: continue

                if index > last_processed_index:
                    new_messages_found_in_batch = True
                    max_index_in_batch = max(max_index_in_batch, index)

                    timestamp_text = "N/A"
                    username_text = "System"
                    message_text = ""
                    is_reply = False

                    try:
                        # Check for reply structure
                        reply_header = await element.query_selector(":scope > div.text-white\\/40") # Need to escape slash for CSS
                        if reply_header:
                            is_reply = True
                            # logger.debug(f"Parsing reply structure for index {index}")
                            # Timestamp in replies might be nested differently or absent, adjust if needed
                            ts_el = await element.query_selector(":scope > div > span.text-neutral.pr-1.font-semibold")
                            if ts_el: timestamp_text = parse_kick_timestamp(await ts_el.inner_text())

                            # User in replies is often inside the main div -> inline-flex -> button
                            usr_el = await element.query_selector(":scope > div > div.inline-flex button.inline.font-bold")
                            if usr_el: username_text = (await usr_el.get_attribute("title") or await usr_el.inner_text()).strip()

                            # Message content in replies is often the last direct span child of the main div
                            msg_content_el = await element.query_selector(":scope > div > span.font-normal.leading-\\[1\\.55\\]")
                            if msg_content_el: message_text = await msg_content_el.inner_text()

                        else: # Standard message structure
                            # Timestamp
                            ts_el = await element.query_selector(":scope > span.text-neutral.pr-1.font-semibold")
                            if ts_el: timestamp_text = parse_kick_timestamp(await ts_el.inner_text())

                            # Username
                            usr_el = await element.query_selector(":scope > div.inline-flex button.inline.font-bold")
                            if usr_el: username_text = (await usr_el.get_attribute("title") or await usr_el.inner_text()).strip()
                            elif await element.query_selector(":scope > div.inline-flex button[title='BotRix']"): # Specific case for BotRix
                                 username_text = "BotRix"


                            # Message Content
                            msg_content_el = await element.query_selector(":scope > span.font-normal.leading-\\[1\\.55\\]")
                            if msg_content_el:
                                message_text = await msg_content_el.inner_text()
                                # Attempt to extract text from emotes' alt attributes if inner_text is empty/just whitespace
                                if not message_text.strip():
                                     emote_texts = []
                                     emote_imgs = await msg_content_el.query_selector_all("img[alt]")
                                     for img in emote_imgs:
                                          alt_text = await img.get_attribute("alt")
                                          if alt_text: emote_texts.append(f":{alt_text}:") # Format like :emoteName:
                                     message_text = " ".join(emote_texts)


                        # Final check for system-like messages we couldn't parse
                        if username_text == "System" and not message_text:
                             full_msg_text = await element.inner_text()
                             if ":" in full_msg_text:
                                  parts = full_msg_text.split(':', 1)
                                  potential_user_part = parts[0].split(']')[-1].strip()
                                  if potential_user_part: username_text = potential_user_part
                                  message_text = parts[1].strip()
                             else:
                                  message_text = " ".join(full_msg_text.split()) # Use cleaned full text
                             logger.debug(f"Using fallback parsing for index {index}, User: {username_text}, Msg: {message_text[:50]}...")

                        # --- Queue the message ---
                        if username_text and (message_text or username_text != "System"): # Ensure we have something meaningful
                            msg = {
                                "data_index": index,
                                "timestamp": timestamp_text,
                                "sender": username_text,
                                "content": message_text.strip(),
                                "is_reply": is_reply,
                            }
                            message_queue.put(msg)
                        else:
                             logger.debug(f"Skipping queuing message index {index} due to missing sender/content after parsing.")

                    except Exception as parse_err:
                        logger.error(f"Error parsing message details at index {index}: {str(parse_err)}")
                        try:
                            outer_html = await element.evaluate("el => el.outerHTML")
                            logger.debug(f"Problematic element HTML for index {index}: {outer_html[:500]}...")
                        except Exception as html_err:
                             logger.error(f"Could not get HTML of problematic element index {index}: {html_err}")

            # Update index after processing batch
            if new_messages_found_in_batch:
                last_processed_index = max_index_in_batch
                logger.info(f"Processed DOM messages up to index {last_processed_index}")

            await asyncio.sleep(0.8) # Polling interval

        except PlaywrightError as e:
            if "closed" in str(e).lower() or "browser has been closed" in str(e):
                 logger.error(f"Persistent Playwright connection closed during polling: {str(e)}")
                 polling_active = False
                 break
            else:
                 logger.error(f"Unhandled Playwright error during DOM polling: {str(e)}")
                 await asyncio.sleep(5)
        except Exception as e:
            logger.exception(f"Generic error during DOM message polling loop: {str(e)}") # Use exception for traceback
            await asyncio.sleep(5)

    logger.info(f"Stopped Kick chat DOM polling for channel: {channel_name}")


async def stream_messages(channel_name):
    """Process messages from the queue and broadcast them."""
    # (Implementation remains the same as the previous good version)
    global polling_active
    logger.info(f"Starting Kick chat message streaming for channel: {channel_name}")
    while polling_active or not message_queue.empty(): # Process remaining messages after polling stops
        try:
            if not message_queue.empty():
                msg = message_queue.get()

                sender = msg.get("sender", "Unknown")
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", "N/A")

                if not sender or (sender == "System" and not content):
                    logger.debug(f"Skipping streaming message index {msg.get('data_index')} due to missing sender/content.")
                    message_queue.task_done()
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
                # Broadcast for main UI
                await globals.manager.broadcast(json.dumps(message_data))

                # Add to config history (ensure thread safety if needed)
                config.kick_chat_messages.append(message_data["data"]) # Keep original data for history
                if len(config.kick_chat_messages) > 100:
                    config.kick_chat_messages = config.kick_chat_messages[-100:]

                message_queue.task_done()
            else:
                if not polling_active: break # Exit if polling stopped and queue empty
                await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"Error streaming message: {str(e)}")
            await asyncio.sleep(0.5)

    logger.info(f"Stopped Kick chat message streaming for channel: {channel_name}")


async def connect_kick_chat(channel_name):
    """Connect to Kick chat: Get ID (via Playwright), init persistent browser, start polling."""
    global driver_page, browser_instance_persistent, playwright_instance_persistent
    global polling_active, last_processed_index, polling_task, streaming_task

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
        await asyncio.sleep(2)

    # --- Reset state ---
    last_processed_index = -1
    config.kick_chat_messages.clear()
    while not message_queue.empty():
        try: message_queue.get_nowait()
        except: pass

    # --- Get Channel ID (Using Playwright due to Cloudflare) ---
    logger.info(f"Getting channel ID for: {channel_name} using Playwright...")
    # Tokens not strictly needed for this endpoint usually, but passing anyway
    tokens = load_kick_tokens()
    channel_id = await get_kick_channel_id(channel_name) # Uses the Playwright version now
    if not channel_id:
        logger.error(f"Could not get Kick channel ID via Playwright for: {channel_name}")
        await globals.manager.broadcast(json.dumps({
            "type": "error",
            "data": {"message": f"Could not find Kick channel or bypass protection for: {channel_name}"}
        }))
        return False # Corrected indentation

    # --- Download Emotes for the Channel ---
    logger.info(f"Attempting to download emotes for channel: {channel_name}")
    emotes_downloaded = await get_all_username_emotes(channel_name)
    if emotes_downloaded:
        logger.info(f"Successfully initiated emote download process for {channel_name}.")
    else:
        logger.warning(f"Failed to download emotes for {channel_name}. Proceeding without custom emotes.")
     # Note: We proceed even if emotes fail, chat should still work.

    # --- Initialize PERSISTENT Playwright for scraping (if needed) ---
    # Corrected indentation for the entire try block below
    try:
        if not playwright_instance_persistent:
            logger.info("Initializing Persistent Playwright...")
            playwright_instance_persistent = await async_playwright().start()

        if not browser_instance_persistent or not browser_instance_persistent.is_connected():
            logger.info("Launching Persistent Browser Instance...")
            browser_instance_persistent = await playwright_instance_persistent.chromium.launch(
                headless=True, # Or False for debugging
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            # Optional: Add listener for disconnect
            browser_instance_persistent.on("disconnected", lambda: logger.warning("Persistent browser disconnected!"))


        if not driver_page or driver_page.is_closed():
            logger.info("Opening Persistent Browser Page...")
            # Create a new context potentially, for better isolation if needed
            # context = await browser_instance_persistent.new_context()
            # driver_page = await context.new_page()
            driver_page = await browser_instance_persistent.new_page()
            logger.info("Applying stealth to Persistent Page...")
            await stealth_async(driver_page)
            driver_page.on("close", lambda: logger.warning("Persistent driver page was closed!")) # Log if page closes unexpectedly


        # --- Navigate Persistent Page and Wait ---
        chat_url = f"https://kick.com/{channel_name}"
        logger.info(f"Navigating Persistent Page to {chat_url}...")
        await driver_page.goto(chat_url, wait_until="load", timeout=90000)

        logger.info("Waiting for chat messages container (#chatroom-messages)...")
        await wait_for_selector_with_retry(driver_page, "#chatroom-messages", timeout_per_try=60000)
        logger.info("Chat messages container found on Persistent Page.")

        # --- Start Polling and Streaming Tasks ---
        polling_active = True
        config.kick_channel_id = channel_id
        config.kick_channel_name = channel_name

        logger.info("Creating polling and streaming tasks...")
        # Ensure previous tasks are properly handled if reconnecting quickly
        if polling_task and not polling_task.done(): polling_task.cancel()
        if streaming_task and not streaming_task.done(): streaming_task.cancel()

        polling_task = asyncio.create_task(poll_messages(channel_name))
        streaming_task = asyncio.create_task(stream_messages(channel_name))

        config.kick_chat_connected = True
        config.kick_chat_stream = {"channel_id": channel_id, "channel_name": channel_name}

        await globals.manager.broadcast(json.dumps({"type": "kick_chat_connected", "data": {"channel": channel_name}}))
        logger.info(f"Successfully connected to Kick chat: {channel_name}")
        return True

    except PlaywrightTimeoutError as e:
        logger.error(f"Connection failed: Timeout waiting for critical element on {channel_name}'s page (Persistent Browser). {e}")
        await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": f"Failed to load Kick channel page for {channel_name} (timeout). Is the channel live?"}}))
        await disconnect_kick_chat() # Clean up on failure
        return False
    except PlaywrightError as e:
        logger.error(f"Connection failed: Playwright error preparing persistent browser for {channel_name}: {str(e)}")
        await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": f"Playwright error connecting to Kick: {str(e)}"}}))
        await disconnect_kick_chat() # Clean up on failure
        return False
    except Exception as e:
        logger.exception(f"Unexpected error during persistent browser setup for {channel_name}: {str(e)}")
        await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": f"Failed to connect to Kick chat: {str(e)}"}}))
        await disconnect_kick_chat() # Clean up on failure
        return False


async def disconnect_kick_chat():
    """Disconnect from Kick chat, stop tasks, and clean up persistent Playwright page."""
    global driver_page, polling_active, polling_task, streaming_task
    # Note: We typically keep the persistent browser and playwright instance running unless the app shuts down.

    if not config.kick_chat_connected and not polling_active:
        logger.info("No active Kick chat connection or tasks to disconnect.")
    else:
        logger.info(f"Disconnecting from Kick chat: {config.kick_channel_name or 'Unknown'}")

    polling_active = False # Signal loops to stop

    # Cancel running tasks
    if polling_task and not polling_task.done():
        polling_task.cancel()
        logger.info("Polling task cancellation requested.")
    if streaming_task and not streaming_task.done():
        streaming_task.cancel()
        logger.info("Streaming task cancellation requested.")

    # Wait briefly for tasks
    await asyncio.sleep(0.5)

    # Close the specific page used for polling, but keep the browser alive
    try:
        if driver_page and not driver_page.is_closed():
            logger.info("Closing persistent Playwright page...")
            await driver_page.close()
            logger.info("Persistent Playwright page closed.")
    except Exception as e:
        logger.error(f"Error closing persistent driver page: {str(e)}")
    finally:
        driver_page = None # Ensure it's marked as closed

    # Reset Config and Globals
    disconnected_channel = config.kick_channel_name or "Unknown"
    config.kick_chat_connected = False
    config.kick_chat_stream = None
    config.kick_channel_id = None
    config.kick_channel_name = None
    last_processed_index = -1
    polling_task = None
    streaming_task = None

    # Clear message queue
    while not message_queue.empty():
        try: message_queue.get_nowait()
        except: break
    logger.info("Message queue cleared.")

    # Notify Clients
    try:
        await globals.manager.broadcast(json.dumps({
            "type": "kick_chat_disconnected",
            "data": {"channel": disconnected_channel}
        }))
    except Exception as broadcast_err:
         logger.error(f"Error broadcasting disconnect message: {broadcast_err}")

    logger.info(f"Successfully disconnected from Kick chat: {disconnected_channel}")
    return True


async def shutdown_playwright():
    """Gracefully close persistent Playwright browser and stop the instance."""
    global browser_instance_persistent, playwright_instance_persistent, driver_page
    logger.info("Shutting down Persistent Playwright resources...")

    # Ensure page is closed first
    if driver_page and not driver_page.is_closed():
        try:
            await driver_page.close()
            logger.info("Persistent page closed during shutdown.")
        except Exception as e:
            logger.error(f"Error closing persistent page during shutdown: {e}") # Log error in empty except
    # Close browser
    if browser_instance_persistent and browser_instance_persistent.is_connected():
        try:
            await browser_instance_persistent.close()
            logger.info("Persistent browser instance closed.")
        except Exception as e:
            logger.error(f"Error closing persistent browser instance: {e}")
    browser_instance_persistent = None

    # Stop Playwright
    if playwright_instance_persistent:
         try:
              await playwright_instance_persistent.stop()
              logger.info("Persistent Playwright instance stopped.")
         except Exception as e:
              logger.error(f"Error stopping persistent playwright instance: {e}")
    playwright_instance_persistent = None

# --- Example Usage (within an async context) ---
# async def main():
#     # Load config, setup globals etc.
#     connected = await connect_kick_chat("oakleyboiii")
#     if connected:
#         logger.info("Connection successful, running for 60 seconds...")
#         await asyncio.sleep(60)
#         await disconnect_kick_chat()
#     await shutdown_playwright()

# if __name__ == "__main__":
#     asyncio.run(main())
