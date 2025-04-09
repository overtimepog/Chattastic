#!/bin/bash
set -e

# Start Xvfb
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1920x1080x24 -ac &
sleep 2

# Check if Xvfb started successfully
if ! ps aux | grep -q "[X]vfb"; then
    echo "Error: Xvfb failed to start"
    exit 1
fi

echo "Xvfb started successfully"

# Start GNOME session in the background
echo "Starting GNOME session..."
export DISPLAY=:99
dbus-launch --exit-with-session gnome-session &
sleep 5

# Create emote_cache directory if it doesn't exist
if [ ! -d "emote_cache" ]; then
    mkdir -p emote_cache
    echo "Created emote_cache directory"
fi

# Run the application
echo "Starting Chattastic application..."
python run.py
