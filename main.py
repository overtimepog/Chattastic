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
import simpleaudio as sa

import logging
# Set logging level to WARNING to reduce console output
# This will stop logging every GET request
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

import warnings
from flask import Flask, render_template
warnings.filterwarnings("default", category=DeprecationWarning)

# Your Twitch application credentials
CLIENT_ID = 'qwfkkoq2roz77rvmauhnmhqr4ckvwt'
CLIENT_SECRET = 'm982e7esph7u5i0tohecryq4ml48z3'
REDIRECT_URI = 'http://localhost:3000/'
SCOPE = 'user:read:email channel:read:vips moderation:read moderator:read:chatters moderator:read:followers'
TOKEN_FILE = 'twitch_tokens.json'
AUTH_URL = f"https://id.twitch.tv/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope={SCOPE}"
TWITCH_USER_ID = None  # Store the user ID after authentication
IS_AUTHENTICATED = False  # Flag to track authentication status

# Variable to store the selected channel name
selected_channel = ""

# Variable to store the selected random viewer
selected_viewer = ""

viewers_list = []

global entered_users
entered_users = []

# Global variable to store the number of selected viewers
selected_viewer_count = 1

global twitch_sock
twitch_sock = None

global selected_viewers
selected_viewers = []

def open_viewer_pages():
    for viewer in selected_viewers:
        webbrowser.open(f'http://localhost:5000/viewer/{viewer}', new=2)

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

    #print("Microphones:", microphones)
    #print("Speakers:", speakers)
    #print("Other", other)
    
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

@app.route('/viewer/<viewer_name>')
def show_viewer(viewer_name):
    if viewer_name in selected_viewers:
        # Placeholder image URLs or integrate an API for random images
        image_urls = ["https://motionarray.imgix.net/preview-165955-sHrBnk2lYE-high_0005.jpg"]
        random_image = random.choice(image_urls)
        viewer_message = viewer_messages.get(viewer_name, "No new messages")
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
                    #viewerImage {{
                        transition: all 0.1s ease;  // Smooth transition for image transformation
                    }}
                </style>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.0/socket.io.js"></script>
            </head>
            <body>
                <h1>Welcome, {viewer_name}!</h1>
                <img id="viewerImage" src="{random_image}" alt="Random Image" width="200" height="200">
                <p id="latestMessage">Latest Message: {viewer_message}</p>
                <script>
                    const socket = io();
                    
                    socket.on('start_animation', function(data) {{
                        const duration = data.duration;
                        startSquashAndStretchAnimation(duration);
                    }});

                    function squashAndStretch(isSquashing) {{
                        const image = document.getElementById('viewerImage');
                        if (isSquashing) {{
                            image.style.width = '250px';  // Squash
                            image.style.height = '150px';
                        }} else {{
                            image.style.width = '200px';  // Stretch back to original size
                            image.style.height = '200px';
                        }}
                    }}

                    function startSquashAndStretchAnimation(duration) {{
                        const image = document.getElementById('viewerImage');
                        const interval = duration / 10;  // Adjust this based on desired animation frequency

                        let isSquashing = true;
                        const animation = setInterval(() => {{
                            squashAndStretch(isSquashing);
                            isSquashing = !isSquashing;
                        }}, interval * 1000);

                        setTimeout(() => {{
                            clearInterval(animation);
                            squashAndStretch(false);  // Reset to original state
                        }}, duration * 1000);
                    }}

                    function updateMessage() {{
                        fetch('/viewer/{viewer_name}/message')
                            .then(response => response.json())
                            .then(data => {{
                                document.getElementById("latestMessage").innerText = "Latest Message: " + data.message;
                            }})
                            .catch(error => console.error('Error:', error));
                    }}
                        setInterval(updateMessage, 500); // Update every 0.5 seconds
                    </script>
                </body>
            </html>
        '''
    else:
        return "Viewer not found", 404

@app.route('/viewer/<viewer_name>/message')
def get_viewer_message(viewer_name):
    global selected_viewers
    if viewer_name in selected_viewers:
        viewer_message = viewer_messages.get(viewer_name, "No new messages")
        return jsonify({"message": viewer_message})
    else:
        return jsonify({"message": "Viewer not found"}), 404

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
    socketio.run(app, debug=False, port=5000, use_reloader=False)

flask_thread = Thread(target=run_flask_app, daemon=True)
flask_thread.start()

# Initialize PyAudio for TTS audio monitoring
py_audio = pyaudio.PyAudio()
audio_stream = py_audio.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)

speech_folder = "viewer_speeches"
if not os.path.exists(speech_folder):
    os.mkdir(speech_folder)

# Assuming the functions analyze_audio and emit_audio_data are defined elsewhere in your code

def play_audio(filename):
    # Open the audio file
    wf = wave.open(filename, 'rb')
    audio_data = wf.readframes(wf.getnframes())

    # Play audio
    play_obj = sa.play_buffer(audio_data, wf.getnchannels(), wf.getsampwidth(), wf.getframerate())

    # Wait for playback to finish
    play_obj.wait_done()

def save_tts_as_wav(text, filename):
    tts = gTTS(text=text, lang='en')
    tts.save("temp.mp3")
    sound = AudioSegment.from_mp3("temp.mp3")
    sound.export(filename, format="wav")
    os.remove("temp.mp3")
    print("Saved TTS as WAV")

def speak_message(message, username, subtitle, socket):
    # Generate speech from text
    language = 'en'
    username = username[:5]  # Make username the first 5 letters of their name
    text = f"{username} says {message}"
    
    # Create a unique filename for each user
    tts_filename = f"{speech_folder}/{username}.wav"
    
    # Generate and save speech as WAV
    save_tts_as_wav(text, tts_filename)

    # Update GUI - assuming you have a GUI setup
    dpg.set_value(message_display, f"{username}: {message}")
    dpg.configure_item(message_display, color=[255, 255, 255], bullet=True)

    sound = AudioSegment.from_file(tts_filename)
    duration = len(sound) / 1000.0  # Duration in seconds

    # Emit a start signal for animation
    socketio.emit('start_animation', {'duration': duration})

    # Start playing the sound in a separate thread and send audio data
    threading.Thread(target=play_audio, args=(tts_filename,)).start()

def save_tokens(access_token, refresh_token, user_id, user_name):
    with open(TOKEN_FILE, 'w') as file:
        json.dump({'access_token': access_token, 'refresh_token': refresh_token, 'user_id': user_id, 'user_name': user_name}, file)

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as file:
            return json.load(file)
    return None

class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
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
                response = requests.post(token_url, data=payload)
                if response.status_code == 200:
                    access_token = response.json().get('access_token')
                    refresh_token = response.json().get('refresh_token')
                    authentication_complete(access_token, refresh_token)
                else:
                    print("Authentication failed. Response:", response.json())

                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(bytes("<html><body><script>window.close();</script>Authentication successful. You can close this tab.</body></html>", "utf-8"))
            else:
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(bytes("<html><body>Authentication failed. Please try again.</body></html>", "utf-8"))

def authentication_complete(access_token, refresh_token):
    global TWITCH_USER_ID, IS_AUTHENTICATED
    user_id = get_user_id(access_token)
    user_name = get_user_name(access_token)
    if user_id and user_name:
        save_tokens(access_token, refresh_token, user_id, user_name)
        TWITCH_USER_ID = user_id
        IS_AUTHENTICATED = True  # Set authentication status to True
        print("Authentication successful! Token: ", access_token, "Refresh Token: ", refresh_token, "User ID: ", user_id, "User Name: ", user_name)
        dpg.set_value(auth_status, "Authenticated")
        dpg.configure_item(auth_status, color=[0, 255, 0])

def get_user_id(access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get('https://id.twitch.tv/oauth2/validate', headers=headers)
    if response.status_code == 200:
        user_id = response.json().get('user_id')
        print(f"User ID: {user_id}")
        return user_id
    else:
        print(f"Failed to validate token: {response.text}")
        return None
    
def get_user_name(access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get('https://id.twitch.tv/oauth2/validate', headers=headers)
    if response.status_code == 200:
        user_name = response.json().get('login')
        print(f"User Name: {user_name}")
        return user_name
    else:
        print(f"Failed to validate token: {response.text}")
        return None

def authenticate_with_twitch():
    #start the server in a new thread
    Thread(target=run_auth_server).start()
    webbrowser.open(AUTH_URL)

def run_auth_server():
    httpd = HTTPServer(('localhost', 3000), AuthHandler)
    print("Starting HTTP server for authentication...")
    httpd.serve_forever()

def cancel_auth():
    print("Cancel Auth Clicked")
    IS_AUTHENTICATED = False
    #delete the tokens file
    os.remove(TOKEN_FILE)
    #reset the auth status
    dpg.set_value(auth_status, "Not Authenticated")
    dpg.configure_item(auth_status, color=[255, 0, 0])

# Function to get chatters' usernames and pick a random one
def get_random_chatter(channel_name, moderator_id, token, client_id, num_viewers=1):

    # Get the broadcaster ID
    broadcaster_id = get_broadcaster_id(client_id, token, channel_name)

    chatters_url = f'https://api.twitch.tv/helix/chat/chatters?broadcaster_id={broadcaster_id}&moderator_id={moderator_id}'

    headers = {
        'Authorization': f'Bearer {token}',
        'Client-Id': client_id
    }

    chatters_resp = requests.get(chatters_url, headers=headers)

    if chatters_resp.status_code != 200:
        print('Failed to get chatters', chatters_resp.status_code, chatters_resp.text)
        
        try:
            error_json = chatters_resp.json()
            error_message = error_json.get("message", "Unknown error occurred")

            # Check for specific phrases in the error message
            if "does not have moderator permissions" in error_message:
                simplified_error_message = "Not a Mod on that Channel, try another"
            else:
                simplified_error_message = error_message  # or some other default message

        except json.JSONDecodeError:
            simplified_error_message = "Failed to parse error message"

        dpg.set_value(error_display, f"Error: {simplified_error_message}")
        #set the color of the error message to red
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message()
        return None

    chatters_data = chatters_resp.json()
    chatters_list = chatters_data.get('data', [])

    if not chatters_list:
        print('No chatters found')
        return None

    usernames = [chatter['user_name'] for chatter in chatters_list]
    #pick that many random viewers
    try:
        random_chatters = random.sample(usernames, num_viewers)
    except ValueError:
        print("Not enough viewers to pick from")
        dpg.set_value(error_display, f"Error: Not enough viewers to pick from")
        #set the color of the error message to red
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message()
        return None
    #print the random viewers
    print(random_chatters)
    #set the value of the user_display to the random viewer
    random_chatters_str = ', '.join(random_chatters)
    dpg.set_value(user_display, random_chatters_str)
    #make the color white
    dpg.configure_item(user_display, color=[255, 255, 255])
    #make the chatters name bold
    dpg.configure_item(user_display, bullet=True)

def get_random_chatter_raffle(num_viewers=1):
    global entered_users  # Make sure to use the global list

    # Check if enough users have entered
    if len(entered_users) < num_viewers:
        print("Not enough viewers to pick from")
        dpg.set_value(error_display, f"Error: Not enough viewers to pick from")
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message()
        return None

    # Select random viewers from entered_users
    try:
        random_chatters = random.sample(entered_users, num_viewers)
    except ValueError:
        print("Error in selecting random viewers")
        return None

    # Print and display the selected viewers
    print(random_chatters)
    random_chatters_str = ', '.join(random_chatters)
    dpg.set_value(user_display, random_chatters_str)
    dpg.configure_item(user_display, color=[255, 255, 255])
    dpg.configure_item(user_display, bullet=True)

    # Clear the entered users list for the next raffle
    entered_users.clear()
    print("The raffle is complete. The entered users list has been cleared for the next raffle.")



def get_broadcaster_id(client_id, token, channel_login):
    url = f"https://api.twitch.tv/helix/users?login={channel_login}"
    headers = {
        'Authorization': f'Bearer {token}',
        "Client-ID": client_id,
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            print(f"Found channel '{channel_login}' with ID {data['data'][0]['id']}")
            return data["data"][0]["id"]
        else:
            print(f"Channel '{channel_login}' not found.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")

    return None

def pick_random_viewer_callback():
    global selected_channel
    global entered_users
    print("Pick Random Viewer Clicked")
    if dpg.get_value(user_data) == None or dpg.get_value(user_data) == "" or dpg.get_value(user_data) == "31" or dpg.get_value(user_data) == " ": #check if the channel name is empty
        print("No channel name entered")
        dpg.set_value(error_display, f"Error: No channel name entered")
        #set the color of the error message to red
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message()
        return None
    
    #check if twitch is on
    if dpg.get_value(enabled) == "Twitch is off :(":
        print("Twitch is off")
        dpg.set_value(error_display, f"Error: Twitch is off")
        #set the color of the error message to red
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message()
        return None

    try:
        access_token = load_tokens()['access_token']
    except(ValueError):
        print("No access token found")
        dpg.set_value(error_display, f"Error: No access token found")
        #set the color of the error message to red
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message()
        return None
    user_id = load_tokens()['user_id']
    
    # Retrieve the channel name from the input field
    channel_name = dpg.get_value(user_data)
    print(channel_name)
    
    # Update the selected_channel variable
    selected_channel = channel_name
    
    # Check the states of the checkboxes
    vip_only = dpg.get_value(vip_box)
    mod_only = dpg.get_value(mod_box)
    sub_only = dpg.get_value(sub_box)
    follower_only = dpg.get_value(follower_box)
    tts_enabled = dpg.get_value(tts_box)
    raffle_box = dpg.get_value(raffle_checkbox)

    num_viewers = dpg.get_value(viewer_number_picker)
    selected_viewer_count = num_viewers

    if vip_only:
        pass
        # Logic to pick from VIPs only
        # Call a different function with appropriate parameters
        # Example: get_random_vip_chatter(selected_channel, user_id, access_token, CLIENT_ID)
    elif mod_only:
        pass
        # Logic to pick from Mods only
        # Call a different function with appropriate parameters
        # Example: get_random_mod_chatter(selected_channel, user_id, access_token, CLIENT_ID)
    elif sub_only:
        pass
        # Logic to pick from Subs only
        # Call a different function with appropriate parameters
        # Example: get_random_sub_chatter(selected_channel, user_id, access_token, CLIENT_ID)
    elif follower_only:
        pass
        # Logic to pick from Followers only
        # Call a different function with appropriate parameters
        # Example: get_random_follower_chatter(selected_channel, user_id, access_token, CLIENT_ID)
    elif raffle_box:
        # Logic to pick from all chatters
        get_random_chatter_raffle(num_viewers)
    else:
        # Default logic (pick from all chatters)
        get_random_chatter(selected_channel, user_id, access_token, CLIENT_ID, num_viewers)

    #check if a socket is already open
    #if tts_enabled:
    #    try:
    #        twitch_sock.close()
    #        print("Socket closed")
    #    except:
    #        pass
    #    start_streaming()

def start_twitch_button_callback():
    #check if a socket is already open
        print("Start Twitch Clicked")
        if dpg.get_value(user_data) == None or dpg.get_value(user_data) == "" or dpg.get_value(user_data) == "31" or dpg.get_value(user_data) == " ": #check if the channel name is empty
            print("No channel name entered")
            dpg.set_value(error_display, f"Error: No channel name entered")
            #set the color of the error message to red
            dpg.configure_item(error_display, color=[255, 0, 0])
            clear_error_message()
            return None
        try:
            twitch_sock.close()
            print("Socket closed")
            dpg.set_value(enabled, "Twitch is off :(")
            dpg.configure_item(enabled, color=[255, 0, 0])
        except:
            pass
        #set the text of enabled to true
        start_streaming()


server = 'irc.chat.twitch.tv'
port = 6667

def connect_to_twitch():
    global twitch_sock

    # Close existing socket connection if open
    if twitch_sock is not None:
        try:
            twitch_sock.close()
            print("Previous socket closed")
        except Exception as e:
            print(f"Error closing socket: {e}")
    try:
        access_token = load_tokens()['access_token']
    except(TypeError):
        #this means that the tokens file is empty
        print("No access token found")
        dpg.set_value(error_display, f"Error: No access token found")
        #set the color of the error message to red
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message()
    user_name = load_tokens()['user_name']
    channel_namestr = dpg.get_value(user_data)
    channel_nameLow = str(channel_namestr).lower()
    channel_name = "#" + channel_nameLow

    if dpg.get_value(tts_box):
        print(f"Connecting to channel: {channel_name}")
        try:
            twitch_sock = socket.socket()
            twitch_sock.connect((server, port))
            twitch_sock.send(f"PASS oauth:jrx6m97t36yqkf5rgdn5gmb6n9dllb\n".encode('utf-8'))
            twitch_sock.send(f"NICK {user_name}\n".encode('utf-8'))
            twitch_sock.send(f"JOIN {channel_name}\n".encode('utf-8'))
            print("Connected to Twitch IRC")
            return twitch_sock
        except Exception as e:
            print(f"Error connecting to socket: {e}")
            return None
    else:
        print("TTS not enabled")
        return None

def receive_messages(twitch_sock):
    # Get manually selected viewers
    num_viewers = dpg.get_value("num_viewers_input")
    selected_viewer_count = num_viewers
    selected_viewers_manual = [dpg.get_value(f"viewer_selection_{i}").lower() for i in range(num_viewers) if dpg.get_value(f"viewer_selection_{i}").strip()]
    print(f"Selected viewers manual: {selected_viewers_manual}")

    # Get randomly picked viewers from user_display
    user_display_str = dpg.get_value(user_display)
    print(f"User display string: {user_display_str}")
    selected_viewers_random = [viewer.strip().lower() for viewer in user_display_str.split(", ") if viewer.strip()]
    print(f"Selected viewers random: {selected_viewers_random}")

    # Combine both lists and remove duplicates
    global selected_viewers
    selected_viewers = list(set(selected_viewers_manual + selected_viewers_random))
    print(f"Combined selected viewers: {selected_viewers}")

    if twitch_sock is None:
        print("Socket is None, not receiving messages.")
        return

    try:
        while True:
            try:
                resp = twitch_sock.recv(2048).decode('utf-8')
                if len(resp) > 0:
                    if not resp.startswith(":tmi.twitch.tv"):
                        parts = resp.split(' ')
                        username = parts[0].split('!')[0][1:]
                        message_start_index = resp.find(" :") + 2
                        message = resp[message_start_index:]

                        if "!talk" in message.lower():
                            handle_enter_command(username)

                        if username.lower() in (viewer.lower() for viewer in selected_viewers):
                            print(f"{username}: {message}")
                            speak_message(message, username, message, twitch_sock)
                            update_viewer_message(username, message)
                        else:
                            print("Message not from selected viewer, ignoring.")
                    else:
                        print("Server message received, ignoring.")
            except socket.error as e:
                print(f"Socket error: {e}")
                break
    except KeyboardInterrupt:
        pass
    finally:
        twitch_sock.close()

def clear_entered_users():
    entered_users.clear()
    print("Entered users list cleared.")

def start_streaming():
    global twitch_sock
    twitch_sock = connect_to_twitch()
    if twitch_sock:
        dpg.set_value(enabled, "Twitch is on :)")
        dpg.configure_item(enabled, color=[0, 255, 0])
        # Start receive_messages in a new thread
        thread = Thread(target=receive_messages, args=(twitch_sock,))
        thread.start()

def initialize_authentication_status():
    # Check if there are saved tokens and validate them
    global IS_AUTHENTICATED
    saved_tokens = load_tokens()
    if saved_tokens:
        access_token = saved_tokens['access_token']
        print("Validating saved token...")
        if get_user_id(access_token):
            IS_AUTHENTICATED = True
            print("Token is valid!")

def clear_error_message():
    # Wait for 5 seconds
    threading.Timer(10.0, lambda: dpg.set_value(error_display, "")).start()
    #clear the bullet
    threading.Timer(10.0, lambda: dpg.configure_item(error_display, bullet=False)).start()

def select_manual_viewer_callback(sender, app_data, user_data):
    if dpg.get_value(user_data) == None or dpg.get_value(user_data) == "" or dpg.get_value(user_data) == "31" or dpg.get_value(user_data) == " ": #check if the channel name is empty
        print("No channel name entered")
        dpg.set_value(error_display, f"Error: No channel name entered")
        #set the color of the error message to red
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message()
        return None
    
    #check if twitch is on
    if dpg.get_value(enabled) == "Twitch is off :(":
        print("Twitch is off")
        dpg.set_value(error_display, f"Error: Twitch is off")
        #set the color of the error message to red
        dpg.configure_item(error_display, color=[255, 0, 0])
        clear_error_message()
        return None

    num_viewers = dpg.get_value("num_viewers_input")
    selected_viewer_count = num_viewers
    selected_viewers = []

    for i in range(num_viewers):
        viewer_selection_tag = f"viewer_selection_{i}"
        if dpg.does_item_exist(viewer_selection_tag):
            selected_viewer = dpg.get_value(viewer_selection_tag)
            if selected_viewer:
                selected_viewers.append(selected_viewer)

    print(f"Manually selected viewers: {selected_viewers}")
    access_token = load_tokens()['access_token']
    user_id = load_tokens()['user_id']
    
    # Retrieve the channel name from the input field
    channel_name = dpg.get_value(user_data)
    print(channel_name)
    
    # Update the selected_channel variable
    selected_channel = channel_name
    
    # Check the states of the checkboxes
    vip_only = dpg.get_value(vip_box)
    mod_only = dpg.get_value(mod_box)
    sub_only = dpg.get_value(sub_box)
    follower_only = dpg.get_value(follower_box)
    tts_enabled = dpg.get_value(tts_box)

    #check if a socket is already open
    #if tts_enabled:
    #    try:
    #        twitch_sock.close()
    #        print("Socket closed")
    #    except:
    #        pass
    #    start_streaming()


def update_viewers_list(channel_name, user_id, token, client_id):
    global viewers_list

    broadcaster_id = get_broadcaster_id(client_id, token, channel_name)
    moderator_id = user_id
    chatters_url = f'https://api.twitch.tv/helix/chat/chatters?broadcaster_id={broadcaster_id}&moderator_id={moderator_id}'

    headers = {
        'Authorization': f'Bearer {token}',
        'Client-Id': client_id
    }

    chatters_resp = requests.get(chatters_url, headers=headers)
    if chatters_resp.status_code == 200:
        chatters_data = chatters_resp.json()
        viewers_list = [chatter['user_name'] for chatter in chatters_data.get('data', [])]
        num_viewers = dpg.get_value("num_viewers_input")
        selected_viewer_count = num_viewers
        for i in range(num_viewers):
            viewer_selection_tag = f"viewer_selection_{i}"
            if dpg.does_item_exist(viewer_selection_tag):
                dpg.configure_item(viewer_selection_tag, items=viewers_list)
    else:
        print('Failed to get chatters', chatters_resp.status_code, chatters_resp.text)
        dpg.set_value(error_display, f"Error: {chatters_resp.status_code} {chatters_resp.text}")

def update_viewers_list_callback():
    channel_name = dpg.get_value(user_data)
    access_token = load_tokens()['access_token']
    user_id = load_tokens()['user_id']
    client_id = CLIENT_ID

    if channel_name:
        update_viewers_list(channel_name, user_id, access_token, client_id)
    else:
        print("Please enter a channel name.")

#clear random viewer selection
def clear_random_viewer_callback():
    dpg.set_value(user_display, "")
    #remove the bullet
    dpg.configure_item(user_display, bullet=False)
    global selected_viewers
    selected_viewers = []

def clear_specific_viewer_callback():
    num_viewers = dpg.get_value("num_viewers_input")
    selected_viewer_count = num_viewers
    for i in range(num_viewers):
        viewer_selection_tag = f"viewer_selection_{i}"
        if dpg.does_item_exist(viewer_selection_tag):
            dpg.set_value(viewer_selection_tag, "")
            global selected_viewers
            selected_viewers = []

def update_viewer_selection_boxes(num_viewers):
    # Ensure the previous viewer selection boxes are removed
    if dpg.does_item_exist("viewer_selection_group"):
        dpg.delete_item("viewer_selection_group")

    with dpg.group(parent="manual_viewer_picker", horizontal=False, tag="viewer_selection_group"):
        for i in range(num_viewers):
            dpg.add_combo(label=f"Viewer {i+1}", items=viewers_list, tag=f"viewer_selection_{i}", width=175, callback=select_manual_viewer_callback)

def on_viewer_number_change(sender, app_data, user_data):
    num_viewers = dpg.get_value(sender)
    selected_viewer_count = num_viewers
    update_viewer_selection_boxes(num_viewers)


initialize_authentication_status()

# GUI Code
dpg.create_context()
dpg.create_viewport(title='Chattastic', height=500, width=400, resizable=False)
dpg.setup_dearpygui()

with dpg.window(label="Chattastic", tag='chat', no_resize=True,):
    #set chat as primary window
    dpg.set_primary_window("chat", True)
    # add text saying authentication status
    with dpg.group(horizontal=True):
        dpg.add_text("Authentication Status:")
        auth_status = (dpg.add_text("Not Authenticated", color=(255, 0, 0), wrap=390) if not IS_AUTHENTICATED else dpg.add_text("Authenticated", color=(0, 255, 0), wrap=390))

    with dpg.collapsing_header(label="Auth"):
        with dpg.group(horizontal=True):
            dpg.add_button(label="Authenticate with Twitch", callback=authenticate_with_twitch)
            # cancel auth button on the same line
            dpg.add_button(label="Cancel Auth", callback=cancel_auth, enabled=IS_AUTHENTICATED)
            
    #audio header
    #with dpg.collapsing_header(label="Audio"):
    #    dpg.add_spacer(height=3)
    #    microphone_selecter = dpg.add_combo(label="Microphones", items=get_audio_devices()[0], default_value="Please Select a Microphone")
    #    speaker_selecter = dpg.add_combo(label="Speakers", items=get_audio_devices()[1], default_value="Please Select a Speaker")
    #    dpg.add_spacer(height=3)

    with dpg.collapsing_header(label="Viewers"):
        dpg.add_spacer(height=2)
        user_data = dpg.add_input_text(label="Channel Name", hint="Enter Channel Name", width=175)
        dpg.add_spacer(height=2)
        viewer_number_picker = dpg.add_input_int(label="Number of Viewers", tag="num_viewers_input", default_value=1, min_value=1, width=175, callback=on_viewer_number_change, min_clamped=True)
        dpg.add_spacer(height=2)
        with dpg.group(horizontal=True):
            start_twitch_button = dpg.add_button(label="Start Twitch", callback=start_twitch_button_callback)
            enabled = dpg.add_text("Twitch is off :(", wrap=390, label="is_twitch_enabled", color=(255, 0, 0))
        dpg.add_text("Note: You will need to Start Twitch before doing anything.", wrap=390)
        dpg.add_spacer(height=2)
        tts_box = dpg.add_checkbox(label="Read Viewer Messages in TTS (Text-to-Speech)", default_value=True)
        dpg.add_spacer(height=2)
        dpg.add_button(label="Open Pages", callback=open_viewer_pages)
        dpg.add_spacer(height=2)
        # add another dropdown inside of this one labeled "Random Viewer Picker"
        with dpg.tree_node(label="Select Viewer Randomly"):
            dpg.add_spacer(height=2)
            raffle_checkbox = dpg.add_checkbox(label="Raffle Mode")         
            with dpg.group(horizontal=True):
                dpg.add_button(label="Pick Random Viewer", callback=pick_random_viewer_callback)
                dpg.add_button(label="Clear Viewer", callback=clear_random_viewer_callback)
                # add a button labeled "Clear Viewer" with a callback to clear_selection
                # add a text label with the selected viewer name

            user_display = dpg.add_text("", wrap=390, label="user display")

            #space out
            dpg.add_spacer(height=2)
            vip_box = dpg.add_checkbox(label="VIPs Only (WIP)")
            mod_box = dpg.add_checkbox(label="Mods Only (WIP)")
            sub_box = dpg.add_checkbox(label="Subs Only (WIP)")
            follower_box = dpg.add_checkbox(label="Followers Only (WIP)")
            dpg.add_spacer()

        with dpg.tree_node(label="Select Viewer Manually", tag="manual_viewer_picker"):
            dpg.add_spacer(height=2)
            # Group for dynamic viewer selection combo boxes
            with dpg.group(horizontal=True):
                update_button = dpg.add_button(label="Update Viewer List", callback=update_viewers_list_callback)
                dpg.add_button(label="Clear Viewer", callback=clear_specific_viewer_callback)

            manual_viewer_selection = dpg.add_group(tag="manual_viewer_selection")
            update_viewer_selection_boxes(1)  # Initialize with 1 viewer selection combo box

        #message display
        dpg.add_spacer(height=2)
        #dpg.add_text("Message:")
        message_display = dpg.add_text("", wrap=390, label="Messages")

        #error display
        dpg.add_spacer(height=2)
        #dpg.add_text("Error Display:")
        error_display = dpg.add_text("", wrap=390, label="error_display")
    
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()

#Sociology Google Classroom Code: fwhtqtp