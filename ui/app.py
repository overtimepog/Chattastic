import dearpygui.dearpygui as dpg
import config
from utils.auth import authenticate_with_twitch, cancel_auth, load_tokens, KickAuth
from utils.audio import get_audio_devices
from api.twitch import get_random_filtered_chatters, get_random_chatter_raffle, start_twitch_button_callback
from ui.viewer import open_viewer_page

# --- UI Element Variables ---
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
enabled = None # For Twitch on/off status
# --- End UI Element Variables ---

def pick_random_viewer_callback():
    print("Pick Random Viewer Clicked")

    # 1. Validate Inputs & Authentication
    channel_name_input = dpg.get_value(user_data)
    if not channel_name_input or channel_name_input.isspace():
        print("No channel name entered")
        dpg.set_value(error_display, "Error: Please enter a channel name.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        from api.twitch import clear_error_message_after_delay
        clear_error_message_after_delay(5)
        return

    config.selected_channel = channel_name_input.strip().lower() # Use lower case consistently

    if not config.IS_AUTHENTICATED:
        print("Not Authenticated")
        dpg.set_value(error_display, "Error: Please authenticate with Twitch first.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        from api.twitch import clear_error_message_after_delay
        clear_error_message_after_delay(5)
        return

    tokens = load_tokens()
    if not tokens or 'access_token' not in tokens or 'user_id' not in tokens:
        print("Authentication tokens are missing or invalid.")
        dpg.set_value(error_display, "Error: Invalid or missing authentication tokens.")
        dpg.configure_item(error_display, color=[255, 0, 0])
        from api.twitch import clear_error_message_after_delay
        clear_error_message_after_delay(5)
        # Maybe try to re-authenticate or guide user?
        return

    access_token = tokens['access_token']
    moderator_id = tokens['user_id'] # The authenticated user's ID acts as moderator ID for API calls

    # 2. Get Settings from UI
    try:
        num_viewers = dpg.get_value(viewer_number_picker)
        config.selected_viewer_count = num_viewers # Update global count if needed elsewhere

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
        from api.twitch import clear_error_message_after_delay
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
            channel_name=config.selected_channel,
            moderator_id=moderator_id,
            token=access_token,
            client_id=config.CLIENT_ID,
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

def initialize_ui():
    # Initialize DPG
    dpg.create_context()
    
    # Create the window and UI components
    create_window()
    
    # Check initial authentication status
    tokens = load_tokens()
    if tokens and 'access_token' in tokens:
        # Validate token silently? Or just assume it's good initially.
        # For simplicity, just update UI if tokens exist
        config.IS_AUTHENTICATED = True # Assume true if tokens exist, validation happens on API call
        config.TWITCH_USER_ID = tokens.get('user_id') # Load user ID
        print(f"Loaded existing tokens for User ID: {config.TWITCH_USER_ID}")
        if dpg.does_item_exist(auth_status):
            dpg.set_value(auth_status, "Authenticated (Cached)")
            dpg.configure_item(auth_status, color=[0, 255, 0])
    
    # Set up the viewport
    dpg.create_viewport(title='Chattastic V3', width=800, height=600)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)

def run_ui():
    dpg.start_dearpygui()
    dpg.destroy_context()
    
    # Cleanup (optional, e.g., stop threads if necessary)
    print("Shutting down application...")
    # Add any cleanup needed for threads or resources
    from utils.auth import auth_server_thread, httpd_server
    if auth_server_thread is not None and auth_server_thread.is_alive():
        # Try to signal server shutdown if it's still running (unlikely after DPG loop ends)
        if httpd_server:
            httpd_server.server_close_request = True
            # Attempt to unblock if needed (see cancel_auth)
        auth_server_thread.join(timeout=1.0) # Wait briefly for thread