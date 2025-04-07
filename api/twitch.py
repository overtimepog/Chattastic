import time
import json
import logging
import requests
import dearpygui.dearpygui as dpg
import random

import config
from utils.auth import load_tokens
from utils.ui_utils import clear_error_message_after_delay

def handle_enter_command(username):
    if username not in config.entered_users:
        config.entered_users.append(username)
        print(f"{username} has entered!")

def _make_twitch_request(url, token, client_id, params=None):
    """ Helper to make authenticated requests to Twitch API. """
    headers = {
        'Authorization': f'Bearer {token}',
        'Client-Id': client_id
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error making Twitch API request to {url}: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response Status: {e.response.status_code}, Body: {e.response.text}")
             # Attempt to parse error message for UI feedback
             try:
                 error_json = e.response.json()
                 error_message = error_json.get("message", "Unknown API error")
                 # Schedule UI update for error message
                 if dpg.does_item_exist("error_display"):
                     dpg.set_value("error_display", f"API Error: {error_message}")
                     dpg.configure_item("error_display", color=[255, 0, 0])
                     clear_error_message_after_delay(5) # Clear after 5 seconds
             except json.JSONDecodeError:
                 pass # Ignore if response body is not JSON
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from {url}: {e}")
        return None

def _get_paginated_data(base_url, token, client_id, broadcaster_id, user_key='user_login', limit=1000, **extra_params):
    """ Fetches paginated data from Twitch API endpoints like subs, followers, vips. """
    all_items = []
    pagination_cursor = None
    params = {'broadcaster_id': broadcaster_id, 'first': 100} # Max 'first' is 100
    params.update(extra_params)

    while len(all_items) < limit:
        if pagination_cursor:
            params['after'] = pagination_cursor
        else:
            params.pop('after', None) # Ensure 'after' isn't carried over incorrectly

        data = _make_twitch_request(base_url, token, client_id, params=params)

        if data and 'data' in data:
            items = [item.get(user_key) for item in data['data'] if item.get(user_key)]
            all_items.extend(items)

            # Check for pagination cursor
            pagination_cursor = data.get('pagination', {}).get('cursor')
            if not pagination_cursor or len(data['data']) < 100: # Stop if no cursor or last page
                break
        else:
            print(f"Failed to fetch data or no 'data' field in response from {base_url}. Params: {params}")
            break # Exit loop on error or empty data

        # Safety break to avoid infinite loops if limit is very high and API behaves unexpectedly
        if 'after' not in params and pagination_cursor:
             print(f"Warning: Pagination cursor received ({pagination_cursor}) but 'after' parameter not used in next request?.")
             # This case shouldn't happen with current logic but is a safeguard

        # Add a small delay to respect rate limits, especially if fetching many pages
        time.sleep(0.1)


    return list(set(all_items)) # Return unique items


def get_all_chatters(broadcaster_id, moderator_id, token, client_id):
    """ Fetches all chatters in the channel. """
    url = f'https://api.twitch.tv/helix/chat/chatters'
    all_chatters = []
    pagination_cursor = None
    params = {'broadcaster_id': broadcaster_id, 'moderator_id': moderator_id, 'first': 1000} # Max 'first' is 1000 for chatters

    while True:
         if pagination_cursor:
             params['after'] = pagination_cursor
         else:
             params.pop('after', None)

         data = _make_twitch_request(url, token, client_id, params=params)

         if data and 'data' in data:
             chatters = [chatter['user_login'] for chatter in data['data']] # Use user_login
             all_chatters.extend(chatters)

             # Check pagination
             pagination_cursor = data.get('pagination', {}).get('cursor')
             total_expected = data.get('total', len(all_chatters)) # Use total if available

             # Exit conditions
             if not pagination_cursor or len(all_chatters) >= total_expected:
                 break
             if len(data['data']) < 1000: # Exit if last page had less than max items
                 break
         else:
             print("Failed to get chatters or empty data.")
             # Display error in UI if applicable
             if dpg.does_item_exist("error_display") and not all_chatters:
                 dpg.set_value("error_display", "Error: Could not fetch chatters list.")
                 dpg.configure_item("error_display", color=[255, 0, 0])
                 clear_error_message_after_delay(5)
             return None # Indicate failure

         time.sleep(0.1) # Small delay between pages

    return list(set(all_chatters)) # Return unique usernames


def get_vips(broadcaster_id, token, client_id):
    """ Fetches VIPs for the channel. """
    url = 'https://api.twitch.tv/helix/channels/vips'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login')

def get_moderators(broadcaster_id, token, client_id):
    """ Fetches Moderators for the channel. """
    url = 'https://api.twitch.tv/helix/moderation/moderators'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login')

def get_subscribers(broadcaster_id, token, client_id):
    """ Fetches Subscribers for the channel. """
    # IMPORTANT: Requires 'channel:read:subscriptions' scope.
    url = 'https://api.twitch.tv/helix/subscriptions'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login') # user_login from sub data


def get_followers(broadcaster_id, token, client_id):
    """ Fetches Followers for the channel. """
    # IMPORTANT: Requires 'moderator:read:followers' scope for the *moderator* token.
    # If using user token, that user needs moderator permissions on the target channel.
    url = 'https://api.twitch.tv/helix/channels/followers'
    # Followers endpoint returns 'user_login' in the 'data' objects directly
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login', moderator_id=config.TWITCH_USER_ID) # Add moderator_id if needed by scope


def get_broadcaster_id(client_id, token, channel_login):
    """ Fetches the Twitch User ID for a given channel login name. """
    url = f"https://api.twitch.tv/helix/users?login={channel_login}"
    headers = {
        'Authorization': f'Bearer {token}',
        "Client-ID": client_id,
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data and "data" in data and len(data["data"]) > 0:
            user_info = data["data"][0]
            print(f"Found channel '{user_info['login']}' with ID {user_info['id']}")
            return user_info["id"]
        else:
            print(f"Channel '{channel_login}' not found or empty data array in response.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching broadcaster ID for {channel_login}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response Status: {e.response.status_code}, Body: {e.response.text}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response for broadcaster ID {channel_login}: {e}")
        return None

# Function to get chatters' usernames and pick random ones based on filters
def get_random_filtered_chatters(channel_name, moderator_id, token, client_id, num_viewers=1, vip_only=False, mod_only=False, sub_only=False, follower_only=False):

    # 1. Get Broadcaster ID
    broadcaster_id = get_broadcaster_id(client_id, token, channel_name)
    if not broadcaster_id:
        print(f"Could not find broadcaster ID for channel: {channel_name}")
        dpg.set_value("error_display", f"Error: Channel '{channel_name}' not found.")
        dpg.configure_item("error_display", color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return None

    # 2. Get all chatters
    all_chatters = get_all_chatters(broadcaster_id, moderator_id, token, client_id)
    if all_chatters is None: # Check for None explicitly, as empty list is valid
        # Error message should be set within get_all_chatters or _make_twitch_request
        print('Failed to get chatters list.')
        return None
    if not all_chatters:
         print('No chatters found in the channel.')
         dpg.set_value("error_display", "No chatters currently in the channel.")
         dpg.configure_item("error_display", color=[255, 165, 0]) # Orange warning
         clear_error_message_after_delay(5)
         return None


    print(f"Total chatters found: {len(all_chatters)}")
    filtered_chatters = set(all_chatters) # Start with all chatters as a set for efficient filtering

    # 3. Apply Filters (if any checkbox is selected)
    any_filter_active = vip_only or mod_only or sub_only or follower_only

    if any_filter_active:
        print("Applying filters...")
        # Fetch required lists only if the corresponding filter is active
        vips = set(get_vips(broadcaster_id, token, client_id)) if vip_only else None
        mods = set(get_moderators(broadcaster_id, token, client_id)) if mod_only else None
        subs = set(get_subscribers(broadcaster_id, token, client_id)) if sub_only else None
        followers = set(get_followers(broadcaster_id, token, client_id)) if follower_only else None

        # --- Filtering Logic ---
        # Start with the set of all chatters and intersect with fetched lists based on flags

        if vip_only:
            if vips is not None:
                print(f"Filtering for VIPs ({len(vips)} found)...")
                filtered_chatters.intersection_update(vips)
            else:
                print("Failed to fetch VIPs list, cannot apply VIP filter.")
                # Optionally clear the set if VIP fetch failed and vip_only was mandatory?
                # filtered_chatters.clear()

        if mod_only:
            if mods is not None:
                print(f"Filtering for Mods ({len(mods)} found)...")
                filtered_chatters.intersection_update(mods)
            else:
                print("Failed to fetch Mods list, cannot apply Mod filter.")

        if sub_only:
            if subs is not None:
                print(f"Filtering for Subs ({len(subs)} found)...")
                filtered_chatters.intersection_update(subs)
            else:
                print("Failed to fetch Subs list, cannot apply Sub filter.")
                # Note: Free subs (Prime) might not be included depending on API/permissions

        if follower_only:
            if followers is not None:
                print(f"Filtering for Followers ({len(followers)} found)...")
                filtered_chatters.intersection_update(followers)
            else:
                print("Failed to fetch Followers list, cannot apply Follower filter.")

        print(f"Chatters remaining after filtering: {len(filtered_chatters)}")
        if not filtered_chatters:
             print('No chatters match the selected filters.')
             dpg.set_value("error_display", "No chatters match the selected criteria.")
             dpg.configure_item("error_display", color=[255, 165, 0]) # Orange warning
             clear_error_message_after_delay(5)
             return None

    # 4. Convert filtered set back to list for sampling
    final_list = list(filtered_chatters)

    # 5. Select Random Chatters
    if not final_list:
        # This case should be caught earlier, but as a safeguard
        print('No chatters available to pick from after filtering.')
        return None

    if len(final_list) < num_viewers:
        print(f"Not enough viewers ({len(final_list)}) match the criteria to pick {num_viewers}.")
        dpg.set_value("error_display", f"Only found {len(final_list)} viewers matching criteria.")
        dpg.configure_item("error_display", color=[255, 165, 0]) # Orange warning
        clear_error_message_after_delay(5)
        # Optionally pick all available if less than requested?
        num_viewers = len(final_list) # Pick all available users
        # return None # Or return None if exactly num_viewers is required

    try:
        random_chatters = random.sample(final_list, num_viewers)
    except ValueError as e:
        print(f"Error sampling viewers: {e}")
        # This shouldn't happen with the length check above, but handle defensively
        dpg.set_value("error_display", f"Error selecting random viewers.")
        dpg.configure_item("error_display", color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return None

    # 6. Update UI and return selected chatters
    print(f"Selected viewers: {random_chatters}")
    random_chatters_str = ', '.join(random_chatters)
    dpg.set_value("user_display", random_chatters_str)
    dpg.configure_item("user_display", color=[255, 255, 255], bullet=True) # White, bullet point

    config.selected_viewers = random_chatters # Update global list for viewer page

    return random_chatters # Return the list of selected users


def get_random_chatter_raffle(num_viewers=1):
    # Check if enough users have entered
    if len(config.entered_users) < num_viewers:
        print(f"Raffle Error: Not enough viewers ({len(config.entered_users)}) have entered to pick {num_viewers}.")
        dpg.set_value("error_display", f"Error: Only {len(config.entered_users)} users entered the raffle.")
        dpg.configure_item("error_display", color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return None

    # Select random viewers from entered_users
    try:
        # Use random.sample to pick unique viewers
        random_chatters = random.sample(config.entered_users, num_viewers)
    except ValueError:
        # Should be caught by the length check above, but handle defensively
        print("Error in selecting random viewers from raffle list.")
        dpg.set_value("error_display", "Error selecting raffle winners.")
        dpg.configure_item("error_display", color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return None

    # Print and display the selected viewers
    print(f"Raffle winners: {random_chatters}")
    random_chatters_str = ', '.join(random_chatters)
    dpg.set_value("user_display", random_chatters_str)
    dpg.configure_item("user_display", color=[255, 255, 255], bullet=True) # White, bullet point

    # Update the global list for the viewer page
    config.selected_viewers = random_chatters
    print("Selected viewers (for viewer page):", config.selected_viewers)

    # Clear the entered users list for the next raffle *after* selection
    print(f"Clearing {len(config.entered_users)} users from the raffle list.")
    config.entered_users.clear()
    print("The raffle is complete. Entered users list cleared.")

    return random_chatters # Return the winners


def start_twitch_button_callback():
    # This function seems intended to connect to Twitch chat for messages,
    # separate from picking random viewers. Keep its logic focused on that.
    print("Start Twitch Chat Connection Clicked (if applicable)")
    channel_name_input = dpg.get_value("user_data")
    if not channel_name_input or channel_name_input.isspace():
        dpg.set_value("error_display", "Error: Enter channel name to connect chat.")
        dpg.configure_item("error_display", color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return

    if not config.IS_AUTHENTICATED:
         dpg.set_value("error_display", "Error: Authenticate first to connect chat.")
         dpg.configure_item("error_display", color=[255, 0, 0])
         clear_error_message_after_delay(5)
         return

    # Add logic here to connect to Twitch chat using IRC if needed for TTS or raffle entries
    # Example:
    # if is_chat_connected(): # Function to check connection status
    #     print("Chat already connected.")
    #     # Optionally disconnect/reconnect or just update status
    #     # stop_chat_connection()
    #
    # print(f"Attempting to connect to Twitch chat for channel: {channel_name_input.strip().lower()}")
    # start_chat_connection(channel_name_input.strip().lower(), load_tokens()['access_token']) # Pass necessary details
    # Update UI element (e.g., 'enabled' button/text) based on connection success/failure
