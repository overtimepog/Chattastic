import os
import random
import logging
import threading
import traceback
import time
import numpy as np
import sounddevice as sd
from gtts import gTTS
from playsound import playsound
from pydub import AudioSegment
import re

import config
from ui.viewer import socketio

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

def analyze_audio(data):
    rms = np.sqrt(np.mean(np.square(data)))
    return rms

def emit_audio_data(data):
    analyzed_data = analyze_audio(data)
    print("Volume:", analyzed_data)
    socketio.emit('audio_data', {'volume': analyzed_data})

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
    import dearpygui.dearpygui as dpg
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
        # config.audio_threads.append(audio_thread)

    except Exception as e:
        print("Error in speak_message: " + str(e))
        traceback.print_exc()
