import sys
import asyncio

# Set the event loop policy for Windows compatibility FIRST
if sys.platform == "win32":
    print("Setting Windows event loop policy for compatibility in twitch.py...")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import time
import json
import logging
import requests
import random
from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel
from typing import List, Optional

import config
import globals # For WebSocket manager access
from utils.auth import load_tokens # Keep token loading

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Helper Functions ---

async def broadcast_error(message: str):
    """Broadcasts an error message via WebSocket."""
    if globals.manager:
        error_message = {
            "type": "error",
            "data": {"message": f"Twitch API Error: {message}"}
        }
        await globals.manager.broadcast(json.dumps(error_message))
    else:
        logger.warning("WebSocket manager not available for broadcasting error.")

async def broadcast_viewer_update():
    """Broadcasts the current viewer lists (all and selected)."""
    if globals.manager:
        viewer_update = {
            "type": "viewer_list_update",
            "data": {"viewers": config.viewers_list} # Assuming config.viewers_list holds all viewers
        }
        selected_update = {
            "type": "selected_viewers_update",
            "data": {"selected_viewers": config.selected_viewers}
        }
        # Use asyncio.gather to send concurrently if desired, or send sequentially
        await globals.manager.broadcast(json.dumps(viewer_update))
        await globals.manager.broadcast(json.dumps(selected_update))
    else:
        logger.warning("WebSocket manager not available for broadcasting viewer updates.")


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
        error_message = f"Error making Twitch API request to {url}: {e}"
        logger.error(error_message)
        if hasattr(e, 'response') and e.response is not None:
             logger.error(f"Response Status: {e.response.status_code}, Body: {e.response.text}")
             # Try to extract a more specific message
             try:
                 error_json = e.response.json()
                 api_error = error_json.get("message", "Unknown API error")
                 error_message = f"Twitch API Error ({e.response.status_code}): {api_error}"
             except json.JSONDecodeError:
                 pass # Use the original error message
        # Schedule the error broadcast in the event loop
        asyncio.create_task(broadcast_error(str(e))) # Broadcast the exception string
        return None
    except json.JSONDecodeError as e:
        error_message = f"Error decoding JSON response from {url}: {e}"
        logger.error(error_message)
        asyncio.create_task(broadcast_error(f"Invalid response from Twitch API: {url}"))
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
            params.pop('after', None)

        data = _make_twitch_request(base_url, token, client_id, params=params)

        if data and 'data' in data:
            items = [item.get(user_key) for item in data['data'] if item.get(user_key)]
            all_items.extend(items)
            pagination_cursor = data.get('pagination', {}).get('cursor')
            if not pagination_cursor or len(data['data']) < 100:
                break
        else:
            logger.warning(f"Failed to fetch data or no 'data' field in response from {base_url}. Params: {params}")
            break

        time.sleep(0.1) # Respect rate limits

    return list(set(all_items))

def get_broadcaster_id(client_id, token, channel_login):
    """ Fetches the Twitch User ID for a given channel login name. """
    url = f"https://api.twitch.tv/helix/users?login={channel_login}"
    data = _make_twitch_request(url, token, client_id)
    if data and "data" in data and len(data["data"]) > 0:
        user_info = data["data"][0]
        logger.info(f"Found channel '{user_info['login']}' with ID {user_info['id']}")
        return user_info["id"]
    else:
        logger.warning(f"Channel '{channel_login}' not found or empty data array in response.")
        asyncio.create_task(broadcast_error(f"Twitch channel '{channel_login}' not found."))
        return None

def get_all_chatters(broadcaster_id, moderator_id, token, client_id):
    """ Fetches all chatters in the channel. """
    url = 'https://api.twitch.tv/helix/chat/chatters'
    all_chatters = []
    pagination_cursor = None
    params = {'broadcaster_id': broadcaster_id, 'moderator_id': moderator_id, 'first': 1000}

    while True:
         if pagination_cursor:
             params['after'] = pagination_cursor
         else:
             params.pop('after', None)

         data = _make_twitch_request(url, token, client_id, params=params)

         if data and 'data' in data:
             chatters = [chatter['user_login'] for chatter in data['data']]
             all_chatters.extend(chatters)
             pagination_cursor = data.get('pagination', {}).get('cursor')
             total_expected = data.get('total', len(all_chatters))
             if not pagination_cursor or len(all_chatters) >= total_expected or len(data['data']) < 1000:
                 break
         else:
             logger.warning("Failed to get chatters or empty data.")
             if not all_chatters: # Only broadcast error if we got nothing at all
                 asyncio.create_task(broadcast_error("Could not fetch Twitch chatters list."))
                 return None # Indicate failure
             else: # If we got some pages but then failed, return what we have
                 logger.warning("Returning partial chatters list due to API error.")
                 break

         time.sleep(0.1)

    unique_chatters = list(set(all_chatters))
    config.viewers_list = unique_chatters # Update global list
    asyncio.create_task(broadcast_viewer_update()) # Broadcast update
    return unique_chatters


def get_vips(broadcaster_id, token, client_id):
    url = 'https://api.twitch.tv/helix/channels/vips'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login')

def get_moderators(broadcaster_id, token, client_id):
    url = 'https://api.twitch.tv/helix/moderation/moderators'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login')

def get_subscribers(broadcaster_id, token, client_id):
    url = 'https://api.twitch.tv/helix/subscriptions'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login')

def get_followers(broadcaster_id, token, client_id, moderator_id):
    url = 'https://api.twitch.tv/helix/channels/followers'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login', moderator_id=moderator_id)


# --- API Endpoints ---

class SelectViewersRequest(BaseModel):
    channel_name: str
    num_viewers: int = 1
    vip_only: bool = False
    mod_only: bool = False
    sub_only: bool = False
    follower_only: bool = False
    use_raffle: bool = False # Add flag for raffle mode

@router.post("/select-viewers")
async def select_viewers_endpoint(request_data: SelectViewersRequest):
    """API endpoint to select random viewers based on criteria or raffle."""
    tokens = load_tokens()
    if not tokens or not config.IS_AUTHENTICATED:
        raise HTTPException(status_code=401, detail="Twitch authentication required.")

    token = tokens['access_token']
    client_id = config.CLIENT_ID
    moderator_id = config.TWITCH_USER_ID # Authenticated user's ID

    if request_data.use_raffle:
        # --- Raffle Logic ---
        logger.info(f"Starting raffle selection for {request_data.num_viewers} winners.")
        if len(config.entered_users) < request_data.num_viewers:
            error_msg = f"Raffle Error: Not enough viewers ({len(config.entered_users)}) have entered to pick {request_data.num_viewers}."
            logger.warning(error_msg)
            await broadcast_error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        try:
            winners = random.sample(config.entered_users, request_data.num_viewers)
        except ValueError as e:
            error_msg = f"Error selecting raffle winners: {e}"
            logger.error(error_msg)
            await broadcast_error("Internal error selecting raffle winners.")
            raise HTTPException(status_code=500, detail="Error selecting raffle winners.")

        logger.info(f"Raffle winners: {winners}")
        config.selected_viewers = winners # Update global selected list
        # Clear raffle list *after* selection
        logger.info(f"Clearing {len(config.entered_users)} users from the raffle list.")
        config.entered_users.clear()
        # Broadcast updates
        await broadcast_viewer_update() # This sends both selected and all (all might be unchanged here)
        return {"selected_viewers": winners}

    else:
        # --- Filtered Chatter Logic ---
        logger.info(f"Starting filtered viewer selection for channel '{request_data.channel_name}'.")
        broadcaster_id = get_broadcaster_id(client_id, token, request_data.channel_name)
        if not broadcaster_id:
            # Error already broadcast by get_broadcaster_id
            raise HTTPException(status_code=404, detail=f"Twitch channel '{request_data.channel_name}' not found.")

        all_chatters = get_all_chatters(broadcaster_id, moderator_id, token, client_id)
        if all_chatters is None:
            raise HTTPException(status_code=500, detail="Failed to fetch chatters list.")
        if not all_chatters:
            await broadcast_error("No chatters currently in the channel.")
            raise HTTPException(status_code=404, detail="No chatters found in the channel.")

        logger.info(f"Total chatters found: {len(all_chatters)}")
        filtered_chatters = set(all_chatters)
        any_filter_active = request_data.vip_only or request_data.mod_only or request_data.sub_only or request_data.follower_only

        if any_filter_active:
            logger.info("Applying filters...")
            # Fetch lists only if needed
            vips = set(get_vips(broadcaster_id, token, client_id)) if request_data.vip_only else None
            mods = set(get_moderators(broadcaster_id, token, client_id)) if request_data.mod_only else None
            subs = set(get_subscribers(broadcaster_id, token, client_id)) if request_data.sub_only else None
            followers = set(get_followers(broadcaster_id, token, client_id, moderator_id)) if request_data.follower_only else None # Pass moderator_id

            # Apply intersections
            if request_data.vip_only and vips is not None: filtered_chatters.intersection_update(vips)
            if request_data.mod_only and mods is not None: filtered_chatters.intersection_update(mods)
            if request_data.sub_only and subs is not None: filtered_chatters.intersection_update(subs)
            if request_data.follower_only and followers is not None: filtered_chatters.intersection_update(followers)

            logger.info(f"Chatters remaining after filtering: {len(filtered_chatters)}")
            if not filtered_chatters:
                msg = "No chatters match the selected filters."
                logger.warning(msg)
                await broadcast_error(msg)
                raise HTTPException(status_code=404, detail=msg)

        final_list = list(filtered_chatters)
        num_to_select = request_data.num_viewers

        if len(final_list) < num_to_select:
            msg = f"Not enough viewers ({len(final_list)}) match criteria to pick {num_to_select}. Selecting all available."
            logger.warning(msg)
            await broadcast_error(msg)
            num_to_select = len(final_list) # Select all available

        if num_to_select == 0:
             msg = "No viewers available to select after filtering."
             logger.warning(msg)
             # await broadcast_error(msg) # Already handled by filter check
             raise HTTPException(status_code=404, detail=msg)


        try:
            selected = random.sample(final_list, num_to_select)
        except ValueError as e:
            error_msg = f"Error sampling viewers: {e}"
            logger.error(error_msg)
            await broadcast_error("Internal error selecting random viewers.")
            raise HTTPException(status_code=500, detail="Error selecting random viewers.")

        logger.info(f"Selected viewers: {selected}")
        config.selected_viewers = selected # Update global list
        await broadcast_viewer_update() # Broadcast changes
        return {"selected_viewers": selected}

# Placeholder for chat connection logic (requires IRC library like twitchio)
# This would likely be triggered via WebSocket message, not a direct API call.
# Example structure:
# async def connect_twitch_chat(channel_name: str):
#     if not config.IS_AUTHENTICATED:
#         await broadcast_error("Cannot connect chat: Twitch not authenticated.")
#         return
#     tokens = load_tokens()
#     if not tokens:
#         await broadcast_error("Cannot connect chat: Missing Twitch tokens.")
#         return
#
#     logger.info(f"Attempting to connect to Twitch chat for channel: {channel_name}")
#     # --- Add twitchio or similar IRC connection logic here ---
#     # Example using a hypothetical ChatManager class:
#     # await chat_manager.connect(channel_name, tokens['access_token'])
#     # On successful connection:
#     config.selected_channel = channel_name
#     await broadcast_auth_status() # Update UI with channel name
#     # On message received (from IRC library callback):
#     #   message_data = {"type": "twitch_chat_message", "data": {"channel": channel, "user": user, "text": text}}
#     #   await globals.manager.broadcast(json.dumps(message_data))
#     # On error:
#     #   await broadcast_error(f"Failed to connect to Twitch chat for {channel_name}")

# Placeholder for handling !enter command (would come from IRC listener)
# def handle_enter_command(username):
#    if username not in config.entered_users:
#        config.entered_users.append(username)
#        logger.info(f"Raffle entry: {username}")
#        # Optionally broadcast raffle entry confirmation?
#        # await broadcast_raffle_entry(username)


# TODO: Add endpoint or WS handler to disconnect chat
# TODO: Add endpoint or WS handler to trigger TTS for selected viewers (in audio.py)
