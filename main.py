
import os
import dearpygui.dearpygui as dpg
import webbrowser
import requests
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from threading import Thread
import threading
import os
import random  # Add the random module for selecting random viewers
import socket
import re
import pyaudio
from gtts import gTTS
from playsound import playsound
import time
import wave
import audioop
import sounddevice as sd
import numpy as np
from flask import jsonify
from flask_socketio import SocketIO, emit
import soundfile as sf
from pydub import AudioSegment
import traceback
import logging
import base64
import hashlib
import urllib.parse
import secrets

# Set logging level to WARNING to reduce console output
# This will stop logging every GET request
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

import warnings
from flask import Flask, render_template
warnings.filterwarnings("default", category=DeprecationWarning)

# Your Twitch application credentials
CLIENT_ID = 'qwfkkoq2roz77rvmauhnmhqr4ckvwt'
CLIENT_SECRET = 'm982e7esph7u5i0tohecryq4ml48z3' # Keep secret secure in production
REDIRECT_URI = 'http://localhost:3000/'
SCOPE = 'user:read:email channel:read:vips channel:read:subscriptions moderation:read moderator:read:chatters moderator:read:followers'
TOKEN_FILE = 'twitch_tokens.json'
AUTH_URL = f"https://id.twitch.tv/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope={SCOPE}"
TWITCH_USER_ID = None  # Store the user ID after authentication
IS_AUTHENTICATED = False  # Flag to track authentication status

#Kick Credentials
KICK_CLIENT_ID = '01JR6H958JM9ZCH9T2F2WVECYW'
KICK_CLIENT_SECRET = 'f9c6a68fdd6b010639be87b8902dc54f0ae62c087008e6533263b6453573cf67'
KICK_REDIRECT_URI = 'http://localhost:3000/'

# Variable to store the selected channel name
selected_channel = ""

# Variable to store the selected random viewer
selected_viewer = ""

viewers_list = []

global entered_users
entered_users = []

audio_threads = []

# Global variable to store the number of selected viewers
selected_viewer_count = 1

global twitch_sock
twitch_sock = None

global selected_viewers
selected_viewers = []

def open_viewer_page():
    webbrowser.open(f'http://localhost:5000/viewer', new=2)

viewer_messages = {}

def update_viewer_message(viewer_name, message):
    global viewer_messages
    viewer_messages[viewer_name] = message

def find_speaker_id(device_name):
    devices = sd.query_devices()
    for device_id, device in enumerate(devices):
        if device['name'] == device_name and device['max_output_channels'] > 0:
            return device_id

def find_microphone_id(device_name):
    devices = sd.query_devices()
    for device_id, device in enumerate(devices):
        if device['name'] == device_name and device['max_input_channels'] > 0:
            return device_id

def get_audio_devices():
    list = sd.query_devices()
    microphones = []
    speakers = []
    other = []

    for device in list:
        if device['max_input_channels'] > 0 and device['max_output_channels'] == 0:
            microphones.append(device['name'])
        elif device['max_output_channels'] > 0 and device['max_input_channels'] == 0:
            speakers.append(device['name'])
        elif device['max_output_channels'] > 0 and device['max_input_channels'] > 0:
            other.append(device["name"])

    return microphones, speakers, other

def handle_enter_command(username):
    if username not in entered_users:
        entered_users.append(username)
        print(f"{username} has entered!")

app = Flask(__name__)
socketio = SocketIO(app)
viewer_messages = {}

@app.route('/')
def home():
    return 'Welcome to the Flask server!'

@app.route('/viewer')
def show_viewer():
    try:
        viewer_content = ""
        for viewer_name in selected_viewers:
            image_urls = ["https://motionarray.imgix.net/preview-165955-sHrBnk2lYE-high_0005.jpg"]
            random_image = random.choice(image_urls)
            viewer_message = viewer_messages.get(viewer_name, "No new messages")
            viewer_content += f'''
                <div class="draggable-viewer" id="viewerBox_{viewer_name}">
                    <div class="move-icon">&#9776;</div>
                    <h1>{viewer_name}!</h1>
                    <img class="viewerImage" id="viewerImage_{viewer_name}" src="{random_image}" alt="Random Image" width="200" height="200">
                    <p class="subtitle" id="subtitle_{viewer_name}"></p> <!-- Subtitle element -->
                </div>
            '''
            print("Adding content for viewer: " + viewer_name)

        print("Finished processing viewers. Total viewers: " + str(len(selected_viewers)))

        # Ensure selected_viewers is properly formatted for JavaScript
        js_selected_viewers = json.dumps(selected_viewers)

        return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Viewer Page</title>
                <style>
                    body {{
                        background-color: transparent !important;
                        color: #000;
                        font-family: Arial, sans-serif;
                    }}
                    .viewerImage {{
                        width: 200px;
                        height: 200px;
                        transition: all 0.1s ease;
                    }}
                    .squash {{
                        animation: squashAndStretch 1s ease-in-out infinite;
                    }}
                    @keyframes squashAndStretch {{
                        0%, 100% {{
                            width: 200px;
                            height: 200px;
                        }}
                        50% {{
                            width: 250px;
                            height: 150px;
                        }}
                    }}
                    .draggable-viewer {{
                        width: 250px;
                        padding: 10px;
                        margin: 10px;
                        background-color: #f0f0f0;
                        border: 1px solid #ddd;
                        position: absolute;
                        cursor: move;
                        box-shadow: 0px 0px 5px 0px rgba(0,0,0,0.15);
                    }}
                    .draggable-viewer:hover {{
                        outline: 2px dashed #555;
                    }}
                    .move-icon {{
                        display: none;
                        position: absolute;
                        top: 5px;
                        right: 5px;
                        cursor: pointer;
                        font-size: 18px;
                        color: #666;
                    }}
                    .draggable-viewer:hover .move-icon {{
                        display: block;
                    }}
                    .subtitle {{
                        font-size: 14px; /* Style for subtitles */
                        color: #555;
                        text-align: center;
                        margin-top: 10px;
                    }}
                </style>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.0/socket.io.js"></script>
            </head>
            <body>
                {viewer_content}
                <script>
                    const socket = io();
                    console.log("Socket initialized");  // Log when socket is initialized

                    const selected_viewers = {js_selected_viewers}; // Use the JSON dumped variable
                    console.log("Selected viewers:", selected_viewers);  // Log selected viewers

                    socket.on('start_animation', function(data) {{
                        console.log("Starting animation for viewer:", data.viewer_name);
                        startSquashAndStretchAnimation(data.viewer_name, data.duration);
                        const subtitleElement = document.getElementById('subtitle_' + data.viewer_name);
                        if (subtitleElement) {{
                            subtitleElement.innerText = data.subtitle; // Set the subtitle
                            setTimeout(() => {{
                                subtitleElement.innerText = ''; // Clear the subtitle after the animation
                            }}, data.duration * 1000);
                        }}
                    }});

                    function startSquashAndStretchAnimation(viewer_name, duration) {{
                        const image = document.getElementById('viewerImage_' + viewer_name);
                        if (image) {{
                            console.log("Applying animation to viewer image:", viewer_name);  // Log when applying animation
                            image.classList.add('squash');
                            setTimeout(() => {{
                                console.log(`Animation ending for viewer ${{viewer_name}}.`);  // Log end of animation
                                image.classList.remove('squash');
                            }}, duration * 1000);
                        }} else {{
                            console.error(`Image element not found for viewer ${{viewer_name}}.`);  // Log if image element is not found
                        }}
                    }}

                    function updateMessage(viewer_name, message) {{
                        console.log("Updating message for viewer:", viewer_name);  // Log when updating message
                        // Note: The element 'latestMessage_' does not exist in the HTML structure above
                        // Consider adding <p id="latestMessage_{viewer_name}"></p> if needed,
                        // or update the subtitle element instead.
                        const subtitleElement = document.getElementById('subtitle_' + viewer_name);
                        if (subtitleElement) {{
                            // Optionally display the message here or elsewhere
                            // subtitleElement.innerText = message; // Example if you want message in subtitle area
                        }} else {{
                            console.log("Subtitle element not found for message update:", viewer_name);
                        }}
                    }}

                    function fetchAndUpdateMessage(viewer_name) {{
                        console.log("Fetching message for viewer:", viewer_name);  // Log when fetching message
                        fetch('/viewer/' + viewer_name + '/message')
                            .then(response => response.json())
                            .then(data => {{
                                console.log("Received message data for viewer:", viewer_name, data);  // Log received data
                                updateMessage(viewer_name, data.message);
                            }})
                            .catch(error => console.error("Error fetching message:", error));  // Log fetch errors
                    }}

                    function updateAllMessages() {{
                        console.log("Updating all messages for viewers");  // Log updating of all messages
                        selected_viewers.forEach(viewer_name => {{
                            fetchAndUpdateMessage(viewer_name);
                        }});
                    }}

                    // Removed setInterval(updateAllMessages, 500); as it might be excessive/not needed

                    socket.on('update_message', function(data) {{
                        console.log("Received updated message for viewer:", data.viewer_name);  // Log updated message event
                        updateMessage(data.viewer_name, data.message);
                    }});

                    function makeDraggable(elem) {{
                        var pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;

                        elem.onmousedown = function(e) {{
                            e.preventDefault(); // Prevent default drag behavior
                            // Get the mouse cursor position at startup:
                            pos3 = e.clientX;
                            pos4 = e.clientY;
                            document.onmouseup = closeDragElement;
                            // Call a function whenever the cursor moves:
                            document.onmousemove = elementDrag;
                        }};

                        function elementDrag(e) {{
                            e.preventDefault(); // Prevent text selection or other default actions
                            // Calculate the new cursor position:
                            pos1 = pos3 - e.clientX;
                            pos2 = pos4 - e.clientY;
                            pos3 = e.clientX;
                            pos4 = e.clientY;
                            // Set the element's new position:
                            elem.style.top = (elem.offsetTop - pos2) + "px";
                            elem.style.left = (elem.offsetLeft - pos1) + "px";
                        }}

                        function closeDragElement() {{
                            // Stop moving when mouse button is released:
                            document.onmouseup = null;
                            document.onmousemove = null;
                        }}
                    }}

                    // Apply the makeDraggable function to your elements after they are fully loaded
                    document.addEventListener('DOMContentLoaded', function() {{
                        var draggableElements = document.querySelectorAll('.draggable-viewer');
                        draggableElements.forEach(function(elem) {{
                            makeDraggable(elem);
                        }});
                    }});
                </script>
            </body>
            </html>
        '''
    except Exception as e:
        print("Error in show_viewer: " + str(e))
        traceback.print_exc() # Print full traceback
        return "Error in show_viewer"

@app.route('/viewer/<viewer_name>/message')
def get_viewer_message(viewer_name):
    try:
        global selected_viewers
        if viewer_name in selected_viewers:
            viewer_message = viewer_messages.get(viewer_name, "No new messages")
            print(f"Fetching message for viewer: {viewer_name}")
            return jsonify({"message": viewer_message})
        else:
            return jsonify({"message": "Viewer not found"}), 404
    except Exception as e:
        print("Error in get_viewer_message for " + viewer_name + ": " + str(e))
        traceback.print_exc() # Print full traceback
        return jsonify({"error": "Internal Server Error"}), 500

def analyze_audio(data):
    rms = np.sqrt(np.mean(np.square(data)))
    return rms

@socketio.on('connect')
def handle_connect():
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

def emit_audio_data(data):
    analyzed_data = analyze_audio(data)
    print("Volume:", analyzed_data)
    socketio.emit('audio_data', {'volume': analyzed_data})

def run_flask_app():
    # Disable Flask's default development server logging for cleaner output
    # Use Waitress or another production-grade server for deployment
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False, log_output=False)


flask_thread = Thread(target=run_flask_app, daemon=True)
flask_thread.start()

# Initialize PyAudio for TTS audio monitoring
py_audio = pyaudio.PyAudio()
# Removed audio_stream initialization here as it wasn't used directly for TTS monitoring

speech_folder = "viewer_speeches"
if not os.path.exists(speech_folder):
    os.makedirs(speech_folder, exist_ok=True) # Use makedirs with exist_ok=True

# Assuming the functions analyze_audio and emit_audio_data are defined elsewhere in your code

def play_audio(filename):
    try:
        logging.info("Playing audio: " + filename)
        # Use playsound within a try-except block to catch its specific errors
        try:
            playsound(filename)
        except Exception as e:
            logging.error(f"Error playing sound with playsound for {filename}: {e}")
            traceback.print_exc()

        logging.info("Finished playing audio: " + filename)

    except Exception as e:
        logging.error("General error in play_audio for file " + filename + ": " + str(e))
        traceback.print_exc()

def save_tts_as_wav(text, filename):
    try:
        # Define the path to your sound effect file
        sound_effect_path = "fart_sound_effect.wav" # Make sure this file exists
        sound_effect = None
        if os.path.exists(sound_effect_path):
             sound_effect = AudioSegment.from_wav(sound_effect_path)
        else:
            logging.warning(f"Sound effect file not found: {sound_effect_path}. Skipping sound effect.")

        # Placeholder for the final combined audio
        final_audio = AudioSegment.empty()

        # Split the text on the cue '(fart)' and process each part
        parts = text.split('(fart)')
        for i, part in enumerate(parts):
            part = part.strip() # Remove leading/trailing whitespace from part
            if part:
                # Generate TTS for this part of the text
                try:
                    tts = gTTS(text=part, lang='en')
                    temp_mp3_path = f"temp_{random.randint(1000, 9999)}.mp3" # Use random name for temp file
                    tts.save(temp_mp3_path)
                    part_audio = AudioSegment.from_mp3(temp_mp3_path)
                    final_audio += part_audio
                    os.remove(temp_mp3_path) # Clean up temp file immediately
                except Exception as tts_err:
                     logging.error(f"gTTS or AudioSegment error for part '{part}': {tts_err}")
                     continue # Skip this part if TTS fails

            # Add the sound effect if it exists and if it's not after the last part
            if sound_effect and i < len(parts) - 1:
                final_audio += sound_effect

        # Export the combined audio to the specified filename
        if len(final_audio) > 0: # Ensure there's audio to save
            final_audio.export(filename, format="wav")
            logging.info(f"Saved TTS as WAV: {filename}")
        else:
            logging.warning(f"No audio generated for TTS, file not saved: {filename}")

    except Exception as e:
        print("Error in save_tts_as_wav: " + str(e))
        traceback.print_exc()


def speak_message(message, username, subtitle, twitch_sock=None): # twitch_sock might not be needed here
    try:
        username = username.strip()  # Remove leading/trailing whitespace
        if not username:
            logging.warning("speak_message called with empty username.")
            return

        # Sanitize username for filename (replace invalid chars)
        safe_username = re.sub(r'[\\/*?:"<>|]', "", username)
        if not safe_username: # Handle cases where username consists only of invalid chars
            safe_username = f"user_{random.randint(1000, 9999)}"

        usernamelessthan5 = safe_username[:5].strip()  # Use sanitized name

        use_says = dpg.get_value("says_box")
        if use_says:
            text = f"{usernamelessthan5} says {message.strip()}"
        else:
            text = message.strip()

        if not text:
            logging.warning(f"speak_message called for {username} with empty message.")
            return

        speech_folder = "viewer_speeches"
        os.makedirs(speech_folder, exist_ok=True) # Ensure folder exists
        tts_filename = os.path.join(speech_folder, f"{safe_username}.wav")

        # Generate TTS file in a separate thread to avoid blocking UI
        tts_thread = threading.Thread(target=save_tts_as_wav, args=(text, tts_filename))
        tts_thread.start()
        tts_thread.join() # Wait for TTS file to be created

        if not os.path.exists(tts_filename):
            logging.error(f"TTS file was not created: {tts_filename}")
            return

        # Update message display logic (ensure message_display exists)
        if dpg.does_item_exist("message_display"):
             dpg.set_value("message_display", f"{username}: {message}")
        else:
             logging.warning("UI item 'message_display' not found.")


        # Get duration *after* file is created
        try:
            sound = AudioSegment.from_file(tts_filename)
            duration = len(sound) / 1000.0
        except Exception as audio_err:
            logging.error(f"Could not read audio file {tts_filename} to get duration: {audio_err}")
            duration = 5 # Default duration if reading fails

        # Socket emission logic
        socketio.emit('start_animation', {'viewer_name': username, 'duration': duration, 'subtitle': subtitle})

        # Play audio in a separate thread
        audio_thread = threading.Thread(target=play_audio, args=(tts_filename,))
        audio_thread.start()
        # Keep track of threads if needed for management (e.g., joining later)
        # audio_threads.append(audio_thread)

    except Exception as e:
        print("Error in speak_message: " + str(e))
        traceback.print_exc()


def save_tokens(access_token, refresh_token, user_id, user_name):
    with open(TOKEN_FILE, 'w') as file:
        json.dump({'access_token': access_token, 'refresh_token': refresh_token, 'user_id': user_id, 'user_name': user_name}, file)

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {TOKEN_FILE}. File might be corrupted.")
            # Optionally, delete or rename the corrupted file
            # os.remove(TOKEN_FILE)
            return None
    return None


class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.server_close_request = False # Flag to control server shutdown
        if self.path.startswith("/?code="):
            parsed_path = urlparse(self.path)
            query_params = parse_qs(parsed_path.query)
            code = query_params.get('code', [''])[0]

            if code:
                token_url = "https://id.twitch.tv/oauth2/token"
                payload = {
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': REDIRECT_URI
                }
                try:
                    response = requests.post(token_url, data=payload, timeout=10) # Add timeout
                    response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

                    access_token = response.json().get('access_token')
                    refresh_token = response.json().get('refresh_token')

                    if access_token and refresh_token:
                         authentication_complete(access_token, refresh_token)
                         self.send_response(200)
                         self.send_header('Content-type', 'text/html')
                         self.end_headers()
                         self.wfile.write(bytes("<html><body><script>window.close();</script>Authentication successful. You can close this tab.</body></html>", "utf-8"))
                         self.server.server_close_request = True # Signal server to shutdown
                    else:
                         print("Authentication failed: Missing tokens in response.")
                         self.send_auth_failed_response("Missing tokens in response")
                         self.server.server_close_request = True # Signal server to shutdown


                except requests.exceptions.RequestException as e:
                    print(f"Authentication failed. Request error: {e}")
                    self.send_auth_failed_response(f"Request error: {e}")
                    self.server.server_close_request = True # Signal server to shutdown
                except Exception as e: # Catch other potential errors like JSON parsing
                    print(f"Authentication failed. Unexpected error: {e}")
                    self.send_auth_failed_response(f"Unexpected error: {e}")
                    self.server.server_close_request = True # Signal server to shutdown

            else:
                print("Authentication failed: No code received.")
                self.send_auth_failed_response("No authorization code received.")
                self.server.server_close_request = True # Signal server to shutdown
        else:
             # Handle other paths if necessary, or send a 404
             self.send_response(404)
             self.send_header('Content-type', 'text/html')
             self.end_headers()
             self.wfile.write(bytes("<html><body>Not Found</body></html>", "utf-8"))
             # Don't necessarily shut down the server for a 404

    def send_auth_failed_response(self, message="Authentication failed. Please try again."):
        self.send_response(400)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(bytes(f"<html><body>{message}</body></html>", "utf-8"))

    def log_message(self, format, *args):
         # Suppress HTTP server logging unless debugging
         # super().log_message(format, *args)
         pass


def authentication_complete(access_token, refresh_token):
    global TWITCH_USER_ID, IS_AUTHENTICATED
    user_id = get_user_id(access_token)
    user_name = get_user_name(access_token)
    if user_id and user_name:
        save_tokens(access_token, refresh_token, user_id, user_name)
        TWITCH_USER_ID = user_id
        IS_AUTHENTICATED = True  # Set authentication status to True
        print("Authentication successful! User ID: ", user_id, "User Name: ", user_name)
        # Schedule UI updates for the main thread
        dpg.mvDataSource("Not Authenticated") # Assume auth_status is the data source name
        dpg.set_value("auth_status", "Authenticated")
        dpg.configure_item("auth_status", color=[0, 255, 0])
    else:
         print("Authentication partially failed: Could not retrieve User ID or User Name.")
         # Update UI to show partial failure?
         dpg.set_value("auth_status", "Auth Error")
         dpg.configure_item("auth_status", color=[255, 165, 0]) # Orange for error


def get_user_id(access_token):
    headers = {'Authorization': f'Bearer {access_token}', 'Client-Id': CLIENT_ID} # Add Client-ID for Helix
    try:
        response = requests.get('https://id.twitch.tv/oauth2/validate', headers=headers, timeout=10)
        response.raise_for_status()
        user_id = response.json().get('user_id')
        if user_id:
            print(f"User ID validation successful: {user_id}")
            return user_id
        else:
            print("Failed to validate token: 'user_id' not found in response.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Failed to validate token: {e}")
        return None


def get_user_name(access_token):
     # The validate endpoint also returns 'login' (username)
    headers = {'Authorization': f'Bearer {access_token}', 'Client-Id': CLIENT_ID}
    try:
        response = requests.get('https://id.twitch.tv/oauth2/validate', headers=headers, timeout=10)
        response.raise_for_status()
        user_name = response.json().get('login')
        if user_name:
            print(f"User Name validation successful: {user_name}")
            return user_name
        else:
            print("Failed to validate token: 'login' not found in response.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Failed to validate token: {e}")
        return None


def authenticate_with_twitch():
    # Use a flag or check thread status to prevent multiple auth servers
    global auth_server_thread
    if 'auth_server_thread' in globals() and auth_server_thread.is_alive():
        print("Authentication server is already running.")
        # Optionally bring the browser window to the front if possible/needed
        webbrowser.open(AUTH_URL) # Re-open auth URL in case user closed tab
        return

    auth_server_thread = Thread(target=run_auth_server, daemon=True) # Make daemon
    auth_server_thread.start()
    # Give server a moment to start before opening browser
    time.sleep(1)
    webbrowser.open(AUTH_URL)

class KickAuth:
    def __init__(self):
        self.code_verifier = self.generate_code_verifier()
        self.code_challenge = self.generate_code_challenge(self.code_verifier)
        self.authorization_code = None
        self.access_token = None

    def generate_code_verifier(self):
        return base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8').rstrip('=')

    def generate_code_challenge(self, verifier):
        challenge = hashlib.sha256(verifier.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(challenge).decode('utf-8').rstrip('=')

    def generate_state(self):
        # Generate a secure random state value
        return secrets.token_hex(16)

    def build_auth_url(self):
        state = self.generate_state()
        params = {
            'client_id': KICK_CLIENT_ID,
            'redirect_uri': KICK_REDIRECT_URI,
            'response_type': 'code',
            # Use the appropriate scopes as per your application's needs:
            'scope': 'chat:write chat:read channel:read user:read events:subscribe',
            'state': state,
            'code_challenge': self.code_challenge,
            'code_challenge_method': 'S256'
        }
        # Use the proper endpoint as per Kick's docs
        created_url = f"https://id.kick.com/oauth/authorize?{urllib.parse.urlencode(params)}"
        print("Auth URL:", created_url)  # Debugging line to show the generated URL
        return created_url

    def start_local_server(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(inner_self):
                parsed = urllib.parse.urlparse(inner_self.path)
                query = urllib.parse.parse_qs(parsed.query)
                if 'code' in query:
                    self.authorization_code = query['code'][0]
                    inner_self.send_response(200)
                    inner_self.send_header('Content-type', 'text/html')
                    inner_self.end_headers()
                    inner_self.wfile.write(b"<h1>Authorization complete. You may close this window.</h1>")
                else:
                    inner_self.send_response(400)
                    inner_self.end_headers()

            def log_message(*args):
                return  # silence logging

        server = HTTPServer(('localhost', 3000), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def exchange_code_for_token(self):
        token_url = "https://id.kick.com/oauth/token"
        data = {
            'grant_type': 'authorization_code',
            'client_id': KICK_CLIENT_ID,
            'client_secret': KICK_CLIENT_SECRET,
            'code': self.authorization_code,
            'redirect_uri': KICK_REDIRECT_URI,
            'code_verifier': self.code_verifier
        }
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        self.access_token = response.json().get('access_token')
        return self.access_token

    def authenticate(self):
        print("Opening browser to authenticate...")
        auth_url = self.build_auth_url()
        server = self.start_local_server()
        webbrowser.open(auth_url)

        print("Waiting for authorization code...")
        while not self.authorization_code:
            pass

        server.shutdown()
        print("Authorization code received. Fetching access token...")
        token = self.exchange_code_for_token()
        print("Access token obtained:", token)
        #TODO: this needs to be read as well for token refresh
        #save it to a json file like twitch does 
        with open('kick_tokens.json', 'w') as f:
            json.dump({'access_token': token}, f)
        print("Access token saved to kick_tokens.json")
        
        return token

class KickApiHelper:
    pass

# Global reference to the auth server instance
httpd_server = None

def run_auth_server():
    global httpd_server
    server_address = ('localhost', 3000)
    try:
        httpd_server = HTTPServer(server_address, AuthHandler)
        print("Starting HTTP server for authentication on port 3000...")
        # httpd_server.serve_forever() # This blocks, use loop instead
        while True:
            httpd_server.handle_request()
            # Check the flag set by AuthHandler to break the loop
            if hasattr(httpd_server, 'server_close_request') and httpd_server.server_close_request:
                break
        print("Authentication process completed, shutting down auth server...")
    except OSError as e:
        print(f"Could not start auth server on port 3000: {e}. Is it already in use?")
        # Update UI to show error
        if dpg.does_item_exist("auth_status"):
            dpg.set_value("auth_status", "Server Error")
            dpg.configure_item("auth_status", color=[255, 0, 0])
    except Exception as e:
        print(f"An error occurred in the auth server: {e}")
        traceback.print_exc()
    finally:
        if httpd_server:
            httpd_server.server_close() # Ensure the socket is closed
            print("Auth server successfully shut down.")
        httpd_server = None # Reset global reference


def cancel_auth():
    print("Cancel Auth Clicked")
    global IS_AUTHENTICATED, TWITCH_USER_ID
    IS_AUTHENTICATED = False
    TWITCH_USER_ID = None
    # Attempt to delete the tokens file
    if os.path.exists(TOKEN_FILE):
        try:
            os.remove(TOKEN_FILE)
            print("Tokens file deleted.")
        except OSError as e:
            print(f"Error deleting tokens file: {e}")
    # Reset the auth status in UI
    if dpg.does_item_exist("auth_status"):
        dpg.set_value("auth_status", "Not Authenticated")
        dpg.configure_item("auth_status", color=[255, 0, 0])

    # Attempt to shutdown the auth server if it's running
    global httpd_server
    if httpd_server:
         print("Attempting to shut down running auth server...")
         httpd_server.server_close_request = True # Signal server to stop
         # Try connecting to the server locally to unblock handle_request if needed
         try:
             # This is a bit of a hack to unblock the server loop if it's stuck waiting
             with socket.create_connection(('localhost', 3000), timeout=0.1) as sock:
                 pass # Just connect and close
         except (socket.timeout, ConnectionRefusedError):
             pass # Ignore if connection fails (server might be closing anyway)


# --- Twitch API Helper Functions ---

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
        print(f"Error making Twitch API request to {url}: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response Status: {e.response.status_code}, Body: {e.response.text}")
             # Attempt to parse error message for UI feedback
             try:
                 error_json = e.response.json()
                 error_message = error_json.get("message", "Unknown API error")
                 # Schedule UI update for error message
                 if dpg.does_item_exist("error_display"):
                     dpg.set_value("error_display", f"API Error: {error_message}")
                     dpg.configure_item("error_display", color=[255, 0, 0])
                     clear_error_message_after_delay(5) # Clear after 5 seconds
             except json.JSONDecodeError:
                 pass # Ignore if response body is not JSON
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from {url}: {e}")
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
            params.pop('after', None) # Ensure 'after' isn't carried over incorrectly

        data = _make_twitch_request(base_url, token, client_id, params=params)

        if data and 'data' in data:
            items = [item.get(user_key) for item in data['data'] if item.get(user_key)]
            all_items.extend(items)

            # Check for pagination cursor
            pagination_cursor = data.get('pagination', {}).get('cursor')
            if not pagination_cursor or len(data['data']) < 100: # Stop if no cursor or last page
                break
        else:
            print(f"Failed to fetch data or no 'data' field in response from {base_url}. Params: {params}")
            break # Exit loop on error or empty data

        # Safety break to avoid infinite loops if limit is very high and API behaves unexpectedly
        if 'after' not in params and pagination_cursor:
             print(f"Warning: Pagination cursor received ({pagination_cursor}) but 'after' parameter not used in next request?.")
             # This case shouldn't happen with current logic but is a safeguard

        # Add a small delay to respect rate limits, especially if fetching many pages
        time.sleep(0.1)


    return list(set(all_items)) # Return unique items


def get_all_chatters(broadcaster_id, moderator_id, token, client_id):
    """ Fetches all chatters in the channel. """
    url = f'https://api.twitch.tv/helix/chat/chatters'
    all_chatters = []
    pagination_cursor = None
    params = {'broadcaster_id': broadcaster_id, 'moderator_id': moderator_id, 'first': 1000} # Max 'first' is 1000 for chatters

    while True:
         if pagination_cursor:
             params['after'] = pagination_cursor
         else:
             params.pop('after', None)

         data = _make_twitch_request(url, token, client_id, params=params)

         if data and 'data' in data:
             chatters = [chatter['user_login'] for chatter in data['data']] # Use user_login
             all_chatters.extend(chatters)

             # Check pagination
             pagination_cursor = data.get('pagination', {}).get('cursor')
             total_expected = data.get('total', len(all_chatters)) # Use total if available

             # Exit conditions
             if not pagination_cursor or len(all_chatters) >= total_expected:
                 break
             if len(data['data']) < 1000: # Exit if last page had less than max items
                 break
         else:
             print("Failed to get chatters or empty data.")
             # Display error in UI if applicable
             if dpg.does_item_exist("error_display") and not all_chatters:
                 dpg.set_value("error_display", "Error: Could not fetch chatters list.")
                 dpg.configure_item("error_display", color=[255, 0, 0])
                 clear_error_message_after_delay(5)
             return None # Indicate failure

         time.sleep(0.1) # Small delay between pages

    return list(set(all_chatters)) # Return unique usernames


def get_vips(broadcaster_id, token, client_id):
    """ Fetches VIPs for the channel. """
    url = 'https://api.twitch.tv/helix/channels/vips'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login')

def get_moderators(broadcaster_id, token, client_id):
    """ Fetches Moderators for the channel. """
    url = 'https://api.twitch.tv/helix/moderation/moderators'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login')

def get_subscribers(broadcaster_id, token, client_id):
    """ Fetches Subscribers for the channel. """
    # IMPORTANT: Requires 'channel:read:subscriptions' scope.
    url = 'https://api.twitch.tv/helix/subscriptions'
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login') # user_login from sub data


def get_followers(broadcaster_id, token, client_id):
    """ Fetches Followers for the channel. """
    # IMPORTANT: Requires 'moderator:read:followers' scope for the *moderator* token.
    # If using user token, that user needs moderator permissions on the target channel.
    url = 'https://api.twitch.tv/helix/channels/followers'
    # Followers endpoint returns 'user_login' in the 'data' objects directly
    return _get_paginated_data(url, token, client_id, broadcaster_id, user_key='user_login', moderator_id=TWITCH_USER_ID) # Add moderator_id if needed by scope


# --- End Twitch API Helper Functions ---


# Function to get chatters' usernames and pick random ones based on filters
def get_random_filtered_chatters(channel_name, moderator_id, token, client_id, num_viewers=1, vip_only=False, mod_only=False, sub_only=False, follower_only=False):

    # 1. Get Broadcaster ID
    broadcaster_id = get_broadcaster_id(client_id, token, channel_name)
    if not broadcaster_id:
        print(f"Could not find broadcaster ID for channel: {channel_name}")
        dpg.set_value(error_display, f"Error: Channel '{channel_name}' not found.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return None

    # 2. Get all chatters
    all_chatters = get_all_chatters(broadcaster_id, moderator_id, token, client_id)
    if all_chatters is None: # Check for None explicitly, as empty list is valid
        # Error message should be set within get_all_chatters or _make_twitch_request
        print('Failed to get chatters list.')
        return None
    if not all_chatters:
         print('No chatters found in the channel.')
         dpg.set_value(error_display, "No chatters currently in the channel.")
         dpg.configure_item(error_display, color=[255, 165, 0]) # Orange warning
         clear_error_message_after_delay(5)
         return None


    print(f"Total chatters found: {len(all_chatters)}")
    filtered_chatters = set(all_chatters) # Start with all chatters as a set for efficient filtering

    # 3. Apply Filters (if any checkbox is selected)
    any_filter_active = vip_only or mod_only or sub_only or follower_only

    if any_filter_active:
        print("Applying filters...")
        # Fetch required lists only if the corresponding filter is active
        vips = set(get_vips(broadcaster_id, token, client_id)) if vip_only else None
        mods = set(get_moderators(broadcaster_id, token, client_id)) if mod_only else None
        subs = set(get_subscribers(broadcaster_id, token, client_id)) if sub_only else None
        followers = set(get_followers(broadcaster_id, token, client_id)) if follower_only else None

        # --- Filtering Logic ---
        # Start with the set of all chatters and intersect with fetched lists based on flags

        if vip_only:
            if vips is not None:
                print(f"Filtering for VIPs ({len(vips)} found)...")
                filtered_chatters.intersection_update(vips)
            else:
                print("Failed to fetch VIPs list, cannot apply VIP filter.")
                # Optionally clear the set if VIP fetch failed and vip_only was mandatory?
                # filtered_chatters.clear()

        if mod_only:
            if mods is not None:
                print(f"Filtering for Mods ({len(mods)} found)...")
                filtered_chatters.intersection_update(mods)
            else:
                print("Failed to fetch Mods list, cannot apply Mod filter.")

        if sub_only:
            if subs is not None:
                print(f"Filtering for Subs ({len(subs)} found)...")
                filtered_chatters.intersection_update(subs)
            else:
                print("Failed to fetch Subs list, cannot apply Sub filter.")
                # Note: Free subs (Prime) might not be included depending on API/permissions

        if follower_only:
            if followers is not None:
                print(f"Filtering for Followers ({len(followers)} found)...")
                filtered_chatters.intersection_update(followers)
            else:
                print("Failed to fetch Followers list, cannot apply Follower filter.")

        print(f"Chatters remaining after filtering: {len(filtered_chatters)}")
        if not filtered_chatters:
             print('No chatters match the selected filters.')
             dpg.set_value(error_display, "No chatters match the selected criteria.")
             dpg.configure_item(error_display, color=[255, 165, 0]) # Orange warning
             clear_error_message_after_delay(5)
             return None

    # 4. Convert filtered set back to list for sampling
    final_list = list(filtered_chatters)

    # 5. Select Random Chatters
    if not final_list:
        # This case should be caught earlier, but as a safeguard
        print('No chatters available to pick from after filtering.')
        return None

    if len(final_list) < num_viewers:
        print(f"Not enough viewers ({len(final_list)}) match the criteria to pick {num_viewers}.")
        dpg.set_value(error_display, f"Only found {len(final_list)} viewers matching criteria.")
        dpg.configure_item(error_display, color=[255, 165, 0]) # Orange warning
        clear_error_message_after_delay(5)
        # Optionally pick all available if less than requested?
        num_viewers = len(final_list) # Pick all available users
        # return None # Or return None if exactly num_viewers is required

    try:
        random_chatters = random.sample(final_list, num_viewers)
    except ValueError as e:
        print(f"Error sampling viewers: {e}")
        # This shouldn't happen with the length check above, but handle defensively
        dpg.set_value(error_display, f"Error selecting random viewers.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return None

    # 6. Update UI and return selected chatters
    print(f"Selected viewers: {random_chatters}")
    random_chatters_str = ', '.join(random_chatters)
    dpg.set_value(user_display, random_chatters_str)
    dpg.configure_item(user_display, color=[255, 255, 255], bullet=True) # White, bullet point

    global selected_viewers
    selected_viewers = random_chatters # Update global list for viewer page

    return random_chatters # Return the list of selected users


def get_random_chatter_raffle(num_viewers=1):
    global entered_users, selected_viewers # Ensure access to global lists

    # Check if enough users have entered
    if len(entered_users) < num_viewers:
        print(f"Raffle Error: Not enough viewers ({len(entered_users)}) have entered to pick {num_viewers}.")
        dpg.set_value(error_display, f"Error: Only {len(entered_users)} users entered the raffle.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return None

    # Select random viewers from entered_users
    try:
        # Use random.sample to pick unique viewers
        random_chatters = random.sample(entered_users, num_viewers)
    except ValueError:
        # Should be caught by the length check above, but handle defensively
        print("Error in selecting random viewers from raffle list.")
        dpg.set_value(error_display, "Error selecting raffle winners.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return None

    # Print and display the selected viewers
    print(f"Raffle winners: {random_chatters}")
    random_chatters_str = ', '.join(random_chatters)
    dpg.set_value(user_display, random_chatters_str)
    dpg.configure_item(user_display, color=[255, 255, 255], bullet=True) # White, bullet point

    # Update the global list for the viewer page
    selected_viewers = random_chatters
    print("Selected viewers (for viewer page):", selected_viewers)

    # Clear the entered users list for the next raffle *after* selection
    print(f"Clearing {len(entered_users)} users from the raffle list.")
    entered_users.clear()
    print("The raffle is complete. Entered users list cleared.")

    return random_chatters # Return the winners


def get_broadcaster_id(client_id, token, channel_login):
    """ Fetches the Twitch User ID for a given channel login name. """
    url = f"https://api.twitch.tv/helix/users?login={channel_login}"
    headers = {
        'Authorization': f'Bearer {token}',
        "Client-ID": client_id,
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data and "data" in data and len(data["data"]) > 0:
            user_info = data["data"][0]
            print(f"Found channel '{user_info['login']}' with ID {user_info['id']}")
            return user_info["id"]
        else:
            print(f"Channel '{channel_login}' not found or empty data array in response.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching broadcaster ID for {channel_login}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response Status: {e.response.status_code}, Body: {e.response.text}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response for broadcaster ID {channel_login}: {e}")
        return None

def clear_error_message_after_delay(seconds=5):
     """Clears the error message display after a delay."""
     def clear():
         time.sleep(seconds)
         if dpg.does_item_exist(error_display):
             dpg.set_value(error_display, "")
     # Run clearing in a separate thread to avoid blocking
     Thread(target=clear, daemon=True).start()


def pick_random_viewer_callback():
    global selected_channel, selected_viewer_count, selected_viewers
    print("Pick Random Viewer Clicked")

    # 1. Validate Inputs & Authentication
    channel_name_input = dpg.get_value(user_data)
    if not channel_name_input or channel_name_input.isspace():
        print("No channel name entered")
        dpg.set_value(error_display, "Error: Please enter a channel name.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return

    selected_channel = channel_name_input.strip().lower() # Use lower case consistently

    if not IS_AUTHENTICATED:
        print("Not Authenticated")
        dpg.set_value(error_display, "Error: Please authenticate with Twitch first.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return

    tokens = load_tokens()
    if not tokens or 'access_token' not in tokens or 'user_id' not in tokens:
        print("Authentication tokens are missing or invalid.")
        dpg.set_value(error_display, "Error: Invalid or missing authentication tokens.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message_after_delay(5)
        # Maybe try to re-authenticate or guide user?
        return

    access_token = tokens['access_token']
    moderator_id = tokens['user_id'] # The authenticated user's ID acts as moderator ID for API calls

    # 2. Get Settings from UI
    try:
        num_viewers = dpg.get_value(viewer_number_picker)
        selected_viewer_count = num_viewers # Update global count if needed elsewhere

        # Checkbox states
        raffle_mode = dpg.get_value(raffle_checkbox)
        vip_only = dpg.get_value(vip_box)
        mod_only = dpg.get_value(mod_box)
        sub_only = dpg.get_value(sub_box)
        follower_only = dpg.get_value(follower_box)
        # tts_enabled = dpg.get_value(tts_box) # If needed later

    except Exception as e:
        print(f"Error getting values from DPG items: {e}")
        dpg.set_value(error_display, "Error: Could not read UI settings.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return

    # 3. Execute Logic based on Mode (Raffle vs. Filtered)
    # Clear previous results/errors first
    dpg.set_value(user_display, "...") # Indicate processing
    dpg.configure_item(user_display, color=[255, 255, 255], bullet=False)
    dpg.set_value(error_display, "")

    if raffle_mode:
        print("Raffle mode selected.")
        # Call raffle function (handles entered_users list)
        get_random_chatter_raffle(num_viewers)
    else:
        print("Filtered selection mode.")
        # Call the filtering function
        get_random_filtered_chatters(
            channel_name=selected_channel,
            moderator_id=moderator_id,
            token=access_token,
            client_id=CLIENT_ID,
            num_viewers=num_viewers,
            vip_only=vip_only,
            mod_only=mod_only,
            sub_only=sub_only,
            follower_only=follower_only
        )

    # Optional: Re-establish chat connection if needed based on TTS or other features
    # if tts_enabled and not raffle_mode: # Example condition
    #     print("TTS enabled, ensuring chat connection...")
    #     # Logic to potentially restart or verify Twitch chat connection
    #     # start_streaming() # If this manages the connection


def start_twitch_button_callback():
    # This function seems intended to connect to Twitch chat for messages,
    # separate from picking random viewers. Keep its logic focused on that.
    print("Start Twitch Chat Connection Clicked (if applicable)")
    channel_name_input = dpg.get_value(user_data)
    if not channel_name_input or channel_name_input.isspace():
        dpg.set_value(error_display, "Error: Enter channel name to connect chat.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message_after_delay(5)
        return

    if not IS_AUTHENTICATED:
         dpg.set_value(error_display, "Error: Authenticate first to connect chat.")
         dpg.configure_item(error_display, color=[255, 0, 0])
         clear_error_message_after_delay(5)
         return

    # Add logic here to connect to Twitch chat using IRC if needed for TTS or raffle entries
    # Example:
    # if is_chat_connected(): # Function to check connection status
    #     print("Chat already connected.")
    #     # Optionally disconnect/reconnect or just update status
    #     # stop_chat_connection()
    #
    # print(f"Attempting to connect to Twitch chat for channel: {channel_name_input.strip().lower()}")
    # start_chat_connection(channel_name_input.strip().lower(), load_tokens()['access_token']) # Pass necessary details
    # Update UI element (e.g., 'enabled' button/text) based on connection success/failure


# DPG Setup and Main Loop
dpg.create_context()

# --- UI Element Variables (declare them here for wider scope if needed) ---
auth_status = None
user_data = None # Channel name input
error_display = None
user_display = None # Display selected user(s)
viewer_number_picker = None
raffle_checkbox = None
vip_box = None
mod_box = None
sub_box = None
follower_box = None
tts_box = None
says_box = None
message_display = None # Added for speak_message
enabled = None # For Twitch on/off status?

# --- End UI Element Variables ---

def create_window():
    global auth_status, user_data, error_display, user_display, viewer_number_picker
    global raffle_checkbox, vip_box, mod_box, sub_box, follower_box, tts_box, says_box
    global message_display, enabled # Make sure all are global

    microphones, speakers, other_devices = get_audio_devices()

    with dpg.window(label="Chattastic V3", width=800, height=600, tag="Primary Window"):
        # Authentication Section
        with dpg.group(horizontal=True):
            dpg.add_button(label="Authenticate with Twitch", callback=authenticate_with_twitch)
            dpg.add_button(label="Authenticate with Kick", callback=KickAuth().authenticate)
            auth_status = dpg.add_text("Not Authenticated", color=[255, 0, 0]) # Assign to global
            dpg.add_button(label="Cancel Authentication", callback=cancel_auth)

        dpg.add_separator()

        # Channel Input and Viewer Selection
        with dpg.group(horizontal=True):
            dpg.add_text("Enter Twitch Channel Name:")
            user_data = dpg.add_input_text(label="", default_value="", width=200) # Assign to global
            dpg.add_text("Number of Viewers to Pick:")
            viewer_number_picker = dpg.add_input_int(label="", default_value=1, min_value=1, max_value=100, width=100) # Assign

        dpg.add_button(label="Pick Random Viewer(s)", callback=pick_random_viewer_callback)
        user_display = dpg.add_text("Selected Viewer: None") # Assign to global
        error_display = dpg.add_text("", color=[255, 0, 0]) # Assign to global
        message_display = dpg.add_text("Last TTS Message: None") # Assign to global for TTS output


        dpg.add_separator()

        # TTS and Filter Options
        with dpg.tab_bar():
            with dpg.tab(label="TTS Options"):
                tts_box = dpg.add_checkbox(label="Read Viewer Messages in TTS (Text-to-Speech)", default_value=True) # Assign
                says_box = dpg.add_checkbox(label="Read Viewer names First (ex. username says hello)", default_value=False, tag="says_box") # Assign

                # Add dropdowns for audio devices if needed
                # dpg.add_combo(label="Microphone", items=microphones, default_value=microphones[0] if microphones else "")
                # dpg.add_combo(label="Speaker", items=speakers, default_value=speakers[0] if speakers else "")


            with dpg.tab(label="Filtering Options"):
                raffle_checkbox = dpg.add_checkbox(label="Raffle Mode (!enter command in chat)", tag="raffle_checkbox") # Assign
                dpg.add_separator()
                dpg.add_text("Filter viewers (requires channel permissions):")
                # Remove (WIP) from labels
                vip_box = dpg.add_checkbox(label="VIPs Only", tag="vip_box") # Assign
                mod_box = dpg.add_checkbox(label="Mods Only", tag="mod_box") # Assign
                sub_box = dpg.add_checkbox(label="Subs Only", tag="sub_box") # Assign
                follower_box = dpg.add_checkbox(label="Followers Only", tag="follower_box") # Assign

        dpg.add_separator()

        # Other Buttons/Status
        # 'enabled' might need rethinking - what does it represent? Chat connection? App status?
        enabled = dpg.add_text("Twitch Status: Unknown", tag="enabled_status") # Example usage
        dpg.add_button(label="Connect Twitch Chat", callback=start_twitch_button_callback) # Example button
        dpg.add_button(label="Open Viewer Page", callback=open_viewer_page)


# Initialize DPG window and elements
create_window()

# Check initial authentication status
tokens = load_tokens()
if tokens and 'access_token' in tokens:
    # Validate token silently? Or just assume it's good initially.
    # For simplicity, just update UI if tokens exist
    IS_AUTHENTICATED = True # Assume true if tokens exist, validation happens on API call
    TWITCH_USER_ID = tokens.get('user_id') # Load user ID
    print(f"Loaded existing tokens for User ID: {TWITCH_USER_ID}")
    if dpg.does_item_exist(auth_status):
        dpg.set_value(auth_status, "Authenticated (Cached)")
        dpg.configure_item(auth_status, color=[0, 255, 0])


dpg.create_viewport(title='Chattastic V3', width=800, height=600)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.set_primary_window("Primary Window", True)
dpg.start_dearpygui()
dpg.destroy_context()

# Cleanup (optional, e.g., stop threads if necessary)
print("Shutting down application...")
# Add any cleanup needed for threads or resources
if 'auth_server_thread' in globals() and auth_server_thread.is_alive():
    # Try to signal server shutdown if it's still running (unlikely after DPG loop ends)
    if httpd_server:
        httpd_server.server_close_request = True
        # Attempt to unblock if needed (see cancel_auth)
    auth_server_thread.join(timeout=1.0) # Wait briefly for thread