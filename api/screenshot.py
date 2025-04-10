import os
import time
import logging
import threading
import subprocess

# Set up logging
logger = logging.getLogger(__name__)

# Global variables
screenshot_thread = None
screenshot_active = False
latest_screenshot_path = None
screenshot_interval = 1.0  # Screenshot interval in seconds

def capture_screenshot(output_path):
    """Capture a screenshot of the Xvfb display using xwd and convert to PNG."""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Use xwd to capture the X display and convert to PNG with ImageMagick
        display = os.environ.get('DISPLAY', ':99')
        cmd = f"xwd -root -display {display} | convert xwd:- png:{output_path}"

        # Execute the command
        result = subprocess.call(cmd, shell=True)

        if result == 0:
            logger.debug(f"Screenshot captured successfully: {output_path}")
            return True
        else:
            logger.error(f"Failed to capture screenshot, command returned: {result}")
            return False
    except Exception as e:
        logger.error(f"Error capturing screenshot: {e}")
        return False

def screenshot_thread_function():
    """Thread function to periodically capture screenshots."""
    global screenshot_active, latest_screenshot_path

    logger.info("Starting screenshot capture thread")

    while screenshot_active:
        try:
            # Use a fixed filename for the desktop view
            filename = "desktop_view.png"
            output_path = os.path.join("static", "screenshots", filename)

            # Capture the screenshot
            if capture_screenshot(output_path):
                latest_screenshot_path = output_path

            # Sleep for the specified interval
            time.sleep(screenshot_interval)
        except Exception as e:
            logger.error(f"Error in screenshot thread: {e}")
            time.sleep(1)  # Sleep briefly on error

    logger.info("Screenshot capture thread stopped")

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
    start_screenshot_service()

# Clean up when the module is unloaded
def cleanup():
    """Clean up the screenshot service."""
    stop_screenshot_service()
