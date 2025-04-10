# Chattastic

## Introduction
Chattastic is an innovative tool designed for Twitch and Kick streamers and moderators. It enhances interaction with viewers through features like Text-to-Speech (TTS) for messages, and random viewer selection. Built using Python, it integrates with Twitch and Kick APIs for authentication and viewer interaction, and provides a user-friendly web interface accessible from any browser.

## Features
- **Twitch & Kick Authentication:** Secure login using Twitch and Kick credentials.
- **Viewer Interaction:** Pick random or specific viewers from your chat for special interactions.
- **Text-to-Speech:** Read viewer messages aloud using TTS.
- **Web Interface:** Access Chattastic from any device with a web browser.
- **Filtering Options:** Select viewers based on criteria like VIP status, moderator status, subscriber status, and follower status.
- **Raffle Mode:** Allow viewers to enter a raffle using the !enter command in chat.
- **Persistent Settings:** Settings are saved to your local Chattastic folder and persist across restarts.
- **Chat Overlay:** Display chat messages in your stream with customizable styles and animations.

## Installation

### Standard Installation
1. Run *run.bat* to install dependencies and start the web server
2. Open your web browser and navigate to http://localhost:8000
3. Follow the on-screen instructions to authenticate with Twitch and/or Kick

### Docker Installation
Chattastic can also be run in a Docker container, which is especially useful for running undetected_chromedriver in headless environments:

1. Make sure Docker and Docker Compose are installed on your system
2. Run *run_docker.bat* to build and start the Docker container
3. Open your web browser and navigate to http://localhost:8000
4. Follow the on-screen instructions to authenticate with Twitch and/or Kick

#### Testing Kick Chat in Docker
To test just the Kick chat functionality in Docker:

```bash
# Run with default channel (xqc) and duration (60 seconds)
run_docker_kick_test.bat

# Run with specific channel and duration (in seconds)
run_docker_kick_test.bat hasanabi 120
```

## Usage
1. Authenticate with Twitch and/or Kick
2. Enter the channel name you want to connect to
3. Configure your preferences in the TTS Options and Filtering Options tabs
4. Click "Pick Random Viewer(s)" to select viewers based on your criteria
5. Use the "Connect Twitch Chat" or "Connect Kick Chat" buttons to connect to chat
6. Click "Open Viewer Page" to display selected viewers in a separate window

## Settings
Chattastic now saves settings to your local Chattastic folder, ensuring they persist across restarts and updates. Settings include:

- **Authentication Tokens:** Your Twitch and Kick authentication tokens are securely stored
- **OBS Source Dimensions:** Set the dimensions of your browser source for optimal display
- **Overlay Styles:** Customize the appearance of your chat overlay
- **Screenshot Interval:** Control how frequently the desktop view is updated

To manage settings:
1. Go to the Settings section in the web interface
2. Adjust your preferences
3. Click "Save All Settings" to persist them to your local Chattastic folder
4. Use "Load Settings" to refresh from the saved file

## Contributions
Contributions to Chattastic are welcome. Please fork the repository, make your changes, and submit a pull request :)
