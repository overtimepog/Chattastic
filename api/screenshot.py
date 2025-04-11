import os
import time
import logging
import threading
import subprocess
import asyncio
import json
import glob
import globals

# Set up logging
logger = logging.getLogger(__name__)

# Global variables
screenshot_thread = None
screenshot_active = False
latest_screenshot_path = None
screenshot_interval = 1.0  # Screenshot interval in seconds

def cleanup_screenshot_files(current_file=None):
    """Clean up old screenshot files, keeping only the current one."""
    try:
        screenshots_dir = os.path.join("static", "screenshots")
        if not os.path.exists(screenshots_dir):
            return

        # Get all PNG files in the screenshots directory
        screenshot_files = glob.glob(os.path.join(screenshots_dir, "*.png"))

        # If we have a current file, don't delete it
        if current_file and os.path.exists(current_file):
            current_file = os.path.abspath(current_file)
            screenshot_files = [f for f in screenshot_files if os.path.abspath(f) != current_file]

        # Delete old screenshot files
        for file_path in screenshot_files:
            try:
                os.remove(file_path)
                logger.debug(f"Deleted old screenshot file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete screenshot file {file_path}: {e}")

    except Exception as e:
        logger.error(f"Error cleaning up screenshot files: {e}")

def cleanup_debug_screenshots(max_age_hours=24):
    """Clean up debug screenshots older than the specified age."""
    try:
        debug_dir = "debug_screenshots"
        if not os.path.exists(debug_dir):
            return

        # Get all PNG files in the debug screenshots directory
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        # Get all PNG files in the directory
        debug_files = glob.glob(os.path.join(debug_dir, "*.png"))

        # Delete files older than max_age_hours
        for file_path in debug_files:
            try:
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > max_age_seconds:
                    os.remove(file_path)
                    logger.debug(f"Deleted old debug screenshot: {file_path} (age: {file_age/3600:.1f} hours)")
            except Exception as e:
                logger.error(f"Failed to delete debug screenshot {file_path}: {e}")

    except Exception as e:
        logger.error(f"Error cleaning up debug screenshots: {e}")

def capture_screenshot(output_path):
    """Capture a screenshot of the Xvfb display using xwd and convert to PNG."""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Use xwd to capture the X display and convert to PNG with ImageMagick
        display = os.environ.get('DISPLAY', ':99')
        cmd = f"xwd -root -display {display} | convert xwd:- png:{output_path}"

        # Execute the command with a timeout to prevent hanging
        try:
            # Use subprocess.run with timeout instead of subprocess.call
            result = subprocess.run(cmd, shell=True, check=False, timeout=5, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

            if result.returncode == 0:
                # Reduced logging - only log at debug level if DEBUG_SCREENSHOTS is enabled
                if os.environ.get('DEBUG_SCREENSHOTS') == '1':
                    logger.debug(f"Screenshot captured successfully: {output_path}")
                # Clean up any old screenshot files
                cleanup_screenshot_files(output_path)
                return True
            else:
                error_output = result.stderr.decode('utf-8', errors='ignore')
                logger.error(f"Failed to capture screenshot, command returned: {result.returncode}\nError: {error_output}")

                # Try an alternative method if the first one fails
                alt_cmd = f"import -window root {output_path}"
                alt_result = subprocess.run(alt_cmd, shell=True, check=False, timeout=5)

                if alt_result.returncode == 0:
                    logger.info(f"Screenshot captured successfully using alternative method: {output_path}")
                    cleanup_screenshot_files(output_path)
                    return True
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"Screenshot capture timed out after 5 seconds")
            return False
    except Exception as e:
        logger.error(f"Error capturing screenshot: {e}")
        return False

# Function to broadcast screenshot updates via WebSocket
async def broadcast_screenshot_update(path):
    """Broadcast a screenshot update notification to all connected clients."""
    try:
        # Create a timestamp to prevent caching
        timestamp = int(time.time() * 1000)
        # Create a unique ID for this screenshot update
        update_id = f"screenshot_{timestamp}_{hash(path) % 10000}"

        # Create a message specifically for screenshot updates
        message = {
            "type": "screenshot_update",
            "data": {
                "path": path,
                "timestamp": timestamp,
                "update_id": update_id
            }
        }

        # Use the global manager to broadcast the message
        if globals.manager:
            # Convert the message to JSON string
            message_str = json.dumps(message)

            # Use the screenshot-specific broadcast queue for high priority
            await globals.manager._screenshot_queue.put(message_str)
            # Only log if debug screenshots are enabled
            if os.environ.get('DEBUG_SCREENSHOTS') == '1':
                logger.debug(f"Queued screenshot update: {path} with ID {update_id}")
        else:
            logger.warning("Cannot broadcast screenshot update: globals.manager is None")
    except Exception as e:
        logger.error(f"Error broadcasting screenshot update: {e}")

# Create an event loop for the screenshot thread to use
screenshot_loop = None

def screenshot_thread_function():
    """Thread function to periodically capture screenshots."""
    global screenshot_active, latest_screenshot_path, screenshot_loop, screenshot_interval

    logger.info(f"Starting screenshot capture thread with interval of {screenshot_interval} seconds")

    # Create a new event loop for this thread
    screenshot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(screenshot_loop)

    # Add a counter to log periodic status updates
    screenshot_count = 0
    status_log_interval = 30  # Log status every 30 screenshots
    last_error_time = 0  # Track when the last error occurred
    last_cleanup_time = time.time()  # Track when we last cleaned up debug screenshots
    cleanup_interval = 3600  # Clean up debug screenshots every hour

    while screenshot_active:
        try:
            # Use a fixed filename for the desktop view
            filename = "desktop_view.png"
            output_path = os.path.join("static", "screenshots", filename)

            # Get the current time for interval calculation
            current_time = time.time()

            # Capture the screenshot
            if capture_screenshot(output_path):
                latest_screenshot_path = output_path
                screenshot_count += 1

                # Broadcast the screenshot update using the event loop
                screenshot_loop.run_until_complete(broadcast_screenshot_update(output_path))

                # Log status periodically to confirm thread is still running
                if screenshot_count % status_log_interval == 0:
                    logger.info(f"Screenshot service still running - captured {screenshot_count} screenshots so far with interval {screenshot_interval}s")

            # Periodically clean up debug screenshots
            current_time = time.time()
            if current_time - last_cleanup_time > cleanup_interval:
                cleanup_debug_screenshots()
                last_cleanup_time = current_time
                logger.info("Performed periodic cleanup of debug screenshots")

            # Calculate how long to sleep based on the current interval setting
            # This allows the interval to be changed dynamically
            sleep_time = max(0.1, screenshot_interval)  # Ensure minimum sleep time
            time.sleep(sleep_time)
        except Exception as e:
            # Only log errors once per minute to avoid spamming the log
            current_time = time.time()
            if current_time - last_error_time > 60:
                logger.error(f"Error in screenshot thread: {e}")
                last_error_time = current_time
            time.sleep(1)  # Sleep briefly on error

    logger.info("Screenshot capture thread stopped")

    # Close the event loop when done
    if screenshot_loop and screenshot_loop.is_running():
        screenshot_loop.close()

def start_screenshot_service():
    """Start the screenshot capture service."""
    global screenshot_thread, screenshot_active

    if screenshot_thread and screenshot_thread.is_alive():
        logger.warning("Screenshot service is already running")
        return False

    # Create the screenshots directory if it doesn't exist
    os.makedirs(os.path.join("static", "screenshots"), exist_ok=True)

    # Start the screenshot thread
    screenshot_active = True
    screenshot_thread = threading.Thread(
        target=screenshot_thread_function,
        daemon=True
    )
    screenshot_thread.start()
    logger.info("Screenshot service started")
    return True

def stop_screenshot_service():
    """Stop the screenshot capture service."""
    global screenshot_active

    if not screenshot_thread or not screenshot_thread.is_alive():
        logger.warning("Screenshot service is not running")
        return False

    # Signal the thread to stop
    screenshot_active = False
    logger.info("Screenshot service stopping")
    return True

def get_latest_screenshot():
    """Get the path to the latest screenshot."""
    return latest_screenshot_path

# Initialize the service when the module is imported
def init():
    """Initialize the screenshot service."""
    # Clean up any existing screenshot files before starting
    cleanup_screenshot_files()
    # Clean up old debug screenshots
    cleanup_debug_screenshots()
    start_screenshot_service()

# Clean up when the module is unloaded
def cleanup():
    """Clean up the screenshot service and any remaining files."""
    stop_screenshot_service()
    # Clean up all screenshot files when shutting down
    cleanup_screenshot_files()
    # Clean up old debug screenshots
    cleanup_debug_screenshots()
