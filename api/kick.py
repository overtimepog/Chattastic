import time
import datetime
import requests
import threading
import json # Added for potential parsing errors

# --- Class-based approach for better management ---

class KickChatStream:
    """
    Manages fetching live chat messages from a Kick channel in a background thread.
    """
    def __init__(self, channel_id, auth_token):
        self.channel_id = channel_id
        self.auth_token = auth_token
        self._headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Accept': 'application/json',
        }
        # Use a threading.Event for graceful stopping
        self._stop_event = threading.Event()
        self._thread = None
        # Consider tracking last message ID/timestamp if API supports fetching delta
        # self._last_message_timestamp = None

        # --- Store fetched messages if you need to access them later ---
        self.messages = [] # Simple list to store messages
        self._message_lock = threading.Lock() # Protect access to the messages list

    def _fetch_and_process_chat(self):
        """Internal method to fetch chat and handle responses."""
        url = f'https://kick.com/api/v1/channels/{self.channel_id}/chat'
        # Add parameters here if needed (e.g., ?since=timestamp)
        params = {}
        # if self._last_message_timestamp:
        #     params['since'] = self._last_message_timestamp # Fictional parameter

        try:
            response = requests.get(url, headers=self._headers, params=params, timeout=10) # Add timeout

            if self._stop_event.is_set(): # Check if stopped during request
                return False # Indicate stop requested

            if response.status_code == 200:
                try:
                    # *** IMPORTANT: Verify Kick API Response Structure ***
                    # The structure might be {'data': {'messages': [...]}} or just {'messages': [...]} etc.
                    # Adjust the parsing based on the actual API response.
                    data = response.json()
                    chat_messages = []
                    if isinstance(data, dict):
                        # Common patterns:
                        if 'messages' in data and isinstance(data['messages'], list):
                            chat_messages = data['messages']
                        elif 'data' in data and isinstance(data.get('data'), dict) and 'messages' in data['data']:
                             chat_messages = data['data']['messages']
                        # Add more checks if the structure is different
                    elif isinstance(data, list): # Fallback if root is list
                        chat_messages = data
                    else:
                        print(f"[{self.channel_id}] Unexpected response format: {type(data)}")

                    new_messages_batch = []
                    for message in chat_messages:
                         if self._stop_event.is_set(): return False # Stop processing if needed

                         # --- Safely access message parts ---
                         sender = message.get('sender', {})
                         username = sender.get('username', 'UnknownUser')
                         # Kick API often uses 'content' instead of 'text'
                         text = message.get('content')
                         if text is None: # Maybe nested under 'message'?
                            text = message.get('message', {}).get('message')

                         if text: # Only process if text exists
                             formatted_msg = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {username}: {text}"
                             print(formatted_msg) # Print live message
                             new_messages_batch.append({
                                 'timestamp': datetime.datetime.now(), # Or use message timestamp if available
                                 'username': username,
                                 'text': text,
                                 'raw': message # Store raw message if needed
                             })
                         # Update tracking if API supports it (e.g., get message ID or timestamp)
                         # msg_time = message.get('created_at')
                         # if msg_time: self._last_message_timestamp = msg_time

                    # --- Safely add messages to the shared list ---
                    if new_messages_batch:
                        with self._message_lock:
                            self.messages.extend(new_messages_batch)
                            # Optional: Limit the size of stored messages
                            # max_messages = 1000
                            # self.messages = self.messages[-max_messages:]

                except json.JSONDecodeError:
                    print(f"[{self.channel_id}] Failed to decode JSON response.")
                except Exception as e: # Catch unexpected parsing errors
                     print(f"[{self.channel_id}] Error processing messages: {e}")
                     print(f"Response text was: {response.text[:200]}") # Print start of text for debug

            elif response.status_code == 404:
                print(f"[{self.channel_id}] Error 404: Channel not found or chat unavailable. Stopping worker.")
                return False # Stop the loop permanently
            elif response.status_code in [401, 403]:
                 print(f"[{self.channel_id}] Error {response.status_code}: Authentication/Authorization failed. Stopping worker.")
                 return False # Stop the loop permanently
            else:
                print(f"[{self.channel_id}] Failed to fetch chat messages: {response.status_code} - {response.text[:100]}")
                # Consider adding a longer sleep interval on repeated errors

        except requests.exceptions.Timeout:
            print(f"[{self.channel_id}] Request timed out.")
        except requests.exceptions.RequestException as e:
            print(f"[{self.channel_id}] Network error: {e}")
            # Consider adding a longer sleep interval here too
        except Exception as e: # Catch any other unexpected errors
             print(f"[{self.channel_id}] Unexpected error in fetch loop: {e}")

        return True # Indicate loop should continue

    def _run(self):
        """The target function for the background thread."""
        print(f"[{self.channel_id}] Chat stream worker started.")
        while not self._stop_event.is_set():
            should_continue = self._fetch_and_process_chat()
            if not should_continue:
                break # Exit loop if fetch indicated a permanent stop condition

            # Wait for the specified interval OR until stop_event is set
            # This makes stopping much more responsive than just time.sleep()
            self._stop_event.wait(5) # Wait for 5 seconds

        print(f"[{self.channel_id}] Chat stream worker finished.")

    def start(self):
        """Starts the background chat fetching thread."""
        if self._thread and self._thread.is_alive():
            print(f"[{self.channel_id}] Chat stream is already running.")
            return False

        # Clear the stop event flag (in case it was stopped before and restarted)
        self._stop_event.clear()
        # Create and start the thread
        # daemon=True means the thread will exit automatically if the main program exits
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[{self.channel_id}] Chat stream started in the background.")
        return True

    def stop(self):
        """Signals the background thread to stop."""
        if not self._thread or not self._thread.is_alive():
            print(f"[{self.channel_id}] Chat stream is not running.")
            return False

        print(f"[{self.channel_id}] Signaling chat stream to stop...")
        self._stop_event.set()
        return True

    def join(self, timeout=None):
        """
        Waits for the background thread to finish.
        :param timeout: Maximum time in seconds to wait.
        """
        if self._thread and self._thread.is_alive():
            print(f"[{self.channel_id}] Waiting for chat stream worker to join...")
            self._thread.join(timeout)
            if self._thread.is_alive():
                print(f"[{self.channel_id}] Chat stream worker did not stop within timeout.")
                return False
            else:
                 print(f"[{self.channel_id}] Chat stream worker joined successfully.")
                 return True
        return True # Already stopped or never started

    def is_running(self):
        """Checks if the chat stream thread is currently active."""
        return self._thread and self._thread.is_alive()

    def get_messages(self):
        """Returns a copy of the collected messages (thread-safe)."""
        with self._message_lock:
            # Return a copy so the caller doesn't modify the internal list directly
            return list(self.messages)

# --- Example Usage ---

if __name__ == "__main__":
    # Replace with your actual channel ID and token
    # **WARNING:** Avoid hardcoding sensitive tokens directly in code.
    # Use environment variables, config files, or secure methods.
    CHANNEL_ID = "your_channel_id"  # e.g., "12345" or streamer username if API uses that
    AUTH_TOKEN = "your_kick_bearer_token" # e.g., os.environ.get("KICK_TOKEN")

    if CHANNEL_ID == "your_channel_id" or AUTH_TOKEN == "your_kick_bearer_token":
        print("Please replace placeholder CHANNEL_ID and AUTH_TOKEN before running.")
    else:
        # Create an instance for a specific channel
        chat_monitor = KickChatStream(CHANNEL_ID, AUTH_TOKEN)

        # Start the chat stream in the background
        chat_monitor.start()

        print("\nMain program continues to run...")
        print("Chat messages will appear above as they arrive.")
        print("Doing other tasks here...")
        time.sleep(10) # Simulate doing other work
        print("Still doing other tasks...")
        time.sleep(10) # Simulate more work

        # Example: Accessing collected messages
        collected = chat_monitor.get_messages()
        print(f"\n--- Collected {len(collected)} messages so far ---")
        for msg in collected[-5:]: # Print last 5 collected
             print(f"Stored: {msg['timestamp']} - {msg['username']}: {msg['text']}")

        print("\n--- Preparing to stop the chat stream ---")

        # Stop the chat stream gracefully
        chat_monitor.stop()

        # Optionally, wait for the thread to completely finish
        # This ensures cleanup or final logs from the thread are processed
        chat_monitor.join(timeout=7) # Wait up to 7 seconds for it to stop cleanly

        if chat_monitor.is_running():
            print("Chat monitor thread is still alive after join timeout.")
        else:
            print("Chat monitor thread has stopped.")

        print("\nMain program finished.")

# --- Kick API helper functions ---

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

def get_kick_channel_id(username, token):
    """Fetch Kick channel ID from username"""
    url = f'https://kick.com/api/v2/channels/{username}'
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and 'id' in data:
                print(f"Found Kick channel '{username}' with ID {data['id']}")
                return str(data['id'])
            else:
                print(f"Unexpected response format for Kick channel {username}")
        else:
            print(f"Failed to fetch Kick channel ID: {response.status_code}")
        return None
    except Exception as e:
        print(f"Error fetching Kick channel ID: {e}")
        return None

def start_kick_button_callback():
    """Handle the Connect Kick Chat button click"""
    print("Connect Kick Chat Clicked")
    
    # 1. Validate inputs and authentication
    channel_name_input = dpg.get_value("user_data")
    if not channel_name_input or channel_name_input.isspace():
        dpg.set_value("error_display", "Error: Enter channel name to connect chat.")
        dpg.configure_item("error_display", color=[255, 0, 0])
        
        # We need to import this function since it's in a different module
        from api.twitch import clear_error_message_after_delay
        clear_error_message_after_delay(5)
        return
    
    # 2. Check if authenticated with Kick
    tokens = load_kick_tokens()
    if not tokens or 'access_token' not in tokens:
        print("Kick authentication tokens are missing or invalid.")
        dpg.set_value("error_display", "Error: Please authenticate with Kick first.")
        dpg.configure_item("error_display", color=[255, 0, 0])
        
        from api.twitch import clear_error_message_after_delay
        clear_error_message_after_delay(5)
        return
    
    access_token = tokens['access_token']
    
    # 3. Get channel ID from username
    channel_name = channel_name_input.strip().lower()
    channel_id = get_kick_channel_id(channel_name, access_token)
    if not channel_id:
        dpg.set_value("error_display", f"Error: Could not find Kick channel: {channel_name}")
        dpg.configure_item("error_display", color=[255, 0, 0])
        
        from api.twitch import clear_error_message_after_delay
        clear_error_message_after_delay(5)
        return
    
    # 4. Stop existing chat connection if any
    if config.kick_chat_stream and config.kick_chat_stream.is_running():
        print("Stopping existing Kick chat connection...")
        config.kick_chat_stream.stop()
        config.kick_chat_stream.join(timeout=3)
    
    # 5. Create and start new chat connection
    try:
        config.kick_chat_stream = KickChatStream(channel_id, access_token)
        success = config.kick_chat_stream.start()
        
        if success:
            # 6. Update UI
            dpg.set_value("enabled_status", f"Kick Chat Connected: {channel_name}")
            dpg.configure_item("enabled_status", color=[0, 255, 0])
            
            print(f"Successfully connected to Kick chat for channel: {channel_name}")
        else:
            dpg.set_value("error_display", "Failed to start Kick chat stream")
            dpg.configure_item("error_display", color=[255, 0, 0])
            
            from api.twitch import clear_error_message_after_delay
            clear_error_message_after_delay(5)
    except Exception as e:
        print(f"Error connecting to Kick chat: {e}")
        dpg.set_value("error_display", f"Error connecting to Kick chat: {str(e)}")
        dpg.configure_item("error_display", color=[255, 0, 0])
        
        from api.twitch import clear_error_message_after_delay
        clear_error_message_after_delay(5)