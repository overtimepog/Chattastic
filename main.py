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

import warnings
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

global sock
sock = None

# Initialize PyAudio for TTS audio monitoring
py_audio = pyaudio.PyAudio()
audio_stream = py_audio.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)

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

def play_audio(filename):
    # This function will play audio to the default output device, 
    # which should be set to VB-Cable in your system settings.
    try:
        with wave.open(filename, 'rb') as wf:
            samplerate = wf.getframerate()
            channels = wf.getnchannels()
            dtype = 'int16'

            stream = sd.OutputStream(channels=channels, 
                                     samplerate=samplerate,
                                     dtype=dtype)
            
            with stream:
                data = wf.readframes(wf.getnframes())
                samples = np.frombuffer(data, dtype=dtype)
                samples = samples.reshape(-1, channels)
                stream.write(samples)

    except Exception as e:
        print(f"Error: {e}")

def speak_message(message, username, subtitle):
    # Generate speech from text
    language = 'en'
    tts_object = gTTS(text=message, lang=language, slow=False)
    tts_filename = "temp_message.mp3"
    tts_object.save(tts_filename)

    # Start playing the sound in a separate thrssead
    dpg.set_value(message_display, f"{username}: {message}")
    #make the color white
    dpg.configure_item(message_display, color=[255, 255, 255])
    #make the chatters name bold
    dpg.configure_item(message_display, bullet=True)
    microphone = dpg.get_value(microphone_selecter)
    speaker = dpg.get_value(speaker_selecter)
    threading.Thread(target=play_audio, args=(tts_filename)).start()

    # Analyze and visualize the audio with username and subtitle
    #analyze_and_visualize(tts_filename, username, subtitle)

    # Clean up the temporary file after some delay
    #time.sleep(10)  # Adjust the delay as needed
    os.remove(tts_filename)

def visualize_in_separate_window(audio_file, username, subtitle):
    # Function to run the visualizer in a separate thread
    def run_visualizer():
        dpg.create_context()
        with dpg.window(label="Audio Visualization"):
            username_id = dpg.add_text(username, color=[250, 250, 250])
            image_id = dpg.add_image("C:\\Users\\truen\\Documents\\GitHub\\Chattastic\\image.png")  # Replace with your image path
            dpg.add_text(subtitle, color=[250, 250, 250], pos=[10, 260])  # Static subtitle at the bottom

        dpg.create_viewport(title='Custom Visualization', width=600, height=300)
        dpg.setup_dearpygui()
        dpg.show_viewport()

        # Open the audio file
        wf = wave.open(audio_file, 'rb')
        frame_rate = wf.getframerate()

        # Process audio and update image and username position
        while True:
            frames = wf.readframes(frame_rate // 10)  # Read frames for 0.1 seconds
            if not frames:
                break

            # Analyze volume
            volume = audioop.rms(frames, wf.getsampwidth())

            # Map volume to image and username position
            min_pos = 100
            max_pos = 200
            pos = min_pos + (max_pos - min_pos) * volume / 32768

            # Update image and username position
            dpg.set_item_pos(image_id, (100, pos))
            dpg.set_item_pos(username_id, (100, pos - 20))  # Adjust username position relative to the image

            # Render the DearPyGui frame
            dpg.render_dearpygui_frame()
            time.sleep(0.1)

        wf.close()
        dpg.destroy_context()

    visualizer_thread = threading.Thread(target=run_visualizer)
    visualizer_thread.start()

def analyze_and_visualize(audio_file, username, subtitle):
    # Call the separate window function
    visualize_in_separate_window(audio_file, username, subtitle)


def save_callback():
    print("Save Clicked")
    authenticate_with_twitch()

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
def get_random_chatter(channel_name, moderator_id, token, client_id):

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
    random_chatter = random.choice(usernames)
    
    print(f"Random chatter: {random_chatter.lower()}")
    dpg.set_value(user_display, random_chatter.lower())
    #make the color white
    dpg.configure_item(user_display, color=[255, 255, 255])
    #make the chatters name bold
    dpg.configure_item(user_display, bullet=True)


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
    print("Pick Random Viewer Clicked")
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
    else:
        # Default logic (pick from all chatters)
        get_random_chatter(selected_channel, user_id, access_token, CLIENT_ID)

    #check if a socket is already open
    if tts_enabled:
        try:
            sock.close()
            print("Socket closed")
        except:
            pass
        start_streaming()


server = 'irc.chat.twitch.tv'
port = 6667

def connect_to_twitch():
    global sel_viewer, sock

    # Close existing socket connection if open
    if sock is not None:
        try:
            sock.close()
            print("Previous socket closed")
        except Exception as e:
            print(f"Error closing socket: {e}")
    access_token = load_tokens()['access_token']
    user_name = load_tokens()['user_name']
    channel_namestr = dpg.get_value(user_data)
    channel_nameLow = str(channel_namestr).lower()
    channel_name = "#" + channel_nameLow
    sel_viewer = dpg.get_value(user_display)
    sel_viewer = dpg.get_value(viewer_selection_id)

    # Check if selected_viewer is not empty and tts_box is checked
    if sel_viewer and dpg.get_value(tts_box):
        print(f"Connecting to channel: {channel_name} for viewer: {sel_viewer}")
        try:
            sock = socket.socket()
            sock.connect((server, port))
            sock.send(f"PASS oauth:jrx6m97t36yqkf5rgdn5gmb6n9dllb\n".encode('utf-8'))
            sock.send(f"NICK {user_name}\n".encode('utf-8'))
            sock.send(f"JOIN {channel_name}\n".encode('utf-8'))
            print("Connected to Twitch IRC")
            return sock
        except Exception as e:
            print(f"Error connecting to socket: {e}")
            return None
    else:
        print("Viewer not selected or TTS not enabled")
        return None

def receive_messages(sock):
    global sel_viewer
    sel_viewer = dpg.get_value(user_display)
    sel_viewer = dpg.get_value(viewer_selection_id)
    if sock is None:
        print("Socket is None, not receiving messages.")
        return
    
    if sel_viewer is None:
        print("Viewer is None, not receiving messages.")
        return

    try:
        while True:
            try:
                resp = sock.recv(2048).decode('utf-8')
                if len(resp) > 0:
                    #if f':{sel_viewer}!' in resp:
                    #print(resp)
                    #tts code to read the message :)
                    # Extract the message from 'resp' and pass it to speak_message
                    #:skelegem!skelegem@skelegem.tmi.twitch.tv
                    #remove the skelegem@skelegem.tmi.twitch.tv from the message 
                    if not resp.startswith(":tmi.twitch.tv"):
                        # It's a user message, process it
                        # Splitting the response to get different parts
                        parts = resp.split(' ')

                        # Extracting the username
                        username = parts[0].split('!')[0][1:] # Removes the leading ':' and splits at '!', taking the first part

                        # Extracting the message
                        message_start_index = resp.find(" :") + 2 # Finds the start of the message and adjusts to get the right index
                        message = resp[message_start_index:]

                        # Combining username and message
                        formatted_message = f"{username}: {message}"

                        print(formatted_message)
                        viwer = sel_viewer.lower()
                        if username == viwer:
                            print("Selected viewer message received, reading aloud.")
                            speak_message(message, username, message)
                    else:
                        # It's a server message, ignore it
                        print("Server message received, ignoring.")
                    #username, channel, message = re.search(r':(.*)\!.*@.*\.tmi\.twitch\.tv PRIVMSG #(.*) :(.*)', username_message).groups()
                    #print(f"Channel: {channel} \nUsername: {username} \nMessage: {message}")
                    #speak_message(message, username, message)

            except socket.error as e:
                print(f"Socket error: {e}")
                break  # Exit the loop if there's a socket error
    except KeyboardInterrupt:
        pass  # Handle interrupt gracefully
    finally:
        sock.close()  # Ensure the socket is closed properly

def start_streaming():
    global sock
    sock = connect_to_twitch()
    if sock:
        # Start receive_messages in a new thread
        thread = Thread(target=receive_messages, args=(sock,))
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

def select_manual_viewer_callback():
    selected_viewer = dpg.get_value(viewer_selection_id)
    print(f"Manually selected viewer: {selected_viewer}")
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
    else:
        # Default logic (pick from all chatters)
        update_viewers_list(selected_channel, user_id, access_token, CLIENT_ID)

    #check if a socket is already open
    if tts_enabled:
        try:
            sock.close()
            print("Socket closed")
        except:
            pass
        start_streaming()


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
        dpg.configure_item(viewer_selection_id, items=viewers_list)
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

def clear_specific_viewer_callback():
    dpg.set_value(viewer_selection_id, "")
    #remove the bullet
    dpg.configure_item(viewer_selection_id, bullet=False)

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
    with dpg.collapsing_header(label="Audio"):
        dpg.add_spacer(height=3)
        microphone_selecter = dpg.add_combo(label="Microphones", items=get_audio_devices()[0], default_value="Please Select a Microphone")
        speaker_selecter = dpg.add_combo(label="Speakers", items=get_audio_devices()[1], default_value="Please Select a Speaker")
        dpg.add_spacer(height=3)

    with dpg.collapsing_header(label="Viewers"):
        dpg.add_spacer(height=2)
        user_data = dpg.add_input_text(label="Channel Name", hint="Enter Channel Name", width=200)
        dpg.add_spacer(height=2)
        tts_box = dpg.add_checkbox(label="Read Viewer Messages in TTS (Text-to-Speech)", default_value=True)
        dpg.add_text("Note: You will need to enable TTS before picking a viewer.", wrap=390)
        dpg.add_spacer(height=2)
        # add another dropdown inside of this one labeled "Random Viewer Picker"
        with dpg.tree_node(label="Select Viewer Randomly"):            
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

        with dpg.tree_node(label="Select Viewer Manually"):
            #channel name input
            dpg.add_spacer(height=2)
            #create a dropdown with the list of viewers
            viewer_selection_id = dpg.add_combo(label="Viewers", items=viewers_list, callback=select_manual_viewer_callback)
            #add a button to update the list of viewers
            with dpg.group(horizontal=True):
                update_button = dpg.add_button(label="Update Viewer List", callback=update_viewers_list_callback)
                dpg.add_button(label="Clear Viewer", callback=clear_specific_viewer_callback)
                
                #with dpg.popup(update_button, mousebutton=dpg.mvMouseButton_Left, tag="update_popup", modal=True):
                #    dpg.add_text("Viewer list updated successfully!")

                
        #message display
        dpg.add_spacer(height=2)
        dpg.add_text("Messages:")
        message_display = dpg.add_text("", wrap=390, label="Messages")

        #error display
        dpg.add_spacer(height=2)
        dpg.add_text("Error Display:")
        error_display = dpg.add_text("", wrap=390, label="error_display")
    
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()

#Sociology Google Classroom Code: fwhtqtp