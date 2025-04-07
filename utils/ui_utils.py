import time
import json
import logging
import requests
import dearpygui.dearpygui as dpg
import random

import config
from utils.auth import load_tokens

def clear_error_message_after_delay(seconds=5):
     """Clears the error message display after a delay."""
     def clear():
         time.sleep(seconds)
         if dpg.does_item_exist("error_display"):
             dpg.set_value("error_display", "")
     # Run clearing in a separate thread to avoid blocking
     from threading import Thread
     Thread(target=clear, daemon=True).start()