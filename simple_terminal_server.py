# simple_terminal_server.py
# A standalone terminal server that will run on port 8888

import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.gen
import paramiko
import os
import sys
import logging
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger('terminal_server')

# Define port - hardcoded to 8888 for compatibility
SERVER_PORT = 8888

# Define static directory
current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "static")

class TerminalWebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        # Allow all origins for testing
        return True
        
    def open(self):
        logger.info("New WebSocket connection opened")
        self.host = self.get_query_argument("host", None)
        self.port = int(self.get_query_argument("port", "22"))
        self.username = self.get_query_argument("username", None)
        self.password = self.get_query_argument("password", None)
        
        # Terminal dimensions - default to a wider terminal
        self.term_cols = 100
        self.term_rows = 24
        
        # Check if we have all required parameters
        if not all([self.host, self.username, self.password]):
            error_msg = "Missing connection parameters. Need host, username, and password."
            logger.error(error_msg)
            self.write_message(f"ERROR: {error_msg}")
            self.close()
            return
            
        logger.info(f"Attempting SSH connection to {self.host}:{self.port} as {self.username}")
        
        try:
            # Create SSH client
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password
            )
            
            # Open a channel for shell with proper terminal type and size
            self.channel = self.ssh.invoke_shell(
                term="xterm-256color",
                width=self.term_cols,
                height=self.term_rows
            )
            self.channel.settimeout(0.0)
            self.alive = True
            
            logger.info(f"SSH connection established successfully with terminal size {self.term_cols}x{self.term_rows}")
            self.write_message("Connected to SSH server")
            
            # Start reading from SSH
            tornado.ioloop.IOLoop.current().spawn_callback(self._read_from_ssh)
        except Exception as e:
            error_msg = f"Failed to connect: {str(e)}"
            logger.error(error_msg)
            self.write_message(f"ERROR: {error_msg}")
            self.close()

    async def _read_from_ssh(self):
        while self.alive:
            try:
                if self.channel.recv_ready():
                    data = self.channel.recv(4096)  # Larger buffer for better performance
                    if not data:
                        logger.info("SSH channel closed")
                        break
                    self.write_message(data, binary=True)
                await tornado.gen.sleep(0.01)
            except Exception as e:
                logger.error(f"Error reading from SSH: {str(e)}")
                break
        self.close()

    def on_message(self, message):
        if not hasattr(self, "channel") or not self.alive:
            return
            
        try:
            # Check if this is a resize message (JSON format)
            if message.startswith('{') and message.endswith('}'):
                try:
                    msg_obj = json.loads(message)
                    
                    # Handle resize event
                    if msg_obj.get('type') == 'resize':
                        cols = int(msg_obj.get('cols', 100))
                        rows = int(msg_obj.get('rows', 24))
                        
                        # Validate dimensions
                        if 10 <= cols <= 500 and 5 <= rows <= 200:
                            logger.info(f"Resizing terminal to {cols}x{rows}")
                            self.term_cols = cols
                            self.term_rows = rows
                            self.channel.resize_pty(width=cols, height=rows)
                        return
                except Exception as e:
                    logger.error(f"Error processing resize: {str(e)}")
                    # Continue processing as normal message
            
            # Check for VT100 resize sequence: ESC[8;rows;colst
            if isinstance(message, str) and message.startswith('\x1b[8;') and 't' in message:
                try:
                    # Parse resize sequence
                    parts = message[4:].split(';')
                    if len(parts) >= 2:
                        rows = int(parts[0])
                        cols = int(parts[1].split('t')[0])
                        
                        # Validate dimensions
                        if 10 <= cols <= 500 and 5 <= rows <= 200:
                            logger.info(f"Resizing terminal via VT100 sequence to {cols}x{rows}")
                            self.term_cols = cols
                            self.term_rows = rows
                            self.channel.resize_pty(width=cols, height=rows)
                        return
                except Exception as e:
                    logger.error(f"Error processing resize sequence: {str(e)}")
                    # Continue processing as normal message
            
            # Normal message - forward to SSH
            if isinstance(message, str):
                message = message.encode("utf-8")
            self.channel.send(message)
            
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            self.write_message(f"ERROR: {str(e)}")
            self.close()

    def on_close(self):
        logger.info("WebSocket connection closed")
        self.alive = False
        try:
            if hasattr(self, "channel"):
                self.channel.close()
            if hasattr(self, "ssh"):
                self.ssh.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        # Just return a simple status page
        self.write("""
        <html>
        <head>
            <title>Terminal Server Status</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 2rem; }
                .status { padding: 1rem; background-color: #dff0d8; border: 1px solid #d6e9c6; border-radius: 4px; }
                code { background-color: #f8f8f8; padding: 0.2rem 0.4rem; border-radius: 3px; }
            </style>
        </head>
        <body>
            <h1>Terminal Server Status</h1>
            <div class="status">
                <p><strong>Status:</strong> Running</p>
                <p><strong>Port:</strong> 8888</p>
                <p>The terminal server is running and ready to accept WebSocket connections at <code>ws://localhost:8888/terminal</code></p>
                <p>To connect to the terminal, use the main SFTP interface at <a href="http://localhost:8000">http://localhost:8000</a></p>
            </div>
        </body>
        </html>
        """)

def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/terminal", TerminalWebSocketHandler),
        (r"/(.*)", tornado.web.StaticFileHandler, {
            "path": static_dir,
            "default_filename": "index.html"
        })
    ])

def check_port_available(port):
    """Check if the port is available for use"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = True
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        result = False
    finally:
        sock.close()
    return result

if __name__ == "__main__":
    print(f"Starting Terminal Server on port {SERVER_PORT}...")
    
    # Check if port is available
    if not check_port_available(SERVER_PORT):
        print(f"ERROR: Port {SERVER_PORT} is already in use!")
        print("Please make sure no other process is using this port and try again.")
        sys.exit(1)
    
    try:
        app = make_app()
        app.listen(SERVER_PORT)
        print(f"Terminal Server is running at http://localhost:{SERVER_PORT}")
        print("Press Ctrl+C to stop the server")
        
        # Start the Tornado IO loop
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        tornado.ioloop.IOLoop.current().stop()
        print("Server stopped.")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
