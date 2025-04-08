# globals.py
# Used for sharing instances like the WebSocket manager across modules

# Placeholder for the ConnectionManager instance from app.py
# app.py will set this instance on startup.
manager = None

# Global dictionary to store Kick emote mappings { "emoteName": "path/to/emote.jpg", ... }
# This will be populated by api/kick.py when connecting
kick_emotes = {}
