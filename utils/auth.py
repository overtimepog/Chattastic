import os
import json
import logging
import requests
import traceback
import base64
import hashlib
import urllib.parse
import secrets
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

import config
import globals # For WebSocket manager access

# Configure logging (can inherit from app or define specifically)
logger = logging.getLogger(__name__)

router = APIRouter()

# --- Token Management ---

def save_tokens(access_token, refresh_token, user_id, user_name):
    """Saves Twitch tokens to the file."""
    try:
        with open(config.TOKEN_FILE, 'w') as file:
            json.dump({'access_token': access_token, 'refresh_token': refresh_token, 'user_id': user_id, 'user_name': user_name}, file)
        logger.info(f"Twitch tokens saved for user {user_name} ({user_id}).")
    except IOError as e:
        logger.error(f"Error saving Twitch tokens to {config.TOKEN_FILE}: {e}")

def load_tokens():
    """Loads Twitch tokens from the file."""
    if os.path.exists(config.TOKEN_FILE):
        try:
            with open(config.TOKEN_FILE, 'r') as file:
                tokens = json.load(file)
                # Basic validation
                if tokens and 'access_token' in tokens and 'refresh_token' in tokens and 'user_id' in tokens:
                     # Optionally validate token expiry here if timestamp is stored
                    return tokens
                else:
                    logger.warning(f"Twitch token file {config.TOKEN_FILE} is missing required fields.")
                    # Optionally delete invalid file
                    # os.remove(config.TOKEN_FILE)
                    return None
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {config.TOKEN_FILE}. File might be corrupted.")
            # Optionally delete corrupted file
            # os.remove(config.TOKEN_FILE)
            return None
        except IOError as e:
            logger.error(f"Error reading Twitch token file {config.TOKEN_FILE}: {e}")
            return None
    return None

def save_kick_token(access_token):
    """Saves Kick token to the file."""
    try:
        with open(config.KICK_TOKEN_FILE, 'w') as f:
            json.dump({'access_token': access_token}, f)
        logger.info(f"Kick token saved to {config.KICK_TOKEN_FILE}")
    except IOError as e:
        logger.error(f"Error saving Kick token to {config.KICK_TOKEN_FILE}: {e}")


def load_kick_tokens():
    """Loads Kick tokens from the file."""
    if os.path.exists(config.KICK_TOKEN_FILE):
        try:
            with open(config.KICK_TOKEN_FILE, 'r') as file:
                tokens = json.load(file)
                if tokens and 'access_token' in tokens:
                    # No refresh token in Kick PKCE flow typically
                    config.KICK_IS_AUTHENTICATED = True # Update status on load
                    return tokens
                else:
                    logger.warning(f"Kick token file {config.KICK_TOKEN_FILE} is missing access_token.")
                    # os.remove(config.KICK_TOKEN_FILE)
                    return None
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from {config.KICK_TOKEN_FILE}. File might be corrupted.")
            # os.remove(config.KICK_TOKEN_FILE)
            return None
        except IOError as e:
            logger.error(f"Error reading Kick token file {config.KICK_TOKEN_FILE}: {e}")
            return None
    return None

# --- Helper Functions ---

async def broadcast_auth_status():
    """Broadcasts the current authentication status via WebSocket."""
    if globals.manager:
        status_message = {
            "type": "status_update",
            "data": {
                "twitch_authenticated": config.IS_AUTHENTICATED,
                "kick_authenticated": config.KICK_IS_AUTHENTICATED,
                "twitch_channel": config.selected_channel, # Or get dynamically if needed
                "kick_channel": config.kick_channel_name
            }
        }
        await globals.manager.broadcast(json.dumps(status_message))
    else:
        logger.warning("WebSocket manager not available for broadcasting auth status.")

def get_twitch_user_info(access_token):
    """Gets user ID and username from Twitch using the access token."""
    headers = {'Authorization': f'Bearer {access_token}', 'Client-Id': config.CLIENT_ID}
    try:
        response = requests.get('https://id.twitch.tv/oauth2/validate', headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        user_id = data.get('user_id')
        user_name = data.get('login')
        if user_id and user_name:
            logger.info(f"Twitch token validation successful: User ID={user_id}, Username={user_name}")
            return user_id, user_name
        else:
            logger.error("Failed to validate Twitch token: 'user_id' or 'login' not found in response.")
            return None, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to validate Twitch token: {e}")
        return None, None
    except json.JSONDecodeError:
        logger.error("Failed to parse Twitch validation response.")
        return None, None


# --- Twitch Authentication ---

@router.get("/twitch/login")
async def twitch_login():
    """Redirects the user to Twitch for authentication."""
    # Ensure config.AUTH_URL is correctly formatted
    logger.info("Redirecting user to Twitch for authentication.")
    return RedirectResponse(url=config.AUTH_URL)

@router.get("/twitch/callback") # Path should match config.REDIRECT_URI path
async def twitch_callback(request: Request, code: str = None, error: str = None, error_description: str = None):
    """Handles the callback from Twitch after authentication attempt."""
    if error:
        logger.error(f"Twitch authentication failed: {error} - {error_description}")
        return HTMLResponse(content=f"<html><body><h1>Twitch Authentication Failed</h1><p>{error}: {error_description}</p><p>You can close this window.</p></body></html>", status_code=400)

    if not code:
        logger.error("Twitch authentication failed: No authorization code received.")
        return HTMLResponse(content="<html><body><h1>Twitch Authentication Failed</h1><p>No authorization code received from Twitch.</p><p>You can close this window.</p></body></html>", status_code=400)

    logger.info("Received Twitch authorization code. Exchanging for tokens...")
    token_url = "https://id.twitch.tv/oauth2/token"
    payload = {
        'client_id': config.CLIENT_ID,
        'client_secret': config.CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': config.REDIRECT_URI # Must match exactly what was sent in login
    }

    try:
        response = requests.post(token_url, data=payload, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        token_data = response.json()

        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')

        if access_token and refresh_token:
            logger.info("Twitch access and refresh tokens obtained.")
            user_id, user_name = get_twitch_user_info(access_token)
            if user_id and user_name:
                save_tokens(access_token, refresh_token, user_id, user_name)
                config.TWITCH_USER_ID = user_id
                config.IS_AUTHENTICATED = True
                logger.info("Twitch authentication successful.")
                await broadcast_auth_status()
                return HTMLResponse(content="<html><body><h1>Twitch Authentication Successful!</h1><p>You can close this window now.</p><script>window.close();</script></body></html>")
            else:
                logger.error("Twitch authentication failed: Could not retrieve User ID or User Name after getting tokens.")
                config.IS_AUTHENTICATED = False
                await broadcast_auth_status()
                return HTMLResponse(content="<html><body><h1>Twitch Authentication Failed</h1><p>Could not verify user details after obtaining tokens.</p><p>You can close this window.</p></body></html>", status_code=500)
        else:
            logger.error("Twitch authentication failed: Missing tokens in response from Twitch.")
            config.IS_AUTHENTICATED = False
            await broadcast_auth_status()
            return HTMLResponse(content="<html><body><h1>Twitch Authentication Failed</h1><p>Did not receive valid tokens from Twitch.</p><p>You can close this window.</p></body></html>", status_code=500)

    except requests.exceptions.RequestException as e:
        logger.error(f"Twitch token exchange failed. Request error: {e}")
        config.IS_AUTHENTICATED = False
        await broadcast_auth_status()
        return HTMLResponse(content=f"<html><body><h1>Twitch Authentication Failed</h1><p>Error communicating with Twitch: {e}</p><p>You can close this window.</p></body></html>", status_code=502) # Bad Gateway
    except json.JSONDecodeError:
        logger.error("Failed to parse Twitch token response.")
        config.IS_AUTHENTICATED = False
        await broadcast_auth_status()
        return HTMLResponse(content="<html><body><h1>Twitch Authentication Failed</h1><p>Invalid response received from Twitch.</p><p>You can close this window.</p></body></html>", status_code=502)
    except Exception as e:
        logger.error(f"An unexpected error occurred during Twitch authentication: {e}", exc_info=True)
        config.IS_AUTHENTICATED = False
        await broadcast_auth_status()
        return HTMLResponse(content="<html><body><h1>Twitch Authentication Failed</h1><p>An unexpected error occurred.</p><p>You can close this window.</p></body></html>", status_code=500)


# --- Kick Authentication (PKCE Flow) ---

# Temporary storage for PKCE verifiers (In a real multi-user app, use a proper session store)
pkce_storage = {}

def generate_pkce_codes():
    """Generates PKCE code_verifier and code_challenge."""
    verifier = base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8').rstrip('=')
    challenge_bytes = hashlib.sha256(verifier.encode('utf-8')).digest()
    challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')
    return verifier, challenge

@router.get("/kick/login")
async def kick_login():
    """Generates PKCE codes, stores verifier, and redirects user to Kick."""
    state = secrets.token_hex(16)
    verifier, challenge = generate_pkce_codes()

    # Store the verifier associated with the state (simple dict for now)
    pkce_storage[state] = verifier
    logger.debug(f"Stored PKCE verifier for state: {state}")

    params = {
        'client_id': config.KICK_CLIENT_ID,
        'redirect_uri': config.KICK_REDIRECT_URI, # Must match exactly
        'response_type': 'code',
        'scope': 'chat:write chat:read channel:read user:read events:subscribe', # Adjust scopes as needed
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256'
    }
    kick_auth_url = f"https://id.kick.com/oauth/authorize?{urllib.parse.urlencode(params)}"
    logger.info("Redirecting user to Kick for authentication.")
    return RedirectResponse(url=kick_auth_url)


@router.get("/kick/callback") # Path should match config.KICK_REDIRECT_URI path
async def kick_callback(request: Request, code: str = None, state: str = None, error: str = None, error_description: str = None):
    """Handles the callback from Kick after authentication attempt."""
    if error:
        logger.error(f"Kick authentication failed: {error} - {error_description}")
        return HTMLResponse(content=f"<html><body><h1>Kick Authentication Failed</h1><p>{error}: {error_description}</p><p>You can close this window.</p></body></html>", status_code=400)

    # Retrieve the verifier using the state
    verifier = pkce_storage.pop(state, None)
    logger.debug(f"Retrieved PKCE verifier for state {state}: {'Found' if verifier else 'Not Found'}")


    if not code or not state or not verifier:
        err_msg = "Kick authentication failed: Missing code, state, or verifier mismatch."
        logger.error(err_msg)
        # Ensure state is removed if it exists but code/verifier is missing
        if state in pkce_storage: pkce_storage.pop(state)
        return HTMLResponse(content=f"<html><body><h1>Kick Authentication Failed</h1><p>{err_msg}</p><p>You can close this window.</p></body></html>", status_code=400)

    logger.info("Received Kick authorization code. Exchanging for token...")
    token_url = "https://id.kick.com/oauth/token"
    data = {
        'grant_type': 'authorization_code',
        'client_id': config.KICK_CLIENT_ID,
        'client_secret': config.KICK_CLIENT_SECRET,
        'code': code,
        'redirect_uri': config.KICK_REDIRECT_URI, # Must match exactly
        'code_verifier': verifier
    }

    try:
        response = requests.post(token_url, data=data, timeout=15) # Increased timeout slightly
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get('access_token')

        if access_token:
            logger.info("Kick access token obtained.")
            save_kick_token(access_token)
            config.KICK_IS_AUTHENTICATED = True
            # TODO: Optionally get Kick user ID/name if needed via another API call
            # config.KICK_USER_ID = get_kick_user_id(access_token) # Placeholder
            logger.info("Kick authentication successful.")
            await broadcast_auth_status()
            return HTMLResponse(content="<html><body><h1>Kick Authentication Successful!</h1><p>You can close this window now.</p><script>window.close();</script></body></html>")
        else:
            logger.error("Kick authentication failed: Missing access_token in response.")
            config.KICK_IS_AUTHENTICATED = False
            await broadcast_auth_status()
            return HTMLResponse(content="<html><body><h1>Kick Authentication Failed</h1><p>Did not receive a valid token from Kick.</p><p>You can close this window.</p></body></html>", status_code=500)

    except requests.exceptions.RequestException as e:
        logger.error(f"Kick token exchange failed. Request error: {e}")
        config.KICK_IS_AUTHENTICATED = False
        await broadcast_auth_status()
        return HTMLResponse(content=f"<html><body><h1>Kick Authentication Failed</h1><p>Error communicating with Kick: {e}</p><p>You can close this window.</p></body></html>", status_code=502)
    except json.JSONDecodeError:
        logger.error("Failed to parse Kick token response.")
        config.KICK_IS_AUTHENTICATED = False
        await broadcast_auth_status()
        return HTMLResponse(content="<html><body><h1>Kick Authentication Failed</h1><p>Invalid response received from Kick.</p><p>You can close this window.</p></body></html>", status_code=502)
    except Exception as e:
        logger.error(f"An unexpected error occurred during Kick authentication: {e}", exc_info=True)
        config.KICK_IS_AUTHENTICATED = False
        await broadcast_auth_status()
        return HTMLResponse(content="<html><body><h1>Kick Authentication Failed</h1><p>An unexpected error occurred.</p><p>You can close this window.</p></body></html>", status_code=500)


# --- Logout / Cancel ---

@router.post("/logout")
async def logout():
    """Clears authentication status and tokens for both platforms."""
    logger.info("Processing logout request.")
    config.IS_AUTHENTICATED = False
    config.KICK_IS_AUTHENTICATED = False
    config.TWITCH_USER_ID = None
    config.KICK_USER_ID = None # Reset Kick user ID if stored

    # Attempt to delete the tokens files
    for token_file in [config.TOKEN_FILE, config.KICK_TOKEN_FILE]:
        if os.path.exists(token_file):
            try:
                os.remove(token_file)
                logger.info(f"Deleted token file: {token_file}")
            except OSError as e:
                logger.error(f"Error deleting token file {token_file}: {e}")

    await broadcast_auth_status()
    return {"message": "Logout successful, tokens cleared."}


# --- Initialization ---
# Load tokens on startup (can be called from app.py)
def initialize_auth():
    logger.info("Initializing authentication state...")
    twitch_tokens = load_tokens()
    if twitch_tokens:
        # TODO: Add token validation/refresh logic here if needed
        # For now, just assume loaded token means authenticated
        config.IS_AUTHENTICATED = True
        config.TWITCH_USER_ID = twitch_tokens.get('user_id')
        logger.info(f"Twitch user {twitch_tokens.get('user_name')} loaded.")
    else:
        config.IS_AUTHENTICATED = False

    kick_tokens = load_kick_tokens()
    if kick_tokens:
        # Kick tokens don't usually expire quickly or have refresh in PKCE
        config.KICK_IS_AUTHENTICATED = True
        # TODO: Load/validate Kick user ID if needed
        logger.info("Kick token loaded.")
    else:
        config.KICK_IS_AUTHENTICATED = False

    # No need to broadcast here, initial status sent on WebSocket connect

# Call initialization when this module is loaded
# initialize_auth() # Or call this explicitly from app.py after globals.manager is set
