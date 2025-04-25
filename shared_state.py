# shared_state.py
"""
This module provides a shared state mechanism for the SFTP and terminal servers.
It uses a simple file-based approach to share authentication data between processes.
"""

import json
import os
import time
import threading
from pathlib import Path

# Define the path for the shared state file
STATE_DIR = Path("./state")
STATE_FILE = STATE_DIR / "client_db.json"

# Create state directory if it doesn't exist
if not STATE_DIR.exists():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

# Initialize the state file if it doesn't exist
if not STATE_FILE.exists():
    with open(STATE_FILE, "w") as f:
        f.write("{}")

# Lock for thread safety when accessing the state file
state_lock = threading.Lock()

def save_client(key, host_ip, port, username, password):
    """
    Save client credentials to the shared state.
    """
    with state_lock:
        try:
            # Read existing state
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            
            # Add/update client entry
            state[key] = {
                "host_ip": host_ip,
                "port": port,
                "username": username,
                "password": password,
                "timestamp": time.time()
            }
            
            # Write updated state
            with open(STATE_FILE, "w") as f:
                json.dump(state, f)
                
            return True
        except Exception as e:
            print(f"Error saving client state: {str(e)}")
            return False

def get_client(key):
    """
    Get client credentials from the shared state.
    """
    with state_lock:
        try:
            # Read state
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            
            # Return client info if it exists
            if key in state:
                return state[key]
            return None
        except Exception as e:
            print(f"Error getting client state: {str(e)}")
            return None

def remove_client(key):
    """
    Remove a client from the shared state.
    """
    with state_lock:
        try:
            # Read state
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            
            # Remove client if it exists
            if key in state:
                del state[key]
                
                # Write updated state
                with open(STATE_FILE, "w") as f:
                    json.dump(state, f)
                return True
            return False
        except Exception as e:
            print(f"Error removing client state: {str(e)}")
            return False

def clear_expired_clients(max_age_seconds=3600):
    """
    Clear clients that haven't been active for a while.
    """
    with state_lock:
        try:
            current_time = time.time()
            # Read state
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            
            # Identify expired clients
            expired_keys = []
            for key, client_info in state.items():
                if current_time - client_info.get("timestamp", 0) > max_age_seconds:
                    expired_keys.append(key)
            
            # Remove expired clients
            for key in expired_keys:
                del state[key]
            
            # Write updated state
            with open(STATE_FILE, "w") as f:
                json.dump(state, f)
                
            return len(expired_keys)
        except Exception as e:
            print(f"Error clearing expired clients: {str(e)}")
            return 0

def has_client(key):
    """
    Check if a client exists in the shared state.
    """
    with state_lock:
        try:
            # Read state
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            
            return key in state
        except Exception as e:
            print(f"Error checking client existence: {str(e)}")
            return False

# Run a background thread to periodically clean up expired clients
def cleanup_thread():
    while True:
        clear_expired_clients()
        time.sleep(300)  # Clean up every 5 minutes

# Start the cleanup thread
cleanup_thread = threading.Thread(target=cleanup_thread, daemon=True)
cleanup_thread.start()