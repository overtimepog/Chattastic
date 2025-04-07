import os
import random
import json
import traceback
import logging
from threading import Thread
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import webbrowser

import config

# Create Flask app
app = Flask(__name__)
socketio = SocketIO(app)
viewer_messages = {}

def update_viewer_message(viewer_name, message):
    global viewer_messages
    viewer_messages[viewer_name] = message

def open_viewer_page():
    webbrowser.open(f'http://localhost:5000/viewer', new=2)

@app.route('/')
def home():
    return 'Welcome to the Flask server!'

@app.route('/viewer')
def show_viewer():
    try:
        viewer_content = ""
        for viewer_name in config.selected_viewers:
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

        print("Finished processing viewers. Total viewers: " + str(len(config.selected_viewers)))

        # Ensure selected_viewers is properly formatted for JavaScript
        js_selected_viewers = json.dumps(config.selected_viewers)

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
        if viewer_name in config.selected_viewers:
            viewer_message = viewer_messages.get(viewer_name, "No new messages")
            print(f"Fetching message for viewer: {viewer_name}")
            return jsonify({"message": viewer_message})
        else:
            return jsonify({"message": "Viewer not found"}), 404
    except Exception as e:
        print("Error in get_viewer_message for " + viewer_name + ": " + str(e))
        traceback.print_exc() # Print full traceback
        return jsonify({"error": "Internal Server Error"}), 500

@socketio.on('connect')
def handle_connect():
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

def run_flask_app():
    # Disable Flask's default development server logging for cleaner output
    # Use Waitress or another production-grade server for deployment
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False, log_output=False)

# Start the Flask app in a separate thread
flask_thread = Thread(target=run_flask_app, daemon=True)
flask_thread.start()