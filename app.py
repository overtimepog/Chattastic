

import asyncio
import os
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import config  # Assuming config.py holds necessary configurations
import globals # Import the globals module
import json # Add json import for message handling

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files directories (for HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="ui"), name="static")
app.mount("/static-assets", StaticFiles(directory="static"), name="static-assets")

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._broadcast_lock = asyncio.Lock()
        self._screenshot_queue = asyncio.Queue()
        self._chat_queue = asyncio.Queue()
        # Start the broadcast workers
        asyncio.create_task(self._screenshot_broadcast_worker())
        asyncio.create_task(self._chat_broadcast_worker())

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected: {websocket.client}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message to {websocket.client}: {e}")
            # Disconnect problematic client
            self.disconnect(websocket)

    async def broadcast(self, message: str):
        # Parse the message to determine its type
        try:
            msg_data = json.loads(message)
            msg_type = msg_data.get("type", "")

            # Route screenshot updates to the high-priority queue
            if msg_type == "screenshot_update" or "desktop_view" in msg_type:
                await self._screenshot_queue.put(message)
            # Route chat messages to the regular queue
            elif msg_type == "kick_chat_message" or "twitch_chat_message" in msg_type:
                await self._chat_queue.put(message)
            # All other messages go through the immediate broadcast
            else:
                await self._direct_broadcast(message)
        except json.JSONDecodeError:
            # If we can't parse the message, just broadcast it directly
            await self._direct_broadcast(message)

    async def _direct_broadcast(self, message: str):
        """Immediately broadcast a message to all connections."""
        async with self._broadcast_lock:
            # Only log non-screenshot messages
            if 'screenshot_update' not in message and 'desktop_view' not in message:
                logger.debug(f"Direct broadcasting message: {message[:100]}...")
            for connection in self.active_connections.copy():  # Use copy to avoid modification during iteration
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"Error sending message to {connection.client}: {e}")
                    # Disconnect problematic clients
                    self.disconnect(connection)

    async def _screenshot_broadcast_worker(self):
        """Worker that processes screenshot messages with high priority."""
        while True:
            try:
                message = await self._screenshot_queue.get()
                await self._direct_broadcast(message)
                self._screenshot_queue.task_done()
            except Exception as e:
                logger.error(f"Error in screenshot broadcast worker: {e}")
                await asyncio.sleep(0.1)

    async def _chat_broadcast_worker(self):
        """Worker that processes chat messages with normal priority."""
        while True:
            try:
                message = await self._chat_queue.get()
                await self._direct_broadcast(message)
                self._chat_queue.task_done()
                # Small delay to allow screenshot messages to be processed
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Error in chat broadcast worker: {e}")
                await asyncio.sleep(0.1)

# Create the manager instance and assign it to the globals module
globals.manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def get_root(code: str = None, state: str = None):
    # Check if this is a Kick callback (code and state parameters are present)
    if code and state:
        logger.info(f"Detected Kick callback at root route with code and state parameters")
        # Forward to the Kick callback handler
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"/api/auth/kick/callback?code={code}&state={state}")

    # If not a callback, serve the main HTML file
    # Assuming index.html is in the 'ui' directory
    try:
        with open("ui/index.html", "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        logger.error("ui/index.html not found.")
        return HTMLResponse(content="<html><body><h1>Error: index.html not found</h1></body></html>", status_code=404)
    except Exception as e:
        logger.error(f"Error reading ui/index.html: {e}")
        return HTMLResponse(content="<html><body><h1>Internal Server Error</h1></body></html>", status_code=500)


# Placeholder for API routers (to be added later)
# from api import twitch, kick
# Import and include routers
from utils import auth as auth_router # Rename to avoid conflict
from api import twitch as twitch_api # Import the refactored twitch api module
from api import kick as kick_api # Import the refactored kick api module
from api import docker as docker_api # Import the Docker API module
from api import screenshot as screenshot_api # Import the screenshot module
from api import settings as settings_module # Import the settings module
from api import settings_api # Import the settings API router
# TODO: Import audio utils if needed for TTS trigger
# from utils import audio as audio_utils

app.include_router(auth_router.router, prefix="/api/auth", tags=["authentication"])
app.include_router(twitch_api.router, prefix="/api/twitch", tags=["twitch"]) # Include Twitch API router
app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"]) # Include Settings API router
# Kick API doesn't have a router, control functions are called directly

# --- WebSocket Message Handling ---
async def handle_ws_message(websocket: WebSocket, message: dict):
    """Processes incoming WebSocket messages."""
    msg_type = message.get("type")
    msg_data = message.get("data", {})
    logger.info(f"Processing WebSocket message type: {msg_type}")

    try:
        if msg_type == "get_initial_status":
            # Resend initial status on explicit request
            # Load current settings
            current_settings = settings_module.load_settings()

            initial_status = {
                "type": "initial_status",
                "data": {
                    "twitch_authenticated": config.IS_AUTHENTICATED,
                    "kick_authenticated": config.KICK_IS_AUTHENTICATED,
                    "twitch_channel": config.selected_channel,
                    "kick_channel": config.kick_channel_name,
                    "kick_connected": config.kick_chat_connected,
                    "raffle_entries_count": len(config.entered_users),
                    "settings": current_settings,
                    # Add twitch connected status if implemented
                }
            }
            logger.info(f"Sending initial status: Twitch={config.IS_AUTHENTICATED}, Kick={config.KICK_IS_AUTHENTICATED}")
            await globals.manager.send_personal_message(json.dumps(initial_status), websocket)

        elif msg_type == "connect_twitch_chat":
            channel = msg_data.get("channel")
            if channel:
                # TODO: Implement and call twitch_api.connect_twitch_chat(channel)
                logger.warning("Twitch chat connection not yet implemented.")
                await globals.manager.send_personal_message(json.dumps({"type": "error", "data": {"message": "Twitch chat connection not implemented"}}), websocket)
            else:
                logger.warning("Connect Twitch chat request missing channel name.")
                await globals.manager.send_personal_message(json.dumps({"type": "error", "data": {"message": "Missing channel name for Twitch connect"}}), websocket)

        elif msg_type == "connect_kick_chat":
            channel = msg_data.get("channel")
            if channel:
                await kick_api.connect_kick_chat(channel) # Call the async function
            else:
                logger.warning("Connect Kick chat request missing channel name.")
                await globals.manager.send_personal_message(json.dumps({"type": "error", "data": {"message": "Missing channel name for Kick connect"}}), websocket)

        elif msg_type == "disconnect_twitch_chat":
             # TODO: Implement and call twitch_api.disconnect_twitch_chat()
             logger.warning("Twitch chat disconnection not yet implemented.")
             await globals.manager.send_personal_message(json.dumps({"type": "error", "data": {"message": "Twitch chat disconnect not implemented"}}), websocket)

        elif msg_type == "disconnect_kick_chat":
             await kick_api.disconnect_kick_chat() # Call the async function

        elif msg_type == "get_docker_containers":
            # Get Docker containers and send to client
            containers = await docker_api.get_containers()
            await globals.manager.send_personal_message(json.dumps({
                "type": "docker_containers",
                "data": {"containers": containers}
            }), websocket)

        elif msg_type == "stream_docker_logs":
            container_id = msg_data.get("container_id")
            if container_id:
                # Start streaming logs for the container
                # This will continue until the WebSocket is closed
                await docker_api.stream_container_logs(container_id, websocket)
            else:
                logger.warning("Stream Docker logs request missing container ID.")
                await globals.manager.send_personal_message(json.dumps({
                    "type": "error",
                    "data": {"message": "Missing container ID for Docker logs"}
                }), websocket)

        elif msg_type == "select_random_viewers":
            count = msg_data.get("count", 1)
            use_raffle = msg_data.get("use_raffle", False)
            platform = msg_data.get("platform", "twitch")

            logger.info(f"Selecting {count} random viewers from {platform} with use_raffle={use_raffle}")

            if platform.lower() == "kick":
                if not config.kick_chat_connected:
                    await globals.manager.send_personal_message(json.dumps({
                        "type": "error",
                        "data": {"message": "Not connected to Kick chat"}
                    }), websocket)
                    return

                # Select random viewers from Kick chat
                selected_viewers = await kick_api.select_random_kick_viewers(count, use_raffle)
                if selected_viewers:
                    # Update global selected viewers list
                    config.selected_viewers = selected_viewers
                    # Broadcast the selected viewers
                    await globals.manager.broadcast(json.dumps({
                        "type": "selected_viewers_update",
                        "data": {"selected_viewers": selected_viewers}
                    }))
            else:  # Default to Twitch
                # This is handled by the POST endpoint in twitch_api
                logger.info("Twitch viewer selection should use POST /api/twitch/select-viewers endpoint.")
                await globals.manager.send_personal_message(json.dumps({
                    "type": "error",
                    "data": {"message": "Use POST /api/twitch/select-viewers endpoint for Twitch"}
                }), websocket)


        elif msg_type == "trigger_speak_selected":
            # TODO: Implement TTS triggering
            logger.warning("TTS triggering not yet implemented.")
            # Example: await audio_utils.speak_messages_for_selected_viewers()
            await globals.manager.send_personal_message(json.dumps({"type": "info", "data": {"message": "TTS triggering not implemented"}}), websocket)

        elif msg_type == "clear_raffle_entries":
            logger.info("Clearing raffle entries")
            config.entered_users.clear()
            await globals.manager.broadcast(json.dumps({
                "type": "raffle_entries_cleared",
                "data": {"message": "Raffle entries cleared"}
            }))

        # --- Handle Control Messages for Kick Overlay ---
        elif msg_type == "control_kick_overlay":
            action = msg_data.get("action")
            logger.info(f"Received Kick overlay control: action={action}, data={msg_data}")
            command_data = {"command": action} # Base command data

            # Handle different actions
            if action == "set_limit":
                value = msg_data.get("value")
                if isinstance(value, int):
                    command_data["limit"] = value
                else:
                    logger.warning(f"Invalid value for set_limit: {value}")
                    return # Don't broadcast invalid command
            elif action == "clear":
                pass # No extra data needed
            elif action == "set_layout":
                flow = msg_data.get("flow")
                if flow in ["upwards", "downwards", "random"]:
                    command_data["flow"] = flow
                else:
                    logger.warning(f"Invalid value for set_layout flow: {flow}")
                    return # Don't broadcast invalid command
            elif action == "set_styles":
                styles = msg_data.get("styles")
                if not isinstance(styles, dict):
                    logger.warning(f"Invalid styles data for set_styles: {styles}")
                    return # Don't broadcast invalid command

                # Validate and sanitize style values
                valid_styles = {}

                # Text color validation
                if "textColor" in styles and isinstance(styles["textColor"], str):
                    valid_styles["textColor"] = styles["textColor"]

                # Username color validation
                if "usernameColor" in styles and isinstance(styles["usernameColor"], str):
                    valid_styles["usernameColor"] = styles["usernameColor"]

                # Font size validation
                if "fontSize" in styles and isinstance(styles["fontSize"], (int, float)):
                    valid_styles["fontSize"] = max(10, min(32, styles["fontSize"]))

                # Text shadow validation
                if "textShadow" in styles and styles["textShadow"] in ["on", "off"]:
                    valid_styles["textShadow"] = styles["textShadow"]

                # Background color validation
                if "bgColor" in styles and isinstance(styles["bgColor"], str):
                    valid_styles["bgColor"] = styles["bgColor"]

                # Background opacity validation
                if "bgOpacity" in styles and isinstance(styles["bgOpacity"], (int, float)):
                    valid_styles["bgOpacity"] = max(0, min(1, styles["bgOpacity"]))

                # Padding validation
                if "padding" in styles and isinstance(styles["padding"], (int, float)):
                    valid_styles["padding"] = max(0, min(20, styles["padding"]))

                # Gap validation
                if "gap" in styles and isinstance(styles["gap"], (int, float)):
                    valid_styles["gap"] = max(0, min(20, styles["gap"]))

                # Border radius validation
                if "borderRadius" in styles and isinstance(styles["borderRadius"], (int, float)):
                    valid_styles["borderRadius"] = max(0, min(20, styles["borderRadius"]))

                # Browser source width validation
                if "width" in styles and isinstance(styles["width"], (int, float)):
                    valid_styles["width"] = max(100, min(3000, styles["width"]))

                # Browser source height validation
                if "height" in styles and isinstance(styles["height"], (int, float)):
                    valid_styles["height"] = max(100, min(3000, styles["height"]))

                # Bottom margin validation
                if "bottomMargin" in styles and isinstance(styles["bottomMargin"], (int, float)):
                    valid_styles["bottomMargin"] = max(0, min(200, styles["bottomMargin"]))

                # Random mode settings validation
                if "randomMessageDuration" in styles and isinstance(styles["randomMessageDuration"], (int, float)):
                    valid_styles["randomMessageDuration"] = max(1, min(60, styles["randomMessageDuration"]))

                if "randomAnimationDuration" in styles and isinstance(styles["randomAnimationDuration"], (int, float)):
                    valid_styles["randomAnimationDuration"] = max(100, min(2000, styles["randomAnimationDuration"]))

                if "randomMaxMessages" in styles and isinstance(styles["randomMaxMessages"], (int, float)):
                    valid_styles["randomMaxMessages"] = max(1, min(50, styles["randomMaxMessages"]))

                # Debug mode validation
                if "debugMode" in styles and isinstance(styles["debugMode"], bool):
                    valid_styles["debugMode"] = styles["debugMode"]

                # Add validated styles to command data
                command_data["styles"] = valid_styles
                logger.info(f"Applying overlay styles: {valid_styles}")
            elif action == "reset_styles":
                # No extra data needed for reset
                pass
            elif action == "toggle_debug":
                # No extra data needed for toggle_debug
                pass
            else:
                logger.warning(f"Unknown or invalid Kick overlay control action: {action}")
                # Optionally send an error back to the sender if needed
                return # Don't broadcast unknown commands

            overlay_command = {
                "type": "kick_overlay_command",
                "data": command_data
            }
            await globals.manager.broadcast(json.dumps(overlay_command))
        # --- End Kick Overlay Control ---

        elif msg_type == "update_screenshot_interval":
            # Update the screenshot interval
            try:
                new_interval = float(msg_data.get("interval", 1.0))
                # Validate the interval (between 0.1 and 10 seconds)
                new_interval = max(0.1, min(10.0, new_interval))

                # Update the screenshot interval in the screenshot module
                screenshot_api.screenshot_interval = new_interval
                logger.info(f"Updated screenshot interval to {new_interval} seconds")

                # Save to settings
                settings_module.set_setting("screenshot.interval", new_interval)
                logger.info(f"Saved screenshot interval {new_interval} to settings")

                # Acknowledge the update
                await globals.manager.send_personal_message(json.dumps({
                    "type": "screenshot_interval_updated",
                    "data": {"interval": new_interval}
                }), websocket)
            except Exception as e:
                logger.error(f"Error updating screenshot interval: {e}")
                await globals.manager.send_personal_message(json.dumps({
                    "type": "error",
                    "data": {"message": f"Error updating screenshot interval: {str(e)}"}
                }), websocket)

        elif msg_type == "update_settings":
            # Update settings
            try:
                new_settings = msg_data.get("settings", {})
                if new_settings:
                    updated_settings = settings_module.update_settings(new_settings)
                    logger.info(f"Updated settings: {updated_settings}")

                    # Broadcast settings update to all clients
                    await globals.manager.broadcast(json.dumps({
                        "type": "settings_updated",
                        "data": updated_settings
                    }))
                else:
                    logger.warning("Update settings request with empty settings data.")
            except Exception as e:
                logger.error(f"Error updating settings: {e}")
                await globals.manager.send_personal_message(json.dumps({
                    "type": "error",
                    "data": {"message": f"Error updating settings: {str(e)}"}
                }), websocket)

        elif msg_type == "get_settings":
            # Get current settings
            try:
                current_settings = settings_module.load_settings()
                await globals.manager.send_personal_message(json.dumps({
                    "type": "settings",
                    "data": current_settings
                }), websocket)
            except Exception as e:
                logger.error(f"Error getting settings: {e}")
                await globals.manager.send_personal_message(json.dumps({
                    "type": "error",
                    "data": {"message": f"Error getting settings: {str(e)}"}
                }), websocket)

        elif msg_type == "update_obs_dimensions":
            # Update OBS source dimensions
            try:
                width = int(msg_data.get("width", 800))
                height = int(msg_data.get("height", 600))
                bottom_margin = int(msg_data.get("bottomMargin", 10))

                # Validate dimensions
                width = max(100, min(3000, width))
                height = max(100, min(3000, height))
                bottom_margin = max(0, min(200, bottom_margin))

                # Update settings
                obs_settings = {
                    "obs_source": {
                        "width": width,
                        "height": height,
                        "bottom_margin": bottom_margin
                    }
                }

                updated_settings = settings_module.update_settings(obs_settings)
                logger.info(f"Updated OBS dimensions: {updated_settings['obs_source']}")

                # Broadcast OBS dimensions update to all clients
                await globals.manager.broadcast(json.dumps({
                    "type": "obs_dimensions_updated",
                    "data": updated_settings["obs_source"]
                }))
            except Exception as e:
                logger.error(f"Error updating OBS dimensions: {e}")
                await globals.manager.send_personal_message(json.dumps({
                    "type": "error",
                    "data": {"message": f"Error updating OBS dimensions: {str(e)}"}
                }), websocket)

                # Acknowledge the update
                await globals.manager.send_personal_message(json.dumps({
                    "type": "screenshot_interval_updated",
                    "data": {"interval": new_interval}
                }), websocket)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid screenshot interval: {e}")
                await globals.manager.send_personal_message(json.dumps({
                    "type": "error",
                    "data": {"message": f"Invalid screenshot interval: {e}"}
                }), websocket)

        else:
            logger.warning(f"Received unhandled WebSocket message type: {msg_type}")
            # await globals.manager.send_personal_message(json.dumps({"type": "error", "data": {"message": f"Unknown command: {msg_type}"}}), websocket)

    except Exception as e:
        logger.error(f"Error handling WebSocket message type {msg_type}: {e}", exc_info=True)
        try:
            await globals.manager.send_personal_message(json.dumps({"type": "error", "data": {"message": f"Error processing command {msg_type}"}}), websocket)
        except Exception: # Ignore errors sending error message back
            pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Use the manager from the globals module
    await globals.manager.connect(websocket)
    try:
        # Send initial status when a client connects
        # Load current settings
        current_settings = settings_module.load_settings()

        initial_status = {
            "type": "initial_status",
            "data": {
                "twitch_authenticated": config.IS_AUTHENTICATED,
                "kick_authenticated": config.KICK_IS_AUTHENTICATED,
                "twitch_channel": config.selected_channel, # Assuming this holds twitch channel
                "kick_channel": config.kick_channel_name, # Assuming this holds kick channel
                "kick_connected": config.kick_chat_connected, # Add kick connection status
                "raffle_entries_count": len(config.entered_users), # Add raffle entries count
                "settings": current_settings, # Include current settings
                # TODO: Add twitch_connected status if implemented
            }
        }
        logger.info(f"Sending initial status to new client: Twitch={config.IS_AUTHENTICATED}, Kick={config.KICK_IS_AUTHENTICATED}")
        try:
            await websocket.send_text(json.dumps(initial_status))
            logger.info("Initial status sent successfully")
        except Exception as e:
            logger.error(f"Error sending initial status: {e}")

        while True:
            # Keep connection open and listen for messages from the client
            data = await websocket.receive_text()
            # logger.info(f"Received message from {websocket.client}: {data}") # Logged in handler now
            try:
                message = json.loads(data)
                await handle_ws_message(websocket, message) # Process the message

            except json.JSONDecodeError:
                logger.error(f"Received invalid JSON from {websocket.client}: {data}")
                await globals.manager.send_personal_message(json.dumps({"type": "error", "data": {"message": "Invalid JSON format"}}), websocket)
            except WebSocketDisconnect: # Handle disconnect inside the loop if receive_text raises it
                logger.info(f"Client {websocket.client} disconnected during receive.")
                globals.manager.disconnect(websocket)
                break # Exit loop on disconnect
            except Exception as inner_e:
                 logger.error(f"Error processing message from {websocket.client}: {inner_e}")
                 # Avoid broadcasting raw internal errors directly to client unless necessary
                 await globals.manager.send_personal_message(json.dumps({"type": "error", "data": {"message": "Error processing message"}}), websocket)


    except WebSocketDisconnect: # Handle disconnect if connect or initial send fails
        # Ensure disconnect is called even if connection fails early
        if websocket in globals.manager.active_connections:
             globals.manager.disconnect(websocket)
        logger.info(f"Client {websocket.client} disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error for {websocket.client}: {e}", exc_info=True)
        # Ensure disconnect happens even on unexpected errors during the loop/setup
        if websocket in globals.manager.active_connections:
            globals.manager.disconnect(websocket)


# Placeholder for other utility endpoints (can be removed if status is handled by WS)
# @app.get("/api/status")
# async def get_status():
#     return {"twitch_authenticated": config.IS_AUTHENTICATED, "kick_authenticated": config.KICK_IS_AUTHENTICATED}

# --- Route for Kick Overlay ---
@app.get("/kick-overlay", response_class=HTMLResponse)
async def get_kick_overlay():
    """Serves the HTML page for the Kick chat overlay."""
    try:
        with open("ui/kick_overlay.html", "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        logger.error("ui/kick_overlay.html not found.")
        return HTMLResponse(content="<html><body><h1>Error: kick_overlay.html not found</h1></body></html>", status_code=404)
    except Exception as e:
        logger.error(f"Error reading ui/kick_overlay.html: {e}")
        return HTMLResponse(content="<html><body><h1>Internal Server Error</h1></body></html>", status_code=500)

# --- Route for Random Overlay ---
@app.get("/random-overlay", response_class=HTMLResponse)
async def get_random_overlay():
    """Serves the HTML page for the random message overlay."""
    try:
        with open("ui/random_overlay.html", "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        logger.error("ui/random_overlay.html not found.")
        return HTMLResponse(content="<html><body><h1>Error: random_overlay.html not found</h1></body></html>", status_code=404)
    except Exception as e:
        logger.error(f"Error reading ui/random_overlay.html: {e}")
        return HTMLResponse(content="<html><body><h1>Internal Server Error</h1></body></html>", status_code=500)

# --- Route for Docker Logs ---
@app.get("/docker-logs", response_class=HTMLResponse)
async def get_docker_logs():
    """Serves the HTML page for the Docker logs viewer."""
    try:
        with open("ui/docker_logs.html", "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        logger.error("ui/docker_logs.html not found.")
        return HTMLResponse(content="<html><body><h1>Error: docker_logs.html not found</h1></body></html>", status_code=404)
    except Exception as e:
        logger.error(f"Error reading ui/docker_logs.html: {e}")
        return HTMLResponse(content="<html><body><h1>Internal Server Error</h1></body></html>", status_code=500)

# Screenshot endpoint
@app.get("/api/screenshot")
async def get_screenshot(t: str = None, id: str = None, fallback: bool = False, direct: bool = False, emergency: bool = False, retry: bool = False):
    screenshot_path = screenshot_api.get_latest_screenshot()

    # Only log special screenshot requests, not regular updates
    if fallback or direct or emergency or retry:
        logger.info(f"Screenshot request with params: fallback={fallback}, direct={direct}, emergency={emergency}, retry={retry}")

    # Check if we need to force a new screenshot capture
    if emergency or retry:
        try:
            # Force a new screenshot capture
            output_path = os.path.join("static", "screenshots", "desktop_view.png")
            if screenshot_api.capture_screenshot(output_path):
                screenshot_path = output_path
                logger.info(f"Emergency screenshot captured successfully: {output_path}")
        except Exception as e:
            logger.error(f"Error capturing emergency screenshot: {e}")

    if screenshot_path and os.path.exists(screenshot_path):
        # Add cache control headers to prevent caching
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        return FileResponse(screenshot_path, headers=headers)
    else:
        logger.warning(f"Screenshot not found at path: {screenshot_path}")
        return HTMLResponse(content="<html><body><h1>No screenshot available</h1></body></html>", status_code=404)

# --- Application Startup/Shutdown ---
@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up...")
    # Initialize settings module
    settings_module.initialize()
    logger.info("Settings module initialized")

    # Initialize authentication state
    await auth_router.initialize_auth()

    # Initialize Docker client
    if not docker_api.init_docker_client():
        logger.warning("Docker API functionality will be limited. Some features may not work.")

    # Initialize screenshot service
    screenshot_api.init()

    # Broadcast initial state to any early WS connections
    # We'll try to broadcast, but it's okay if it fails (no connections yet)
    try:
        await auth_router.broadcast_auth_status()
        logger.info("Broadcast initial authentication status")
    except Exception as e:
        logger.warning(f"Could not broadcast initial auth status: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down...")
    # Stop screenshot service
    screenshot_api.cleanup()

    # Disconnect Kick chat cleanly
    await kick_api.disconnect_kick_chat()
    # TODO: Add disconnect for Twitch chat if implemented
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    # Note: Use 'uvicorn app:app --reload' from CLI for development
    # The --reload flag handles code changes automatically
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
