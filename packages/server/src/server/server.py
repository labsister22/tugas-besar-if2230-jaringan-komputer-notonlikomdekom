import socket
import threading
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import sys
import os
import random # Added for local_seq_num generation

# Ensure the tou package is findable
# This sys.path.append might be fragile. Consider packaging structure or environment variables.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'tou', 'src')))
from tou.Connection import Connection, ConnectionState # source 6 (modified)
from tou.Segments import Segments # source 8

class ChatServer:
    # Constants
    IDLE_TIMEOUT = 300  # seconds (increased for testing)
    SERVER_NAME = "SERVER"
    ADMIN_PASSWORD = "admin123"

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = False
        # users: Dict[addr_tuple, user_info_dict]
        self.users: Dict[Tuple[str, int], Dict] = {}
        self.messages: List[Dict] = []
        self.lock = threading.Lock() # To protect shared resources like self.users and self.messages

    def start(self):
        """Start the chat server"""
        self.socket.bind((self.host, self.port))
        self.socket.setblocking(False)
        self.running = True
        print(f"Server started on {self.host}:{self.port}")

        idle_checker = threading.Thread(target=self._check_idle_users)
        idle_checker.daemon = True
        idle_checker.start()

        try:
            while self.running:
                try:
                    data, addr = self.socket.recvfrom(Segments.MAX_HEADER_SIZE + Segments.MAX_PAYLOAD_SIZE)
                    self._handle_client_message(data, addr)
                except BlockingIOError:
                    time.sleep(0.01) # Short sleep to yield CPU
                    continue
                except Exception as e:
                    print(f"Main server loop error: {e}")
        finally:
            print("Server shutting down...")
            self.stop() # Ensure cleanup

    def stop(self):
        """Stop the chat server"""
        if not self.running:
            return
        self.running = False

        self.broadcast_message("Server is shutting down...")

        with self.lock:
            user_addrs = list(self.users.keys()) # Iterate over a copy of keys
            for addr in user_addrs:
                user_info = self.users.get(addr)
                if user_info and 'connection' in user_info:
                    try:
                        user_info['connection'].close()
                    except Exception as e:
                        print(f"Error closing connection for {addr}: {e}")
            self.users.clear()

        if self.socket:
            self.socket.close()
            self.socket = None
        print("Server stopped.")


    def _check_idle_users(self):
        """Background thread to check for idle users"""
        while self.running:
            current_time = time.time()
            to_remove_info = [] # List of (addr, name)

            with self.lock:
                # Iterate over a copy of items if modifying self.users within loop is risky,
                # but _remove_user re-acquires lock. For collecting, this is fine.
                for addr, user_info in self.users.items():
                    if user_info.get('name') == "pending_handshake": # Don't kick during handshake
                        if current_time - user_info.get('last_heartbeat', current_time) > 20: # Shorter timeout for pending
                           to_remove_info.append((addr, "pending_handshake_timeout"))
                        continue

                    if current_time - user_info.get('last_heartbeat', 0) > self.IDLE_TIMEOUT:
                        to_remove_info.append((addr, user_info.get('name', str(addr))))

            # Perform removals outside the users iteration lock if _remove_user is complex,
            # but _remove_user itself locks.
            for addr, name in to_remove_info:
                if name == "pending_handshake_timeout":
                    print(f"Timing out pending handshake for {addr}")
                    self._remove_user(addr) # Just remove, no broadcast
                else:
                    self.add_system_message(f"{name} was AFK and has been kicked from the chat!")
                    self._remove_user(addr)

            time.sleep(5) # Check every 5 seconds


    def _remove_user(self, addr: Tuple[str, int]):
        """Remove a user from the chat room. Assumes lock may be needed if called externally."""
        with self.lock: # Ensure thread-safe modification of self.users
            user_info = self.users.pop(addr, None)
            if user_info and 'connection' in user_info:
                print(f"Removing user {user_info.get('name', addr)}. Closing their connection.")
                try:
                    user_info['connection'].close()
                except Exception as e:
                    print(f"Error closing connection for removed user {addr}: {e}")
            elif user_info:
                print(f"Removed user {user_info.get('name', addr)} (no connection object found).")


    def _add_user(self, addr: Tuple[str, int], name: str, connection_obj: Connection):
        """
        Officially add a user after handshake or name change.
        Assumes 'connection_obj' is the established Connection object.
        """
        with self.lock:
            if name.upper() == self.SERVER_NAME:
                # Inform client name is reserved (not implemented here, client should handle this)
                return False

            # Check if name is already taken
            for user_addr, user_data in self.users.items():
                if user_addr != addr and user_data.get('name', '').lower() == name.lower():
                    # Inform client name is taken
                    return False

            self.users[addr] = {
                'name': name,
                'last_heartbeat': time.time(),
                'connection': connection_obj # Store the established connection
            }
            print(f"User '{name}' ({addr}) added/updated in users dict.")
            return True


    def _handle_client_message(self, data: bytes, addr: Tuple[str, int]):
        try:
            segment = Segments.unpack(data)
        except ValueError as e: # Segment unpacking error
            print(f"Segment unpack error from {addr}: {e}")
            return

        # Handle new connections (SYN from client)
        if segment.flags & Segments.SYN_flag:
            with self.lock: # Protect access to self.users for checking/adding
                if addr not in self.users or self.users[addr].get('name') == "pending_handshake_timeout":
                    print(f"Server: SYN received from new address {addr}")
                    conn = Connection(local_addr=(self.host, self.port), socket=self.socket)
                    conn.remote_addr = addr
                    conn.remote_seq_num = segment.seq_num
                    conn.local_seq_num = random.randint(0, Segments.seq_max)
                    conn.local_window = Segments.window_max # Initialize our window

                    syn_ack_segment = Segments(
                        source_port=conn.local_addr[1],
                        dest_port=conn.remote_addr[1],
                        seq_num=conn.local_seq_num,
                        ack_num=conn.remote_seq_num + 1,
                        flags=Segments.SYN_flag | Segments.ACK_flag,
                        window=conn.local_window
                    )
                    self.socket.sendto(syn_ack_segment.pack(), conn.remote_addr)
                    conn.state = ConnectionState.SYN_RECEIVED

                    self.users[addr] = {
                        'name': "pending_handshake",
                        'last_heartbeat': time.time(), # For timeout of pending handshake
                        'connection': conn
                    }
                    print(f"Server: Sent SYN-ACK to {addr}. Connection state: {conn.state}")

                elif self.users[addr]['connection'].state == ConnectionState.SYN_RECEIVED:
                    # Retransmitted SYN, client might have missed SYN-ACK. Resend.
                    print(f"Server: Retransmitted SYN received from {addr} in SYN_RECEIVED. Resending SYN-ACK.")
                    conn = self.users[addr]['connection']
                    syn_ack_segment = Segments(
                        source_port=conn.local_addr[1],
                        dest_port=conn.remote_addr[1],
                        seq_num=conn.local_seq_num, # Use existing seq_num
                        ack_num=conn.remote_seq_num + 1,
                        flags=Segments.SYN_flag | Segments.ACK_flag,
                        window=conn.local_window
                    )
                    self.socket.sendto(syn_ack_segment.pack(), conn.remote_addr)
            return # End of SYN processing

        # Process packets for existing connections or pending handshakes
        user_info = None
        conn = None
        with self.lock: # Get user_info and conn atomically
            user_info = self.users.get(addr)
            if user_info:
                conn = user_info.get('connection')

        if not user_info or not conn:
            print(f"Server: Packet from unknown or unconnected {addr} (not SYN). Discarding.")
            return

        # Handle ACK for our SYN-ACK (Completing the handshake)
        if conn.state == ConnectionState.SYN_RECEIVED:
            # ---- START DEBUG PRINT ----
            print(f"Server: Conn for {addr} in SYN_RECEIVED. Processing segment with Flags={segment.flags}, Seq={segment.seq_num}, Ack={segment.ack_num}. Expecting AckNum={ (conn.local_seq_num + 1) & Segments.ack_max } for my SYN (which was Seq={conn.local_seq_num}).")
            # ---- END DEBUG PRINT ----
            if (segment.flags == Segments.ACK_flag and
                segment.ack_num == (conn.local_seq_num + 1) & Segments.ack_max ):
                print(f"Server: ACK for SYN-ACK received from {addr} and validated. Establishing connection.")
                conn.state = ConnectionState.ESTABLISHED
                conn.remote_window = segment.window

                conn.start_background_threads(is_server_instance=True)

                with self.lock:
                    user_info['last_heartbeat'] = time.time()
                    # VVV UPDATE USER NAME TO PREVENT PENDING HANDSHAKE TIMEOUT VVV
                    default_user_name = f"User-{addr[1]}"
                    user_info['name'] = default_user_name

                # VVV Use the updated name in the system message VVV
                self.add_system_message(f"{default_user_name} ({addr[0]}:{addr[1]}) has connected.")
                print(f"Server: Connection ESTABLISHED with {addr}. State: {conn.state}")
            else:
                print(f"Server: For {addr} in SYN_RECEIVED, received packet was NOT the expected final ACK. Flags={segment.flags}, AckNum={segment.ack_num} vs Expected={(conn.local_seq_num + 1) & Segments.ack_max}")
            return

        # If connection is established, pass segment to connection object for processing
        if conn.state == ConnectionState.ESTABLISHED:
            # Update heartbeat before processing
            with self.lock:
                 user_info['last_heartbeat'] = time.time()

            # Let the Connection object handle the segment (data, ACKs for our data, FINs)
            conn.handle_received_segment(segment)

            # After handle_received_segment, check if there's application data to process
            # The Connection.receive() method pulls from its internal receive_buffer
            app_data = conn.receive()
            while app_data: # Process all data segments that might have been delivered
                try:
                    message_str = app_data.decode('utf-8')
                    #print(f"Server: Decoded app_data from {addr}: '{message_str}'")

                    if message_str.startswith('!heartbeat'): # Client sends this as app data now
                        # Already handled by updating last_heartbeat above
                        pass
                    elif message_str.startswith('!name '): # Example: Client sets name: !name <myname>
                        new_name = message_str.split(' ', 1)[1].strip()
                        if new_name:
                            old_name = user_info.get('name', str(addr))
                            if self._add_user(addr, new_name, conn): # _add_user updates self.users
                                self.add_system_message(f"{old_name} is now known as {new_name}.")
                            else: # Name taken or invalid
                                # Send error back to client (not implemented here)
                                print(f"Failed to change name for {addr} to {new_name}")
                    elif message_str.startswith('!'):
                        self._handle_command(message_str, addr)
                    else: # Regular chat message
                        self.add_message(user_info.get('name', str(addr)), message_str)

                except UnicodeDecodeError:
                    print(f"Server: Received non-UTF8 data from {user_info.get('name', addr)}. Discarding.")

                app_data = conn.receive() # Check for more data

        elif conn.state == ConnectionState.CLOSED or conn.state == ConnectionState.TIME_WAIT:
             print(f"Server: Received packet for already closed/time_wait connection from {addr}. Removing user.")
             self._remove_user(addr)


    def _handle_command(self, message: str, addr: Tuple[str, int]):
        """Handle special commands"""
        cmd_parts = message.split()
        command = cmd_parts[0].lower()
        user_name = "Unknown"
        with self.lock: # Get current name safely
            if addr in self.users:
                user_name = self.users[addr].get('name', str(addr))

        print(f"Server: Handling command '{command}' from {user_name} ({addr})")

        if command == '!disconnect':
            self.add_system_message(f"{user_name} has disconnected!")
            self._remove_user(addr) # This will also close the connection object

        elif command == '!kill' and len(cmd_parts) > 1:
            password_attempt = cmd_parts[1]
            if password_attempt == self.ADMIN_PASSWORD:
                self.add_system_message("Server shutdown initiated by admin.")
                # self.stop() # This can be abrupt. Signal main loop to stop.
                self.running = False # Signal main loop to terminate
            else:
                # Optionally send "invalid password" message back to admin client
                pass

        # Name change is now handled by !name in _handle_client_message for clarity
        # elif command == '!change' and len(cmd_parts) > 1:
        # ... (original logic, but better integrated with name setting)


    def add_message(self, name: str, message_content: str):
        """Add a message to the chat room and broadcast it."""
        timestamp = datetime.now().strftime("%I:%M %p")
        chat_message = {
            'name': name,
            'timestamp': timestamp,
            'message': message_content
        }
        with self.lock:
            self.messages.append(chat_message)
            # Limit message history if needed
            if len(self.messages) > 200: # Example limit
                self.messages = self.messages[-200:]

        # Broadcasting should be done outside the lock on self.messages if it involves network I/O
        self._broadcast_to_all_users(name, timestamp, message_content)


    def add_system_message(self, message_content: str):
        """Add a system message to the chat room."""
        print(f"SYSTEM MSG: {message_content}")
        self.add_message(self.SERVER_NAME, message_content)

    def broadcast_message(self, message_content: str): # Typically system originated
        """Broadcast a generic message to all connected users (usually from server itself)."""
        self.add_system_message(message_content)


    def _broadcast_to_all_users(self, name: str, timestamp: str, message_content: str):
        """Send a formatted chat message to all established users."""
        formatted_msg_str = f"{name} [{timestamp}]: {message_content}"
        msg_bytes = formatted_msg_str.encode('utf-8')

        with self.lock: # Iterate over a copy of users if modification can happen
            current_users = list(self.users.items())

        for addr, user_info in current_users:
            conn = user_info.get('connection')
            # Send only to established and active connections
            if conn and conn.state == ConnectionState.ESTABLISHED:
                try:
                    conn.send(msg_bytes) # Connection.send adds to its buffer, _send_loop sends
                except Exception as e:
                    print(f"Error broadcasting to {user_info.get('name', addr)}: {e}")
                    # Consider removing user if send fails persistently (e.g. connection broken)


    def get_recent_messages(self, count: int = 20) -> List[Dict]:
        """Get the most recent messages (for potential future use, e.g. new client join)."""
        with self.lock:
            return self.messages[-count:]

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Chat Room Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=12345, help='Port to bind to')
    parser.add_argument('--password', default='admin123', help='Admin password for !kill command')

    args = parser.parse_args()

    # Global assignment for server instance if needed by signal handlers (not used here)
    # global server_instance
    server_instance = ChatServer(args.host, args.port)
    server_instance.ADMIN_PASSWORD = args.password

    try:
        server_instance.start()
    except KeyboardInterrupt:
        print("Keyboard interrupt received, stopping server...")
    finally:
        if 'server_instance' in locals() and server_instance.running:
             server_instance.stop()

if __name__ == "__main__":
    main()