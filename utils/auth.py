import os
import json
import logging
import threading
import time
import requests
import traceback
import webbrowser
import socket
import base64
import hashlib
import urllib.parse
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from threading import Thread

import config
import dearpygui.dearpygui as dpg

def save_tokens(access_token, refresh_token, user_id, user_name):
    with open(config.TOKEN_FILE, 'w') as file:
        json.dump({'access_token': access_token, 'refresh_token': refresh_token, 'user_id': user_id, 'user_name': user_name}, file)

def load_tokens():
    if os.path.exists(config.TOKEN_FILE):
        try:
            with open(config.TOKEN_FILE, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {config.TOKEN_FILE}. File might be corrupted.")
            # Optionally, delete or rename the corrupted file
            # os.remove(config.TOKEN_FILE)
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
                    'client_id': config.CLIENT_ID,
                    'client_secret': config.CLIENT_SECRET,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': config.REDIRECT_URI
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
    user_id = get_user_id(access_token)
    user_name = get_user_name(access_token)
    if user_id and user_name:
        save_tokens(access_token, refresh_token, user_id, user_name)
        config.TWITCH_USER_ID = user_id
        config.IS_AUTHENTICATED = True  # Set authentication status to True
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
    headers = {'Authorization': f'Bearer {access_token}', 'Client-Id': config.CLIENT_ID} # Add Client-ID for Helix
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
    headers = {'Authorization': f'Bearer {access_token}', 'Client-Id': config.CLIENT_ID}
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


# Global reference to the auth server instance
httpd_server = None
auth_server_thread = None

def authenticate_with_twitch():
    # Use a flag or check thread status to prevent multiple auth servers
    global auth_server_thread
    if auth_server_thread is not None and auth_server_thread.is_alive():
        print("Authentication server is already running.")
        # Optionally bring the browser window to the front if possible/needed
        webbrowser.open(config.AUTH_URL) # Re-open auth URL in case user closed tab
        return

    auth_server_thread = Thread(target=run_auth_server, daemon=True) # Make daemon
    auth_server_thread.start()
    # Give server a moment to start before opening browser
    time.sleep(1)
    webbrowser.open(config.AUTH_URL)

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
    config.IS_AUTHENTICATED = False
    config.TWITCH_USER_ID = None
    # Attempt to delete the tokens file
    if os.path.exists(config.TOKEN_FILE):
        try:
            os.remove(config.TOKEN_FILE)
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
            'client_id': config.KICK_CLIENT_ID,
            'redirect_uri': config.KICK_REDIRECT_URI,
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
            'client_id': config.KICK_CLIENT_ID,
            'client_secret': config.KICK_CLIENT_SECRET,
            'code': self.authorization_code,
            'redirect_uri': config.KICK_REDIRECT_URI,
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