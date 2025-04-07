import os
import logging

# Set logging level to WARNING to reduce console output
# This will stop logging every GET request
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Twitch application credentials
CLIENT_ID = 'qwfkkoq2roz77rvmauhnmhqr4ckvwt'
CLIENT_SECRET = 'm982e7esph7u5i0tohecryq4ml48z3' # Keep secret secure in production
REDIRECT_URI = 'http://localhost:3000/'
SCOPE = 'user:read:email channel:read:vips channel:read:subscriptions moderation:read moderator:read:chatters moderator:read:followers'
TOKEN_FILE = 'twitch_tokens.json'
AUTH_URL = f"https://id.twitch.tv/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope={SCOPE}"
TWITCH_USER_ID = None  # Store the user ID after authentication
IS_AUTHENTICATED = False  # Flag to track authentication status

# Kick Credentials
KICK_CLIENT_ID = '01JR6H958JM9ZCH9T2F2WVECYW'
KICK_CLIENT_SECRET = 'f9c6a68fdd6b010639be87b8902dc54f0ae62c087008e6533263b6453573cf67'
KICK_REDIRECT_URI = 'http://localhost:3000/'

# Global variables
selected_channel = ""
selected_viewer = ""
viewers_list = []
entered_users = []
audio_threads = []
selected_viewer_count = 1
twitch_sock = None
selected_viewers = []
viewer_messages = {}

# Directories
speech_folder = "viewer_speeches"
if not os.path.exists(speech_folder):
    os.makedirs(speech_folder, exist_ok=True)