

import asyncio
import sys
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import config  # Assuming config.py holds necessary configurations
import globals # Import the globals module
import json # Add json import for message handling

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files directory (for HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="ui"), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected: {websocket.client}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        logger.info(f"Broadcasting message: {message}")
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending message to {connection.client}: {e}")
                # Optionally disconnect problematic clients
                # self.disconnect(connection)

# Create the manager instance and assign it to the globals module
globals.manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def get_root():
    # Serve the main HTML file
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
# TODO: Import audio utils if needed for TTS trigger
# from utils import audio as audio_utils

app.include_router(auth_router.router, prefix="/api/auth", tags=["authentication"])
app.include_router(twitch_api.router, prefix="/api/twitch", tags=["twitch"]) # Include Twitch API router
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
            initial_status = {
                "type": "initial_status",
                "data": {
                    "twitch_authenticated": config.IS_AUTHENTICATED,
                    "kick_authenticated": config.KICK_IS_AUTHENTICATED,
                    "twitch_channel": config.selected_channel,
                    "kick_channel": config.kick_channel_name,
                    "kick_connected": config.kick_chat_connected,
                    # Add twitch connected status if implemented
                }
            }
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
                if flow in ["upwards", "downwards"]:
                    command_data["flow"] = flow
                else:
                    logger.warning(f"Invalid value for set_layout flow: {flow}")
                    return # Don't broadcast invalid command
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
        initial_status = {
            "type": "initial_status",
            "data": {
                "twitch_authenticated": config.IS_AUTHENTICATED,
                "kick_authenticated": config.KICK_IS_AUTHENTICATED,
                "twitch_channel": config.selected_channel, # Assuming this holds twitch channel
                "kick_channel": config.kick_channel_name, # Assuming this holds kick channel
                "kick_connected": config.kick_chat_connected, # Add kick connection status
                "raffle_entries_count": len(config.entered_users), # Add raffle entries count
                # TODO: Add twitch_connected status if implemented
            }
        }
        await globals.manager.send_personal_message(json.dumps(initial_status), websocket)

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

# --- Application Startup/Shutdown ---
@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up...")
    # Initialize authentication state
    auth_router.initialize_auth()
    # Broadcast initial state to any early WS connections (though usually happens on connect)
    # await auth_router.broadcast_auth_status() # Might be redundant with on-connect send

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down...")
    # Disconnect Kick chat cleanly
    await kick_api.disconnect_kick_chat()
    # TODO: Add disconnect for Twitch chat if implemented
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    # Note: Use 'uvicorn app:app --reload' from CLI for development
    # The --reload flag handles code changes automatically
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
