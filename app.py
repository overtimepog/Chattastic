
"""
Docker Desktop Viewer Application

A streamlined application for viewing Docker container logs and desktop screenshots.
Provides a web interface for monitoring Docker containers and viewing their logs.
"""

import asyncio
import os
import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Import local modules
import config
import globals
from api import docker as docker_api
from api import screenshot as screenshot_api

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define lifespan context manager for application lifecycle events
@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Manage application lifecycle events.

    Handles startup and shutdown tasks for the application.
    """
    # Startup
    logger.info("Application starting up...")

    # Initialize Docker client
    if not docker_api.init_docker_client():
        logger.warning("Docker API functionality will be limited. Some features may not work.")

    # Initialize screenshot service
    screenshot_api.init()

    yield

    # Shutdown
    logger.info("Application shutting down...")

    # Stop screenshot service
    screenshot_api.cleanup()

    logger.info("Shutdown complete.")

# Create FastAPI application with lifespan
app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    description="Web interface for monitoring Docker containers and viewing their logs",
    lifespan=lifespan
)

# Mount static files directories (for HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="ui"), name="static")
app.mount("/static-assets", StaticFiles(directory="static"), name="static-assets")

class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.

    Handles connection lifecycle and provides methods for sending messages
    to individual clients or broadcasting to all connected clients.
    """

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._broadcast_lock = asyncio.Lock()
        self._screenshot_queue = asyncio.Queue()
        # Start the screenshot broadcast worker
        asyncio.create_task(self._screenshot_broadcast_worker())

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection from the active connections list."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected: {websocket.client}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message to {websocket.client}: {e}")
            # Disconnect problematic client
            self.disconnect(websocket)

    async def broadcast(self, message: str):
        """
        Broadcast a message to all connected clients.

        Screenshot updates are sent through a dedicated queue for better performance.
        """
        try:
            msg_data = json.loads(message)
            msg_type = msg_data.get("type", "")

            # Route screenshot updates to the high-priority queue
            if msg_type == "screenshot_update" or "desktop_view" in msg_type:
                await self._screenshot_queue.put(message)
            # All other messages go through the immediate broadcast
            else:
                await self._direct_broadcast(message)
        except json.JSONDecodeError:
            # If we can't parse the message, just broadcast it directly
            await self._direct_broadcast(message)

    async def _direct_broadcast(self, message: str):
        """Immediately broadcast a message to all connections."""
        async with self._broadcast_lock:
            # Only log non-screenshot messages to reduce noise
            if 'screenshot_update' not in message and 'desktop_view' not in message:
                logger.debug(f"Broadcasting message: {message[:100]}...")

            # Use a copy of the connections list to avoid modification during iteration
            for connection in self.active_connections.copy():
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

# Create the manager instance and assign it to the globals module
globals.manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def get_root():
    """
    Serve the main application HTML page.

    Returns the index.html file from the ui directory.
    """
    try:
        with open("ui/index.html", "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        logger.error("ui/index.html not found.")
        return HTMLResponse(content="<html><body><h1>Error: index.html not found</h1></body></html>", status_code=404)
    except Exception as e:
        logger.error(f"Error reading ui/index.html: {e}")
        return HTMLResponse(content="<html><body><h1>Internal Server Error</h1></body></html>", status_code=500)

# --- WebSocket Message Handling ---
async def handle_ws_message(websocket: WebSocket, message: dict):
    """
    Process incoming WebSocket messages.

    Handles Docker container operations and screenshot settings.
    """
    msg_type = message.get("type")
    msg_data = message.get("data", {})
    logger.info(f"Processing WebSocket message type: {msg_type}")

    try:
        if msg_type == "get_initial_status":
            # Send application status to the client
            initial_status = {
                "type": "initial_status",
                "data": {
                    "app_name": config.APP_NAME,
                    "app_version": config.APP_VERSION,
                    "screenshot_interval": config.SCREENSHOT_INTERVAL
                }
            }
            logger.info(f"Sending initial status to client")
            await globals.manager.send_personal_message(json.dumps(initial_status), websocket)

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

        elif msg_type == "update_screenshot_interval":
            # Update the screenshot interval
            try:
                new_interval = float(msg_data.get("interval", 1.0))
                # Validate the interval (between 0.1 and 10 seconds)
                new_interval = max(0.1, min(10.0, new_interval))

                # Update the screenshot interval in the screenshot module
                screenshot_api.screenshot_interval = new_interval
                # Update the global config
                config.SCREENSHOT_INTERVAL = new_interval
                logger.info(f"Updated screenshot interval to {new_interval} seconds")

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

        else:
            logger.warning(f"Received unhandled WebSocket message type: {msg_type}")

    except Exception as e:
        logger.error(f"Error handling WebSocket message type {msg_type}: {e}", exc_info=True)
        try:
            await globals.manager.send_personal_message(json.dumps({
                "type": "error",
                "data": {"message": f"Error processing command {msg_type}"}
            }), websocket)
        except Exception:
            # Ignore errors sending error message back
            pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time communication with clients.

    Handles connection lifecycle and message processing.
    """
    # Use the manager from the globals module
    await globals.manager.connect(websocket)
    try:
        # Send initial status when a client connects
        initial_status = {
            "type": "initial_status",
            "data": {
                "app_name": config.APP_NAME,
                "app_version": config.APP_VERSION,
                "screenshot_interval": config.SCREENSHOT_INTERVAL
            }
        }
        logger.info(f"Sending initial status to new client")
        try:
            await websocket.send_text(json.dumps(initial_status))
            logger.info("Initial status sent successfully")
        except Exception as e:
            logger.error(f"Error sending initial status: {e}")

        while True:
            # Keep connection open and listen for messages from the client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await handle_ws_message(websocket, message) # Process the message
            except json.JSONDecodeError:
                logger.error(f"Received invalid JSON from {websocket.client}: {data}")
                await globals.manager.send_personal_message(json.dumps({
                    "type": "error",
                    "data": {"message": "Invalid JSON format"}
                }), websocket)
            except WebSocketDisconnect: # Handle disconnect inside the loop
                logger.info(f"Client {websocket.client} disconnected during receive.")
                globals.manager.disconnect(websocket)
                break # Exit loop on disconnect
            except Exception as inner_e:
                logger.error(f"Error processing message from {websocket.client}: {inner_e}")
                # Avoid broadcasting raw internal errors directly to client
                await globals.manager.send_personal_message(json.dumps({
                    "type": "error",
                    "data": {"message": "Error processing message"}
                }), websocket)

    except WebSocketDisconnect: # Handle disconnect if connect or initial send fails
        # Ensure disconnect is called even if connection fails early
        if websocket in globals.manager.active_connections:
            globals.manager.disconnect(websocket)
        logger.info(f"Client {websocket.client} disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error for {websocket.client}: {e}", exc_info=True)
        # Ensure disconnect happens even on unexpected errors
        if websocket in globals.manager.active_connections:
            globals.manager.disconnect(websocket)


# --- Route for Docker Logs ---
@app.get("/docker-logs", response_class=HTMLResponse)
async def get_docker_logs():
    """
    Serve the Docker logs viewer HTML page.

    Returns the docker_logs.html file from the ui directory.
    """
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
async def get_screenshot(force: bool = False, emergency: bool = False, retry: bool = False):
    """
    Serve the latest desktop screenshot.

    Args:
        force: Force a new screenshot capture
        emergency: Force a new screenshot capture with high priority
        retry: Retry screenshot capture if it failed previously

    Returns:
        The screenshot image file with cache control headers
    """
    screenshot_path = screenshot_api.get_latest_screenshot()

    # Only log special screenshot requests, not regular updates
    if force or emergency or retry:
        logger.info(f"Screenshot request with params: force={force}, emergency={emergency}, retry={retry}")

    # Check if we need to force a new screenshot capture
    if force or emergency or retry:
        try:
            # Force a new screenshot capture
            output_path = os.path.join("static", "screenshots", "desktop_view.png")
            if screenshot_api.capture_screenshot(output_path):
                screenshot_path = output_path
                logger.info(f"Screenshot captured successfully: {output_path}")
        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}")

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


if __name__ == "__main__":
    """
    Run the application directly using Uvicorn.

    For development, use: uvicorn app:app --reload
    """
    logger.info(f"Starting {config.APP_NAME} v{config.APP_VERSION}")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
