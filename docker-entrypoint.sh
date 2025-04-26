#!/bin/bash
# Docker Desktop Viewer - Container Entrypoint Script
# Sets up the X display environment and starts the application

set -e

echo "Starting Docker Desktop Viewer environment..."

# Check if Xvfb is already running
if [ -e /tmp/.X99-lock ]; then
    # Check if the process is actually running
    if ps -p $(cat /tmp/.X99-lock 2>/dev/null) > /dev/null 2>&1 || ps aux | grep -q "[X]vfb.*:99"; then
        echo "Xvfb is already running for display :99"
    else
        # Lock file exists but process is not running, remove the lock
        echo "Removing stale Xvfb lock file"
        rm -f /tmp/.X99-lock

        # Kill any existing Xvfb processes
        pkill -9 Xvfb || true

        # Start Xvfb with appropriate settings
        echo "Starting Xvfb..."
        Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
        sleep 3
    fi
else
    # Start Xvfb
    echo "Starting Xvfb..."
    Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
    sleep 3
fi

# Check if Xvfb started successfully
if ! ps aux | grep -q "[X]vfb"; then
    echo "Error: Xvfb failed to start"
    exit 1
fi

echo "Xvfb started successfully with PID: $(pgrep Xvfb)"

# Set up display environment
export DISPLAY=:99

# Make sure the DISPLAY is accessible
xhost + local: || true

# Check if XFCE session is already running
if pgrep -f "xfce4-session" > /dev/null; then
    echo "XFCE session is already running"
    DESKTOP_STARTED=true
else
    # Start XFCE session for a proper desktop environment
    echo "Starting XFCE session..."

    # Create necessary directories for XFCE session
    mkdir -p /app/.config/autostart

    # Set up D-Bus session
    export $(dbus-launch)
    echo "D-Bus session started with PID: $DBUS_SESSION_BUS_PID"

    # Start XFCE desktop environment
    DESKTOP_STARTED=false

    # Start XFCE session
    if command -v startxfce4 >/dev/null 2>&1; then
        echo "Starting XFCE session..."
        startxfce4 &
        XFCE_PID=$!
        sleep 3

        if ps -p $XFCE_PID > /dev/null; then
            echo "XFCE session started successfully with PID: $XFCE_PID"
            DESKTOP_STARTED=true
        else
            echo "XFCE session failed to start properly"
            # Try to kill any hanging processes
            pkill -9 xfce || true
        fi
    fi
fi

# Fallback to minimal X session if XFCE fails
if ! $DESKTOP_STARTED && command -v xterm >/dev/null 2>&1; then
    echo "XFCE could not be started. Using minimal xterm session..."
    xterm -geometry 100x30+10+10 -e "echo 'Minimal X session active'; sleep 10" &
    sleep 2
    DESKTOP_STARTED=true
fi

if $DESKTOP_STARTED; then
    echo "Desktop environment or window manager started successfully"
else
    echo "WARNING: Failed to start any desktop environment or window manager"
    echo "Chrome/Selenium may not function correctly without a window manager"
fi

# Create debug_screenshots directory if it doesn't exist
if [ ! -d "debug_screenshots" ]; then
    mkdir -p debug_screenshots
    echo "Created debug_screenshots directory"
fi

# Run the application
echo "Starting Docker Desktop Viewer application..."
python start.py
