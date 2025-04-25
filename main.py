#!/usr/bin/env python
# run_servers.py - A robust launcher for both SFTP and terminal servers

import os
import sys
import socket
import subprocess
import time
import signal
import atexit

print("=== Local SFTP and Terminal Server Launcher ===")

# Make sure required directories exist
for directory in ['./dtmp/', './utmp/', './share/', './static/']:
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"Created directory: {directory}")

# Check if a port is in use
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

# Kill a process listening on a specific port (Unix/Linux/macOS)
def kill_process_on_port(port):
    if sys.platform.startswith('win'):
        # Windows
        try:
            cmd = f"FOR /F \"tokens=5\" %P IN ('netstat -ano ^| findstr :{port}') DO TaskKill /PID %P /F"
            subprocess.run(cmd, shell=True)
            print(f"Attempted to kill process on port {port}")
            time.sleep(1)  # Give it time to die
        except Exception as e:
            print(f"Failed to kill process on port {port}: {e}")
    else:
        # Unix/Linux/macOS
        try:
            pid_cmd = f"lsof -ti:{port}"
            pid = subprocess.check_output(pid_cmd, shell=True).decode().strip()
            if pid:
                kill_cmd = f"kill -9 {pid}"
                subprocess.run(kill_cmd, shell=True)
                print(f"Killed process {pid} on port {port}")
                time.sleep(1)  # Give it time to die
        except Exception as e:
            print(f"Failed to kill process on port {port}: {e}")

# Terminal Server port
TERMINAL_PORT = 8888

# SFTP Server port
SFTP_PORT = 8000

# Check if ports are available
if is_port_in_use(TERMINAL_PORT):
    print(f"WARNING: Port {TERMINAL_PORT} is already in use!")
    choice = input(f"Do you want to try to kill the process on port {TERMINAL_PORT}? (y/n): ")
    if choice.lower() == 'y':
        kill_process_on_port(TERMINAL_PORT)
        if is_port_in_use(TERMINAL_PORT):
            print(f"ERROR: Failed to free up port {TERMINAL_PORT}.")
            sys.exit(1)
        else:
            print(f"Port {TERMINAL_PORT} is now available.")
    else:
        print(f"Please free up port {TERMINAL_PORT} and try again.")
        sys.exit(1)

if is_port_in_use(SFTP_PORT):
    print(f"WARNING: Port {SFTP_PORT} is already in use!")
    choice = input(f"Do you want to try to kill the process on port {SFTP_PORT}? (y/n): ")
    if choice.lower() == 'y':
        kill_process_on_port(SFTP_PORT)
        if is_port_in_use(SFTP_PORT):
            print(f"ERROR: Failed to free up port {SFTP_PORT}.")
            sys.exit(1)
        else:
            print(f"Port {SFTP_PORT} is now available.")
    else:
        print(f"Please free up port {SFTP_PORT} and try again.")
        sys.exit(1)

# Launch the servers as separate processes
terminal_server_cmd = ["python", "simple_terminal_server.py"]
sftp_server_cmd = ["python", "-m", "uvicorn", "local_sftp:app", "--host", "0.0.0.0", "--port", str(SFTP_PORT)]

try:
    # Start the terminal server
    print(f"Starting terminal server on port {TERMINAL_PORT}...")
    terminal_proc = subprocess.Popen(terminal_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait a moment to see if it starts
    time.sleep(1)
    if terminal_proc.poll() is not None:
        # Process has terminated
        stdout, stderr = terminal_proc.communicate()
        print("ERROR: Terminal server failed to start!")
        print("Stdout:", stdout.decode())
        print("Stderr:", stderr.decode())
        sys.exit(1)
    
    # Start the SFTP server
    print(f"Starting SFTP server on port {SFTP_PORT}...")
    sftp_proc = subprocess.Popen(sftp_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait a moment to see if it starts
    time.sleep(1)
    if sftp_proc.poll() is not None:
        # Process has terminated
        stdout, stderr = sftp_proc.communicate()
        print("ERROR: SFTP server failed to start!")
        print("Stdout:", stdout.decode())
        print("Stderr:", stderr.decode())
        # Kill terminal server if SFTP server fails
        terminal_proc.terminate()
        sys.exit(1)
    
    print("\n=== Servers Started Successfully ===")
    print(f"SFTP server is running at http://localhost:{SFTP_PORT}")
    print(f"Terminal server is running at http://localhost:{TERMINAL_PORT}")
    print("\nPress Ctrl+C to stop the servers...")
    
    # Function to kill processes on exit
    def cleanup():
        print("\nShutting down servers...")
        terminal_proc.terminate()
        sftp_proc.terminate()
        print("Servers stopped.")
    
    # Register cleanup function
    atexit.register(cleanup)
    
    # Keep the script running
    while True:
        # Check if processes are still running
        if terminal_proc.poll() is not None:
            print("WARNING: Terminal server has stopped unexpectedly. Restarting...")
            terminal_proc = subprocess.Popen(terminal_server_cmd)
        
        if sftp_proc.poll() is not None:
            print("WARNING: SFTP server has stopped unexpectedly. Restarting...")
            sftp_proc = subprocess.Popen(sftp_server_cmd)
        
        time.sleep(2)  # Check every 2 seconds
        
except KeyboardInterrupt:
    print("\nShutting down servers...")
    try:
        terminal_proc.terminate()
        sftp_proc.terminate()
    except:
        pass
    print("Servers stopped.")
    sys.exit(0)