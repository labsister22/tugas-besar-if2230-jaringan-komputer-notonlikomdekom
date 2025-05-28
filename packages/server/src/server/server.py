import socket
import threading
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'tou', 'src')))
from tou.Connection import Connection
from tou.Segments import Segments

class ChatServer:
    # Constants
    IDLE_TIMEOUT = 30  # seconds
    SERVER_NAME = "SERVER"
    ADMIN_PASSWORD = "admin123"  # You can change this or make it configurable

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = False
        self.users: Dict[str, Dict] = {}  # ip:port -> {name, last_heartbeat, connection}
        self.messages: List[Dict] = []  # List of {name, timestamp, message}
        self.lock = threading.Lock()

    def start(self):
        """Start the chat server"""
        self.socket.bind((self.host, self.port))
        self.socket.setblocking(False)  # Non-blocking mode
        self.running = True
        print(f"Server started on {self.host}:{self.port}")

        # Start idle user checker thread
        idle_checker = threading.Thread(target=self._check_idle_users)
        idle_checker.daemon = True
        idle_checker.start()

        last_check = time.time()
        TIMEOUT = 5  # seconds

        try:
            while self.running:
                now = time.time()
                try:
                    data, addr = self.socket.recvfrom(128)
                    self._handle_client_message(data, addr)
                    last_check = now  # Reset last_check on activity
                except BlockingIOError:
                    # No data available
                    time.sleep(0.05)
                except Exception as e:
                    if isinstance(e, BlockingIOError):
                        # Non-blocking socket: no data available, ignore
                        time.sleep(0.05)
                        continue
                    print(f"Error handling client: {e}")
                # Manual timeout logic (if needed for other periodic tasks)
                if now - last_check > TIMEOUT:
                    # You can add any periodic timeout logic here
                    last_check = now
        finally:
            self.socket.close()

    def stop(self):
        """Stop the chat server"""
        self.running = False
        # Notify all users that server is shutting down
        self.broadcast_message("Server is shutting down...")
        # Close all connections
        with self.lock:
            for user_info in self.users.values():
                if 'connection' in user_info:
                    user_info['connection'].close()
            self.users.clear()

    def _check_idle_users(self):
        """Background thread to check for idle users"""
        while self.running:
            current_time = time.time()
            to_remove = []

            with self.lock:
                for addr, user_info in self.users.items():
                    if current_time - user_info['last_heartbeat'] > self.IDLE_TIMEOUT:
                        to_remove.append((addr, user_info['name']))

                for addr, name in to_remove:
                    self._remove_user(addr)
                    self.add_system_message(f"{name} was AFK and has been kicked from the chat!")

            time.sleep(1)

    def _remove_user(self, addr: Tuple[str, int]):
        """Remove a user from the chat room"""
        with self.lock:
            if addr in self.users:
                user_info = self.users[addr]
                if 'connection' in user_info:
                    user_info['connection'].close()
                del self.users[addr]

    def _add_user(self, addr: Tuple[str, int], name: str, connection: Connection):
        """Add a new user to the chat room"""
        with self.lock:
            if name.upper() == self.SERVER_NAME:
                return False
            
            # Check if name is already taken
            for user in self.users.values():
                if user['name'].lower() == name.lower():
                    return False

            self.users[addr] = {
                'name': name,
                'last_heartbeat': time.time(),
                'connection': connection
            }
            return True

    def _handle_client_message(self, data: bytes, addr: Tuple[str, int]):
        """Handle incoming client messages"""
        try:
            segment = Segments.unpack(data)
            
            # Handle new connections
            if segment.flags & Segments.SYN_flag:
                conn = Connection((self.host, self.port), self.socket)
                conn.listen()  # Ensure the connection is in LISTEN state
                conn.remote_addr = addr
                conn.accept()
                return

            # Parse message
            message = segment.payload.decode('utf-8')
            
            # Handle heartbeat
            if message.startswith('!heartbeat'):
                if addr in self.users:
                    self.users[addr]['last_heartbeat'] = time.time()
                return

            # Handle commands
            if message.startswith('!'):
                self._handle_command(message, addr)
                return

            # Regular message
            if addr in self.users:
                user_info = self.users[addr]
                self.add_message(user_info['name'], message)
                user_info['last_heartbeat'] = time.time()

        except Exception as e:
            print(f"Error processing message from {addr}: {e}")

    def _handle_command(self, message: str, addr: Tuple[str, int]):
        """Handle special commands"""
        cmd_parts = message.split()
        command = cmd_parts[0].lower()

        if command == '!disconnect':
            if addr in self.users:
                name = self.users[addr]['name']
                self._remove_user(addr)
                self.add_system_message(f"{name} has disconnected!")

        elif command == '!kill' and len(cmd_parts) > 1:
            if cmd_parts[1] == self.ADMIN_PASSWORD:
                self.add_system_message("Server shutdown initiated by admin")
                self.stop()

        elif command == '!change' and len(cmd_parts) > 1:
            new_name = cmd_parts[1]
            if addr in self.users and new_name.upper() != self.SERVER_NAME:
                old_name = self.users[addr]['name']
                # Check if new name is available
                name_available = True
                for user in self.users.values():
                    if user['name'].lower() == new_name.lower():
                        name_available = False
                        break
                
                if name_available:
                    self.users[addr]['name'] = new_name
                    self.add_system_message(f"{old_name} changed their name to {new_name}")

    def add_message(self, name: str, message: str):
        """Add a message to the chat room"""
        timestamp = datetime.now().strftime("%I:%M %p")
        with self.lock:
            self.messages.append({
                'name': name,
                'timestamp': timestamp,
                'message': message
            })
            self._broadcast_to_all_users(name, timestamp, message)

    def add_system_message(self, message: str):
        """Add a system message to the chat room"""
        self.add_message(self.SERVER_NAME, message)

    def broadcast_message(self, message: str):
        """Broadcast a message to all connected users"""
        self.add_system_message(message)

    def _broadcast_to_all_users(self, name: str, timestamp: str, message: str):
        """Send a message to all connected users"""
        formatted_msg = f"{name} [{timestamp}]: {message}"
        with self.lock:
            for user_info in self.users.values():
                if 'connection' in user_info:
                    try:
                        user_info['connection'].send(formatted_msg.encode('utf-8'))
                    except:
                        pass  # Connection might be closed or in error state

    def get_recent_messages(self, count: int = 20) -> List[Dict]:
        """Get the most recent messages"""
        with self.lock:
            return self.messages[-count:]

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Chat Room Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=12345, help='Port to bind to')
    parser.add_argument('--password', default='admin123', help='Admin password for !kill command')
    
    args = parser.parse_args()
    server = ChatServer(args.host, args.port)
    server.ADMIN_PASSWORD = args.password
    
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()