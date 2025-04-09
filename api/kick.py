import time
import datetime
import json
import asyncio
import os
import random
import threading
from queue import Queue
# Assuming config.py and globals.py exist and are configured
import config
# Removed proxy config import
import globals # Import globals to access kick_emotes
import logging
from bs4 import BeautifulSoup, Tag # Import BeautifulSoup
import stealth_requests as requests # Import stealth_requests
import requests as standard_requests # Import standard requests for exceptions, Timeout

# Set up logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Example basic config
logger = logging.getLogger(__name__)

# Proxy Management Removed

# Import Selenium and undetected_chromedriver
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException

# --- Globals ---
# Persistent Selenium driver instance for scraping the live chat DOM
selenium_driver = None # WebDriver instance for ongoing chat polling

# Thread-safe queue and polling control
message_queue = Queue()
last_processed_index = -1
polling_active = False
polling_task = None
streaming_task = None

# Keep-alive timer thread
keep_alive_timer = None
keep_alive_active = False
# --- Globals End ---

# Removed get_zenrows_browser function as stealth_requests handles this internally

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

# --- API Calls using stealth_requests (to handle Cloudflare/fingerprinting) ---
# Note: These calls now use stealth_requests directly without the proxy wrapper.

async def get_all_username_emotes(username):
    """
    Download all emote images for a given username from Kick using stealth_requests.

    Steps:
      1. Navigate to https://kick.com/emotes/{username} and extract JSON data.
      2. For every emote in the JSON, construct the image URL.
      3. Use Playwright’s request API to fetch the image and save it in a folder named "emote_cache/{username}_emotes".
      4. Populate globals.kick_emotes with {"emoteName": "/emotes/{username}_emotes/filename.jpg"}
    """
    logger.info(f"Starting to get emotes for username: {username} using stealth_requests")

    # Clear previous emotes for this user from the global dict
    # This assumes emotes are user-specific and we want fresh data
    # A more complex approach might merge or only update, but clearing is simpler for now.
    # We need to iterate and remove keys associated with this user's path prefix.
    emote_path_prefix = f"/emotes/{username}_emotes/"
    keys_to_remove = [k for k, v in globals.kick_emotes.items() if v.startswith(emote_path_prefix)]
    for key in keys_to_remove:
        del globals.kick_emotes[key]
    logger.info(f"Cleared previous emotes for {username} from globals.kick_emotes")

    try:
        # Fetch the emotes list JSON using stealth_requests directly
        emotes_url = f"https://kick.com/emotes/{username}"
        logger.info(f"Fetching emotes list from {emotes_url} using stealth_requests")
        resp = await asyncio.to_thread(requests.get, emotes_url, timeout=30)
        resp.raise_for_status() # Check for HTTP errors
        data = resp.json()

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
                    logger.info(f"Downloading emote '{emote_name}' from {image_url} using stealth_requests")
                    try:
                        # Use stealth_requests directly to fetch the image
                        img_resp = await asyncio.to_thread(requests.get, image_url, timeout=30)
                        img_resp.raise_for_status() # Check for HTTP errors
                        image_bytes = img_resp.content
                        # Determine file extension (basic check, could be improved)
                        content_type = img_resp.headers.get('content-type', '').lower()
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
                    except (standard_requests.exceptions.RequestException, standard_requests.exceptions.Timeout) as download_err:
                        # Log error if direct request fails
                        logger.error(f"Failed to download emote '{emote_name}' using stealth_requests: {str(download_err)}")
                    except IOError as save_err:
                        logger.error(f"Error saving emote '{emote_name}' image: {str(save_err)}")
                    except Exception as other_err: # Catch other potential errors (e.g., file system)
                        logger.error(f"Unexpected error processing emote '{emote_name}': {str(other_err)}")

        logger.info(f"Finished downloading {emotes_found_count} emotes for username: {username}")
        logger.debug(f"Current globals.kick_emotes: {globals.kick_emotes}") # Log the result for debugging
        return True

    except (standard_requests.exceptions.RequestException, standard_requests.exceptions.Timeout) as req_err: # type: ignore
        # Log error if direct request fails for the main list
        logger.error(f"Failed to fetch emotes list for {username} using stealth_requests: {str(req_err)}")
    except json.JSONDecodeError as json_err:
        logger.error(f"JSON decoding failed for {username} emotes list: {json_err}. Response text: {resp.text[:200] if 'resp' in locals() and resp else 'N/A'}")
    except IOError as dir_err:
        logger.error(f"Error creating/accessing emote directory for {username}: {str(dir_err)}")
    except Exception as e:
        logger.exception(f"Unexpected error in get_all_username_emotes for {username}: {str(e)}")

    return None # Return None on failure


async def get_kick_channel_id(username):
    """Get Kick channel ID using stealth_requests to handle Cloudflare."""
    logger.info(f"Attempting to get channel ID for '{username}' using stealth_requests...")
    api_url = f"https://kick.com/api/v2/channels/{username}"
    headers = {'Accept': 'application/json'}

    try:
        # Use stealth_requests directly to fetch the channel data
        logger.info(f"Fetching channel data from {api_url} using stealth_requests")
        resp = await asyncio.to_thread(requests.get, api_url, headers=headers, timeout=30)
        resp.raise_for_status() # Check for HTTP errors
        data = resp.json()

        channel_id = data.get("id")
        if not channel_id:
            logger.warning(f"Channel ID key 'id' not found in JSON for username: {username}. Data: {data}")
            return None

        logger.info(f"Found channel ID for {username}: {channel_id}")
        return str(channel_id)

    except (standard_requests.exceptions.RequestException, standard_requests.exceptions.Timeout) as req_err: # type: ignore
        logger.error(f"Failed to get channel ID for {username} using stealth_requests: {str(req_err)}")
        return None
    except json.JSONDecodeError as json_err:
        logger.error(f"Failed to parse JSON for {username} channel ID: {json_err}. Response text: {resp.text[:500] if 'resp' in locals() and resp else 'N/A'}...")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting channel ID for {username}: {str(e)}")
        return None


async def get_latest_subscriber(channel_id):
    """Get the latest Kick subscriber using stealth_requests."""
    logger.info(f"Attempting to get latest subscriber for channel ID {channel_id} using stealth_requests...")
    api_url = f"https://kick.com/api/v2/channels/{channel_id}/subscribers/last"
    headers = {'Accept': 'application/json'}

    try:
        # Use stealth_requests directly to fetch the subscriber data
        logger.info(f"Fetching subscriber data from {api_url} using stealth_requests")
        resp = await asyncio.to_thread(requests.get, api_url, headers=headers, timeout=30)
        resp.raise_for_status() # Check for HTTP errors
        data = resp.json()

        if "data" in data and data["data"]: # Check if data exists and is not empty/null
            logger.info(f"Found latest subscriber data for channel {channel_id}")
            return data["data"]
        else:
            logger.warning(f"No subscriber 'data' key found in JSON response for channel: {channel_id}. Data: {data}")
            return None

    except (standard_requests.exceptions.RequestException, standard_requests.exceptions.Timeout) as req_err: # type: ignore
        logger.error(f"Failed to get latest subscriber for {channel_id} using stealth_requests: {str(req_err)}")
        return None
    except json.JSONDecodeError as json_err:
        logger.error(f"Failed to parse JSON for latest subscriber (Channel {channel_id}): {json_err}. Response text: {resp.text[:500] if 'resp' in locals() and resp else 'N/A'}...")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting latest subscriber for {channel_id}: {str(e)}")
        return None
# --- End API Calls ---

def _parse_kick_message_html(html_content: str):
    """
    Parses the HTML content of a Kick chat message using BeautifulSoup
    to extract sender, message text, and emote details.

    Args:
        html_content: The raw outerHTML string of the message element.

    Returns:
        A dictionary containing:
        - 'sender': The username of the message sender.
        - 'message_text': The textual content of the message, with emotes replaced by placeholders like [emote:name].
        - 'emotes': A list of dictionaries, each containing 'name' and 'url' for an emote found in the message.
        - 'timestamp': The timestamp string (e.g., '12:31 AM') or None if not found.
        - 'is_reply': Boolean indicating if it's a reply message.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    sender = "System"
    message_parts = []
    emotes = []
    timestamp = None
    is_reply = False

    # Determine if it's a reply based on the presence of the reply header div
    reply_header = soup.find('div', class_='text-white/40')
    if reply_header:
        is_reply = True
        # In replies, the main content div is usually the direct child after the header
        main_content_div = reply_header.find_next_sibling('div')
        if not main_content_div:
             main_content_div = soup # Fallback if structure is unexpected
    else:
        # In standard messages, the main content div is often the root or a direct child
        main_content_div = soup

    # --- Extract Timestamp ---
    # Replies and standard messages might have slightly different structures for timestamp
    ts_el = main_content_div.find('span', class_='text-neutral')
    if ts_el:
        timestamp = ts_el.get_text(strip=True)

    # --- Extract Sender ---
    # Look for the button containing the username
    # Replies: Often nested deeper
    # Standard: More direct
    user_button = main_content_div.find('button', class_='inline font-bold')
    if user_button:
        sender = user_button.get('title', user_button.get_text(strip=True))
    elif main_content_div.find('button', title='BotRix'): # Specific BotRix case
         sender = "BotRix"

    # --- Extract Message Content and Emotes ---
    # Find the span containing the actual message parts (text and emotes)
    message_span = main_content_div.find('span', class_='font-normal') # Simplified selector, adjust if needed
    if message_span:
        for element in message_span.children:
            if isinstance(element, Tag):
                # Check if it's an emote span (contains an img)
                img_tag = element.find('img', alt=True, src=True)
                if img_tag:
                    emote_name = img_tag.get('alt')
                    emote_url = img_tag.get('src')
                    emote_id = emote_url.split('/emotes/')[1].split('/')[0]
                    if emote_name:
                        message_parts.append(f"[emote:{emote_name}|{emote_id}]") # Placeholder in text with ID
                        emotes.append({"name": emote_name, "url": emote_url, "id": emote_id}) # Include ID in emotes data
                else:
                    # Append other tag text content if necessary, though usually emotes are the main tags
                    message_parts.append(element.get_text())
            else:
                # It's a NavigableString (plain text)
                message_parts.append(str(element)) # Convert NavigableString to string

    message_text = "".join(message_parts).strip()

    # Fallback if parsing failed to get sender/message but we have some text
    if sender == "System" and not message_text:
         full_text = soup.get_text(separator=' ', strip=True)
         # Basic attempt to split user: message
         if ':' in full_text:
              parts = full_text.split(':', 1)
              potential_user = parts[0].split(']')[-1].strip() # Handle timestamps like [12:31 AM] User
              if potential_user: sender = potential_user
              message_text = parts[1].strip()
         else:
              message_text = full_text # Use the whole text if no colon

    return {
        "sender": sender,
        "message_text": message_text,
        "emotes": emotes,
        "timestamp": timestamp,
        "is_reply": is_reply,
    }


def parse_kick_timestamp(time_str):
    """Placeholder for parsing Kick's chat timestamp (e.g., '08:22 PM') if needed."""
    return time_str.strip() # Currently returns as string


async def wait_for_element_with_retry(driver, by, value, max_retries=2, delay=1, timeout_per_try=7, log_prefix="", channel_name="unknown"):
    """
    Attempts to wait for an element with retries and longer timeouts using Selenium.
    Takes a screenshot on timeout.
    """
    attempt = 1
    last_exception = None
    selector_str = f"{by}={value}" # For logging
    while attempt <= max_retries:
        try:
            logger.info(f"{log_prefix}Element wait attempt {attempt}/{max_retries}: Waiting for '{selector_str}' (timeout: {timeout_per_try}s)...")
            # Wrap synchronous WebDriverWait in asyncio.to_thread
            element = await asyncio.to_thread(
                WebDriverWait(driver, timeout_per_try).until,
                EC.visibility_of_element_located((by, value))
            )
            logger.info(f"{log_prefix}Element '{selector_str}' found and visible.")
            return element # Return the WebElement if successful
        except TimeoutException as e:
            logger.warning(f"{log_prefix}Element wait attempt {attempt}/{max_retries}: Timeout waiting for '{selector_str}'.")
            last_exception = e
            # --- Take Screenshot on Timeout ---
            try:
                # Ensure the driver is still usable for screenshot
                if driver and driver.session_id:
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_selector = value.replace('#','').replace('.','').replace('[','').replace(']','').replace('=','')[:30] # Basic sanitize
                    screenshot_filename = f"debug_screenshots/{timestamp}_{channel_name}_attempt{attempt}_timeout_{safe_selector}.png"
                    # Wrap synchronous screenshot in asyncio.to_thread
                    await asyncio.to_thread(driver.save_screenshot, screenshot_filename)
                    logger.info(f"{log_prefix}Saved screenshot on timeout to: {screenshot_filename}")
                else:
                    logger.warning(f"{log_prefix}Driver was closed or invalid, cannot take screenshot for timeout on attempt {attempt}.")
            except Exception as ss_err:
                logger.error(f"{log_prefix}Failed to take or save screenshot on timeout: {ss_err}")
            # --- End Screenshot ---

            if attempt < max_retries:
                 logger.info(f"{log_prefix}Retrying element wait in {delay} seconds...")
                 await asyncio.sleep(delay)
            attempt += 1
        except WebDriverException as e: # Catch other potential Selenium errors
             logger.error(f"{log_prefix}Element wait attempt {attempt}/{max_retries}: WebDriver error waiting for '{selector_str}': {str(e)}")
             last_exception = e
             # Check if the browser/driver is closed
             if "disconnected" in str(e).lower() or "session deleted" in str(e).lower() or "no such window" in str(e).lower():
                 logger.error(f"{log_prefix}Driver appears to be closed. Raising exception.")
                 raise e # Don't retry if driver is closed
             await asyncio.sleep(delay)
             attempt += 1
        except Exception as e: # Catch unexpected errors
            logger.exception(f"{log_prefix}Unexpected error during element wait for '{selector_str}': {e}")
            last_exception = e
            # Decide if retry is appropriate based on error type if needed
            await asyncio.sleep(delay)
            attempt += 1


    logger.error(f"Failed to locate element '{selector_str}' after {max_retries} attempts.")
    raise last_exception or TimeoutException(f"Element '{selector_str}' not found after {max_retries} attempts.")


async def poll_messages(channel_name):
    """Continuously poll for new chat messages using the persistent Selenium driver."""
    global last_processed_index, polling_active, selenium_driver
    if not selenium_driver or not selenium_driver.session_id:
        logger.error("Polling cannot start: Persistent Selenium driver is not initialized or session is invalid.")
        polling_active = False
        return

    logger.info(f"Starting Kick chat DOM polling for channel: {channel_name}")
    message_selector = "div#chatroom-messages > div.relative > div[data-index]" # CSS Selector for message wrappers

    while polling_active:
        try:
            # Check if driver is still alive (basic check)
            try:
                # Accessing current_url is a lightweight way to check session validity
                _ = await asyncio.to_thread(getattr, selenium_driver, 'current_url')
            except WebDriverException as wd_err:
                 logger.warning(f"Polling loop detected WebDriverException (driver likely closed): {wd_err}. Stopping.")
                 polling_active = False
                 break

            # Wrap synchronous find_elements in asyncio.to_thread
            message_elements = await asyncio.to_thread(selenium_driver.find_elements, By.CSS_SELECTOR, message_selector)

            if not message_elements:
                # logger.debug("No message elements found in current poll cycle.")
                await asyncio.sleep(1) # Wait a bit longer if nothing is found
                continue

            new_messages_found_in_batch = False
            max_index_in_batch = last_processed_index

            # Process elements synchronously within the thread to avoid excessive thread switching
            # This requires careful handling if parsing itself becomes very slow
            def process_batch(elements, current_last_index):
                processed_messages = []
                max_idx = current_last_index
                new_found = False
                for element in elements:
                    try:
                        index_str = element.get_attribute("data-index")
                        if not index_str: continue
                        index = int(index_str)

                        if index > current_last_index:
                            new_found = True
                            max_idx = max(max_idx, index)
                            # Get the raw HTML of the message element
                            outer_html = element.get_attribute("outerHTML")
                            if outer_html:
                                processed_messages.append({"index": index, "html": outer_html})
                            else:
                                logger.warning(f"Could not get outerHTML for element with index {index}")
                    except (ValueError, NoSuchElementException, WebDriverException) as el_err:
                        logger.warning(f"Error getting attributes for a message element: {el_err}")
                    except Exception as gen_err: # Catch unexpected errors during attribute access
                        logger.error(f"Unexpected error getting attributes for element: {gen_err}")
                return processed_messages, max_idx, new_found

            # Run the batch processing in a thread
            messages_to_parse, max_index_in_batch, new_messages_found_in_batch = await asyncio.to_thread(
                process_batch, message_elements, last_processed_index
            )

            # Parse HTML and queue messages asynchronously
            for item in messages_to_parse:
                index = item["index"]
                outer_html = item["html"]
                try:
                    # Parse the HTML using BeautifulSoup (already imported)
                    parsed_data = _parse_kick_message_html(outer_html)

                    # Extract data from the parsed result
                    timestamp_text = parsed_data.get("timestamp", "N/A")
                    username_text = parsed_data.get("sender", "System")
                    message_text = parsed_data.get("message_text", "")
                    emotes_list = parsed_data.get("emotes", [])
                    is_reply = parsed_data.get("is_reply", False)

                    # --- Queue the message ---
                    # Ensure we have a sender and either text or emotes
                    if username_text and (message_text or emotes_list or username_text != "System"):
                        msg = {
                            "data_index": index,
                            "timestamp": timestamp_text,
                            "sender": username_text,
                            "content": message_text,
                            "emotes": emotes_list,
                            "is_reply": is_reply,
                        }
                        message_queue.put(msg)
                        # logger.debug(f"Queued message index {index}: User='{username_text}', Text='{message_text[:30]}...', Emotes={len(emotes_list)}")
                    else:
                         logger.debug(f"Skipping queuing message index {index} due to missing sender/content after BS4 parsing.")

                except Exception as parse_err:
                    logger.error(f"Error parsing or queuing message element at index {index}: {str(parse_err)}")
                    logger.debug(f"Problematic element HTML for index {index}: {outer_html[:500]}...")


            # Update index after processing batch
            if new_messages_found_in_batch:
                last_processed_index = max_index_in_batch
                logger.info(f"Processed DOM messages up to index {last_processed_index}")

                last_processed_index = max_index_in_batch
                logger.info(f"Processed DOM messages up to index {last_processed_index}")

            await asyncio.sleep(0.8) # Polling interval

        except WebDriverException as e:
            # More specific handling for closed driver/browser
            if "disconnected" in str(e).lower() or "session deleted" in str(e).lower() or "no such window" in str(e).lower() or "unable to connect" in str(e).lower():
                 logger.error(f"Persistent Selenium driver connection closed or lost during polling: {str(e)}")
                 polling_active = False
                 break # Exit loop
            else:
                 logger.error(f"Unhandled WebDriverException during DOM polling: {str(e)}")
                 await asyncio.sleep(5) # Wait before retrying
        except Exception as e:
            logger.exception(f"Generic error during DOM message polling loop: {str(e)}") # Use exception for traceback
            await asyncio.sleep(5) # Wait before retrying

    logger.info(f"Stopped Kick chat DOM polling for channel: {channel_name}")


async def handle_enter_command(username):
    """Handle the !enter command for Kick chat."""
    if username not in config.entered_users:
        config.entered_users.append(username)
        logger.info(f"Raffle entry from Kick: {username}")
        # Broadcast raffle entry confirmation
        await broadcast_raffle_entry(username)
        return True
    return False


async def broadcast_raffle_entry(username):
    """Broadcast a raffle entry to all connected clients."""
    entry_data = {
        "type": "raffle_entry",
        "data": {
            "user": username,
            "platform": "kick",
            "total_entries": len(config.entered_users)
        }
    }
    await globals.manager.broadcast(json.dumps(entry_data))


async def get_active_kick_viewers():
    """Get a list of active viewers from Kick chat messages."""
    if not config.kick_chat_connected or not config.kick_chat_messages:
        logger.warning("Cannot get active Kick viewers: Not connected or no messages")
        return []

    # Extract unique usernames from recent chat messages
    unique_viewers = set()
    for msg in config.kick_chat_messages:
        if "user" in msg and msg["user"] != "System":
            unique_viewers.add(msg["user"])

    logger.info(f"Found {len(unique_viewers)} active Kick viewers")
    return list(unique_viewers)


async def select_random_kick_viewers(count=1, use_raffle=False):
    """Select random viewers from Kick chat.

    Args:
        count: Number of viewers to select
        use_raffle: If True, select from raffle entries, otherwise from active viewers

    Returns:
        List of selected viewer usernames
    """
    if use_raffle:
        # Select from raffle entries
        if not config.entered_users:
            logger.warning("No raffle entries to select from")
            await broadcast_error("No raffle entries to select from")
            return []

        if len(config.entered_users) < count:
            logger.warning(f"Not enough raffle entries ({len(config.entered_users)}) to select {count} viewers")
            await broadcast_error(f"Not enough raffle entries ({len(config.entered_users)}) to select {count} viewers")
            count = len(config.entered_users)

        try:
            winners = random.sample(config.entered_users, count)
            logger.info(f"Selected {len(winners)} winners from raffle entries: {winners}")
            # Clear raffle entries after selection
            config.entered_users.clear()
            await globals.manager.broadcast(json.dumps({
                "type": "raffle_entries_cleared",
                "data": {"message": "Raffle entries cleared after selection"}
            }))
            return winners
        except Exception as e:
            logger.error(f"Error selecting raffle winners: {e}")
            await broadcast_error(f"Error selecting raffle winners: {str(e)}")
            return []
    else:
        # Select from active viewers
        active_viewers = await get_active_kick_viewers()
        if not active_viewers:
            logger.warning("No active Kick viewers to select from")
            await broadcast_error("No active Kick viewers to select from")
            return []

        if len(active_viewers) < count:
            logger.warning(f"Not enough active viewers ({len(active_viewers)}) to select {count} viewers")
            await broadcast_error(f"Not enough active viewers ({len(active_viewers)}) to select {count} viewers")
            count = len(active_viewers)

        try:
            selected = random.sample(active_viewers, count)
            logger.info(f"Selected {len(selected)} random Kick viewers: {selected}")
            return selected
        except Exception as e:
            logger.error(f"Error selecting random Kick viewers: {e}")
            await broadcast_error(f"Error selecting random Kick viewers: {str(e)}")
            return []


async def broadcast_error(message):
    """Broadcast an error message to all connected clients."""
    error_data = {
        "type": "error",
        "data": {"message": message}
    }
    await globals.manager.broadcast(json.dumps(error_data))


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
                emotes = msg.get("emotes", []) # Get the emotes list

                # Skip if message is essentially empty (no sender or just system message without content/emotes)
                if not sender or (sender == "System" and not content and not emotes):
                    logger.debug(f"Skipping streaming message index {msg.get('data_index')} due to missing sender/content/emotes.")
                    message_queue.task_done()
                    continue

                # Check for !enter command
                if content.strip().lower() == "!enter":
                    await handle_enter_command(sender)

                message_data = {
                    "type": "kick_chat_message",
                    "data": {
                        "channel": channel_name,
                        "user": sender,
                        "text": content, # Text with placeholders like [emote:name]
                        "timestamp": timestamp,
                        "emotes": emotes # List of {"name": "...", "url": "..."}
                    }
                }
                # Broadcast for main UI (now includes emotes)
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


def keep_alive_thread_function(interval=1):
    """Thread function to keep the chat page alive even when minimized.
    Enhanced for Docker/Xvfb environments where window focus works differently."""
    global selenium_driver, keep_alive_active
    logger.info(f"Starting keep-alive thread with interval of {interval} seconds")

    # Track time for periodic refresh
    last_refresh_time = time.time()
    refresh_interval = 30  # Refresh page every 30 seconds (reduced from 60)
    # Alert interval is not needed in Docker/Xvfb as there's no real window focus
    # but we'll keep the variable for code structure
    last_interaction_time = time.time()
    interaction_interval = 5  # Interact with the page every 5 seconds

    while keep_alive_active and selenium_driver:
        try:
            # Check if driver is still valid
            if not selenium_driver or not selenium_driver.session_id:
                logger.warning("Keep-alive thread detected invalid driver. Stopping.")
                break

            current_time = time.time()

            # Periodic page refresh to ensure chat stays active
            if current_time - last_refresh_time >= refresh_interval:
                try:
                    logger.info("Performing periodic page refresh to keep chat active")
                    # Refresh the page
                    selenium_driver.refresh()
                    # Wait for chat container to reappear
                    WebDriverWait(selenium_driver, 15).until(  # Increased timeout for Docker
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "#chatroom-messages"))
                    )
                    last_refresh_time = current_time
                    logger.info("Page refreshed successfully")
                except Exception as refresh_err:
                    logger.error(f"Error during page refresh: {refresh_err}")

            # Regular interaction with the page (instead of alerts which may not work in Docker/Xvfb)
            if current_time - last_interaction_time >= interaction_interval:
                try:
                    logger.debug("Performing page interaction to maintain activity")
                    # Instead of alerts, we'll use more reliable DOM interactions

                    # Scroll chat container to trigger activity
                    selenium_driver.execute_script("""
                        const chatContainer = document.getElementById('chatroom-messages');
                        if (chatContainer) {
                            const currentScroll = chatContainer.scrollTop;
                            chatContainer.scrollTop = currentScroll + 1;
                            setTimeout(() => chatContainer.scrollTop = currentScroll, 100);
                        }
                    """)

                    last_interaction_time = current_time
                except Exception as interact_err:
                    logger.warning(f"Error during page interaction: {interact_err}")

            # Execute JavaScript to prevent throttling - optimized for Docker/Xvfb
            try:
                # Force window focus and prevent background throttling with more aggressive approach
                selenium_driver.execute_script("""
                    // Keep the page active
                    window.focus();
                    document.hasFocus = function() { return true; };

                    // Prevent throttling with multiple techniques
                    if (typeof requestIdleCallback === 'function') {
                        requestIdleCallback(() => {}, { timeout: 1 });
                    }

                    // Request animation frame to keep page active
                    requestAnimationFrame(() => {});

                    // Create a dummy audio context to prevent throttling
                    try {
                        const AudioContext = window.AudioContext || window.webkitAudioContext;
                        if (AudioContext && !window._dummyAudioContext) {
                            window._dummyAudioContext = new AudioContext();
                        }
                    } catch(e) {}

                    // Override visibility API to always report visible
                    Object.defineProperty(document, 'hidden', { value: false, writable: false });
                    Object.defineProperty(document, 'visibilityState', { value: 'visible', writable: false });
                    document.dispatchEvent(new Event('visibilitychange'));

                    // Simulate user interaction with keyboard events
                    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
                    document.dispatchEvent(new KeyboardEvent('keyup', { key: 'a', bubbles: true }));

                    // Click on a non-interactive element to trigger activity
                    const nonInteractiveElements = document.querySelectorAll('div:not(button):not(a):not(input)');
                    if (nonInteractiveElements.length > 0) {
                        const randomElement = nonInteractiveElements[Math.floor(Math.random() * nonInteractiveElements.length)];
                        randomElement.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true
                        }));
                    }
                """)

            except Exception as js_err:
                logger.warning(f"JavaScript execution error in keep-alive: {js_err}")
                # Don't break the loop for JS errors

            # Sleep interval for interaction frequency
            time.sleep(interval)

        except Exception as e:
            logger.error(f"Error in keep-alive thread: {str(e)}")
            time.sleep(2)  # Slightly longer wait on error

    logger.info("Keep-alive thread stopped")


async def connect_kick_chat(channel_name):
    """Connect to Kick chat: Get ID, init persistent Selenium driver, start polling."""
    global selenium_driver # Use the Selenium driver global
    global polling_active, last_processed_index, polling_task, streaming_task
    global keep_alive_timer, keep_alive_active

    if not channel_name or channel_name.isspace():
        logger.warning("Connect Kick chat request missing channel name.")
        await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": "Please enter a Kick channel name."}}))
        return False

    channel_name = channel_name.strip().lower()
    logger.info(f"Attempting to connect to Kick chat for channel: {channel_name}")

    # --- Disconnect if already connected ---
    if config.kick_chat_connected:
        logger.info(f"Disconnecting previous Kick chat ({config.kick_channel_name}) before connecting to {channel_name}.")
        await disconnect_kick_chat() # Ensure previous state is cleared
        await asyncio.sleep(1) # Short delay

    # --- Reset state ---
    last_processed_index = -1
    config.kick_chat_messages.clear()
    while not message_queue.empty():
        try: message_queue.get_nowait()
        except: pass

    # --- Get Channel ID (Using stealth_requests) ---
    logger.info(f"Getting channel ID for: {channel_name} using https://github.com/jpjacobpadilla/Stealth-Requests...")
    channel_id = await get_kick_channel_id(channel_name) # Uses the stealth_requests version now
    if not channel_id:
        logger.error(f"Could not get Kick channel ID via stealth_requests for: {channel_name}")
        await globals.manager.broadcast(json.dumps({
            "type": "error",
            "data": {"message": f"Could not find Kick channel or bypass protection for: {channel_name}"}
        }))
        return False
    logger.info(f"Successfully obtained Kick channel ID: {channel_id}")

    # --- Download Emotes for the Channel ---
    logger.info(f"Attempting to download emotes for channel: {channel_name}")
    emotes_downloaded = await get_all_username_emotes(channel_name)
    if emotes_downloaded:
        logger.info(f"Successfully initiated emote download process for {channel_name}.")
    else:
        logger.warning(f"Failed to download emotes for {channel_name}. Proceeding without custom emotes.")
     # Note: We proceed even if emotes fail, chat should still work.

    # --- Initialize PERSISTENT Selenium Driver (if needed) ---
    try:
        if not selenium_driver or not selenium_driver.session_id:
            logger.info("Initializing Persistent Selenium Driver (undetected-chromedriver)...")
            # Wrap synchronous driver initialization in asyncio.to_thread
            def start_driver():
                options = uc.ChromeOptions()
                # Avoid using headless mode with undetected-chromedriver
                # Instead, we're using a virtual display with GNOME
                options.add_argument('--disable-background-timer-throttling')
                options.add_argument('--disable-backgrounding-occluded-windows')
                options.add_argument("--disable-renderer-backgrounding")
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                # You might need to specify the driver executable path if not in PATH
                # driver_executable_path = '/path/to/chromedriver'
                # return uc.Chrome(options=options, driver_executable_path=driver_executable_path)
                return uc.Chrome(options=options)

            selenium_driver = await asyncio.to_thread(start_driver)
            logger.info("Persistent Selenium Driver initialized.")
        else:
            logger.info("Reusing existing Persistent Selenium Driver.")

        # --- Navigate and Wait ---
        chat_url = f"https://kick.com/{channel_name}"
        connection_successful = False
        last_exception = None
        log_prefix = "[Selenium Connect] "

        try:
            logger.info(f"{log_prefix}Navigating to {chat_url}...")
            # Wrap synchronous driver.get in asyncio.to_thread
            await asyncio.to_thread(selenium_driver.get, chat_url)
            logger.info(f"{log_prefix}Navigation complete. Waiting for chat messages container (#chatroom-messages)...")

            # Use the modified wait function
            await wait_for_element_with_retry(
                selenium_driver,
                By.CSS_SELECTOR,
                "#chatroom-messages",
                timeout_per_try=15, # Timeout in seconds for Selenium
                log_prefix=log_prefix,
                channel_name=channel_name
            )

            logger.info(f"{log_prefix}Connection successful!")
            connection_successful = True

        except (TimeoutException, WebDriverException) as e:
            logger.error(f"{log_prefix}Selenium connection failed: {type(e).__name__} - {str(e)}")
            last_exception = e
        except Exception as e:
             logger.error(f"{log_prefix}Unexpected error during Selenium connection: {e}", exc_info=True)
             last_exception = e

        # --- Check final connection status ---
        if not connection_successful:
            error_msg = f"Selenium connection failed for {channel_name}. Last error: {type(last_exception).__name__ if last_exception else 'N/A'}"
            logger.error(error_msg)
            # Attempt to quit the driver if connection failed mid-way
            if selenium_driver:
                try:
                    await asyncio.to_thread(selenium_driver.quit)
                    logger.info("Quit Selenium driver after connection failure.")
                    selenium_driver = None
                except Exception as q_err:
                    logger.error(f"Error quitting Selenium driver after connection failure: {q_err}")
            raise last_exception or WebDriverException(f"Failed to connect to {channel_name} using Selenium.")

        # --- Start Polling and Streaming Tasks ---
        # Ensure previous tasks are properly handled before setting new state
        if polling_task and not polling_task.done():
            polling_task.cancel()
        if streaming_task and not streaming_task.done():
            streaming_task.cancel()

        # Validate channel info before updating state
        if not channel_id or not channel_name:
            raise ValueError("Invalid channel ID or name received")

        # Update configuration state atomically
        config.kick_channel_id = channel_id
        config.kick_channel_name = channel_name
        polling_active = True  # Set flag after state is properly configured

        logger.info("Creating polling and streaming tasks...")
        # Ensure previous tasks are properly handled if reconnecting quickly
        if polling_task and not polling_task.done(): polling_task.cancel()
        if streaming_task and not streaming_task.done(): streaming_task.cancel()

        polling_task = asyncio.create_task(poll_messages(channel_name))
        streaming_task = asyncio.create_task(stream_messages(channel_name))

        config.kick_chat_connected = True
        config.kick_chat_stream = {"channel_id": channel_id, "channel_name": channel_name}

        # Set a fixed window size for Docker/Xvfb environment
        # In Docker with Xvfb, window positioning doesn't matter as much
        # but we still want a reasonable window size for performance
        width = 1024
        height = 768

        #
        await asyncio.to_thread(selenium_driver.execute_script("focus the window")) # Focus the window


        logger.info(f"Browser window set to fixed size ({width}x{height}) for Docker environment")

        # Start the keep-alive timer thread with shorter interval
        keep_alive_active = True
        keep_alive_timer = threading.Thread(
            target=keep_alive_thread_function,
            args=(1,),  # 1-second interval for more frequent interactions
            daemon=True
        )
        keep_alive_timer.start()
        logger.info("Started enhanced keep-alive timer thread")

        await globals.manager.broadcast(json.dumps({"type": "kick_chat_connected", "data": {"channel": channel_name}}))
        logger.info(f"Successfully connected to Kick chat: {channel_name}")
        return True

        # Note: No return False here, error is raised above if connection failed

    # Outer exception handling for Selenium connection/wait failures
    except (TimeoutException, WebDriverException) as e:
        logger.error(f"Selenium connection/wait failed for {channel_name}: {type(e).__name__} - {str(e)}")
        error_message = f"Failed to load Kick channel page or find chat for {channel_name} (timeout or WebDriver error). Is the channel live or blocked?"
        await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": error_message}}))
        # Ensure disconnect cleanup runs even if connection failed partway
        await disconnect_kick_chat(driver_already_quit=(selenium_driver is None)) # Pass flag if driver was quit during failure handling
        return False
    except Exception as e: # Catch other unexpected errors during setup/connection
        logger.exception(f"Unexpected error during Selenium driver setup or connection for {channel_name}: {str(e)}")
        error_message = f"Unexpected error connecting to Kick chat: {str(e)}"
        await globals.manager.broadcast(json.dumps({"type": "error", "data": {"message": error_message}}))
        # Ensure disconnect cleanup runs
        await disconnect_kick_chat(driver_already_quit=(selenium_driver is None))
        return False


async def disconnect_kick_chat(driver_already_quit=False):
    """Disconnect from Kick chat, stop tasks. Optionally keeps driver running."""
    global selenium_driver, polling_active, polling_task, streaming_task
    global keep_alive_active, keep_alive_timer
    # Note: We keep the persistent driver running by default unless shutdown_selenium_driver is called.

    if not config.kick_chat_connected and not polling_active:
        logger.info("No active Kick chat connection or tasks to disconnect.")
        # Still ensure driver is handled if disconnect is called after a failed connect where driver might exist
        if selenium_driver and not driver_already_quit:
             logger.debug("Disconnect called with no active connection, but driver exists. Keeping driver alive.")
    else:
        logger.info(f"Disconnecting from Kick chat: {config.kick_channel_name or 'Unknown'}")

    # Stop all active tasks and threads
    polling_active = False # Signal polling loops to stop
    keep_alive_active = False # Signal keep-alive thread to stop

    # Cancel running asyncio tasks
    if polling_task and not polling_task.done():
        polling_task.cancel()
        logger.info("Polling task cancellation requested.")
    if streaming_task and not streaming_task.done():
        streaming_task.cancel()
        logger.info("Streaming task cancellation requested.")

    # Wait for keep-alive thread to finish if it's running
    if keep_alive_timer and keep_alive_timer.is_alive():
        logger.info("Waiting for keep-alive thread to stop...")
        # We don't join the thread here as it might block if the thread is stuck
        # The daemon=True flag ensures it will be terminated when the program exits

    # Wait briefly for tasks
    await asyncio.sleep(0.5)

    # Reset Config and Globals (Do this before potentially slow driver operations)
    disconnected_channel = config.kick_channel_name or "Unknown"
    config.kick_chat_connected = False
    config.kick_chat_stream = None
    config.kick_channel_id = None
    config.kick_channel_name = None
    # Reset the last processed index for message tracking
    global last_processed_index
    last_processed_index = -1
    polling_task = None
    streaming_task = None
    keep_alive_timer = None

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

    logger.info(f"Successfully disconnected logic for Kick chat: {disconnected_channel}")
    return True


async def shutdown_selenium_driver():
    """Gracefully close the persistent Selenium driver."""
    global selenium_driver
    logger.info("Shutting down Persistent Selenium Driver...")

    if selenium_driver:
        try:
            # Wrap synchronous driver.quit in asyncio.to_thread
            await asyncio.to_thread(selenium_driver.quit)
            logger.info("Persistent Selenium driver quit successfully.")
        except WebDriverException as e:
            logger.error(f"WebDriverException during Selenium driver quit: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during Selenium driver quit: {e}")
        finally:
            selenium_driver = None # Ensure it's marked as closed/quit
    else:
        logger.info("Persistent Selenium driver was already None.")

# --- Example Usage (within an async context) ---
# async def main():
#     # Load config, setup globals etc.
#     connected = await connect_kick_chat("your_channel_name") # Replace with actual channel
#     if connected:
#         logger.info("Connection successful, running for 60 seconds...")
#         await asyncio.sleep(60)
#         await disconnect_kick_chat()
#     await shutdown_selenium_driver() # Use the new shutdown function

# if __name__ == "__main__":
#     # Setup basic logging for testing
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
#     # Initialize dummy globals manager if needed for testing broadcast
#     class DummyManager:
#         async def broadcast(self, msg): print(f"BROADCAST: {msg}")
#     globals.manager = DummyManager()
#     # Initialize dummy config if needed
#     class DummyConfig:
#         kick_chat_connected = False
#         kick_chat_stream = None
#         kick_channel_id = None
#         kick_channel_name = None
#         kick_chat_messages = []
#         entered_users = []
#         KICK_TOKEN_FILE = 'kick_tokens.json'
#     config = DummyConfig()
#     # Initialize dummy globals emotes
#     globals.kick_emotes = {}

#     asyncio.run(main())
