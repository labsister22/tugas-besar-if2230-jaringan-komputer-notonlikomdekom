import curses
import socket
import threading
import time
from datetime import datetime
from typing import List, Optional
from tou.Connection import Connection
from tou.Segments import Segments

class ChatClient:
    def __init__(self, host: str, port: int, display_name: str):
        self.host = host
        self.port = port
        self.display_name = display_name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', 0))  # Bind to random available port
        self.connection: Optional[Connection] = None
        self.running = False
        self.messages: List[str] = []
        self.lock = threading.Lock()
        self.input_buffer = ""
        self.last_heartbeat = time.time()

    def _setup_curses(self):
        """Initialize curses windows"""
        self.screen = curses.initscr()
        curses.noecho()  # Don't echo keystrokes
        curses.cbreak()  # React to keys instantly
        self.screen.keypad(True)  # Enable keypad mode
        curses.start_color()

        # Initialize color pairs
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)  # For online users
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # For system messages
        curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)  # For regular messages

        # Get screen dimensions
        self.max_y, self.max_x = self.screen.getmaxyx()

        # Create windows
        self.chat_win = curses.newwin(self.max_y - 3, self.max_x, 0, 0)
        self.input_win = curses.newwin(3, self.max_x, self.max_y - 3, 0)

        # Enable scrolling for chat window
        self.chat_win.scrollok(True)

        # Draw borders
        self.chat_win.box()
        self.input_win.box()

        # Initial refresh
        self.chat_win.refresh()
        self.input_win.refresh()

    def _cleanup_curses(self):
        """Clean up curses settings"""
        curses.nocbreak()
        self.screen.keypad(False)
        curses.echo()
        curses.endwin()

    def _draw_header(self):
        """Draw the chat room header"""
        server_info = f"Connected to {self.host}:{self.port}'s chat room"
        online_users = "(3 online users)"  # This should be dynamic based on actual users
        header = f"{server_info} {online_users}"
        separator = "-" * self.max_x

        self.chat_win.addstr(0, 0, header, curses.color_pair(1))
        self.chat_win.addstr(1, 0, separator)
        self.chat_win.refresh()

    def _handle_user_input(self):
        """Handle user input in a separate thread"""
        while self.running:
            try:
                key = self.input_win.getch()

                if key == ord('\n'):  # Enter key
                    if self.input_buffer:
                        # Handle commands
                        if self.input_buffer.startswith('!'):
                            self._handle_command(self.input_buffer)
                        else:
                            # Send regular message
                            self._send_message(self.input_buffer)

                        # Clear input buffer
                        self.input_buffer = ""
                        self.input_win.clear()
                        self.input_win.box()
                        self.input_win.refresh()

                elif key == curses.KEY_BACKSPACE or key == 127:  # Backspace
                    if self.input_buffer:
                        self.input_buffer = self.input_buffer[:-1]
                        self.input_win.clear()
                        self.input_win.box()
                        self.input_win.addstr(1, 1, self.input_buffer)
                        self.input_win.refresh()

                elif key != -1 and 32 <= key <= 126:  # Printable characters
                    if len(self.input_buffer) < self.max_x - 4:  # Leave space for borders
                        self.input_buffer += chr(key)
                        self.input_win.addstr(1, 1, self.input_buffer)
                        self.input_win.refresh()

            except Exception as e:
                self._add_message(f"Input error: {e}", is_system=True)

    def _add_message(self, message: str, is_system: bool = False):
        """Add a message to the chat window"""
        with self.lock:
            try:
                # Calculate available space
                max_lines = self.max_y - 5  # Account for borders and input area

                # Add timestamp if not a system message
                if not is_system:
                    timestamp = datetime.now().strftime("%I:%M %p")
                    message = f"[{timestamp}] {message}"

                # Split long messages
                lines = []
                while len(message) > self.max_x - 4:
                    lines.append(message[:self.max_x - 4])
                    message = message[self.max_x - 4:]
                lines.append(message)

                # Add lines to messages list
                self.messages.extend(lines)

                # Keep only last max_lines messages
                if len(self.messages) > max_lines:
                    self.messages = self.messages[-max_lines:]

                # Redraw chat window
                self.chat_win.clear()
                self.chat_win.box()
                self._draw_header()

                line_num = 2  # Start after header
                for msg in self.messages:
                    color = curses.color_pair(2 if is_system else 3)
                    self.chat_win.addstr(line_num, 1, msg, color)
                    line_num += 1

                self.chat_win.refresh()

            except Exception as e:
                # If there's an error, try to show it
                try:
                    self.chat_win.addstr(2, 1, f"Display error: {e}", curses.color_pair(2))
                    self.chat_win.refresh()
                except:
                    pass

    def _send_message(self, message: str):
        """Send a message to the server"""
        if self.connection and self.connection.state == Connection.ConnectionState.ESTABLISHED:
            try:
                formatted_msg = f"{self.display_name}: {message}"
                self.connection.send(formatted_msg.encode('utf-8'))
            except Exception as e:
                self._add_message(f"Error sending message: {e}", is_system=True)

    def _send_heartbeat(self):
        """Send periodic heartbeat to server"""
        while self.running:
            try:
                if self.connection and time.time() - self.last_heartbeat >= 1.0:
                    self.connection.send(b"!heartbeat")
                    self.last_heartbeat = time.time()
            except Exception as e:
                self._add_message(f"Heartbeat error: {e}", is_system=True)
            time.sleep(0.1)

    def _handle_command(self, command: str):
        """Handle special commands"""
        if command == "!disconnect":
            self.stop()
        elif command.startswith("!change "):
            new_name = command[8:].strip()
            if new_name:
                self.display_name = new_name
                self._send_message(f"!change {new_name}")
        elif command.startswith("!kill "):
            password = command[6:].strip()
            self._send_message(f"!kill {password}")

    def start(self):
        """Start the chat client"""
        try:
            # Setup curses
            # self._setup_curses()

            # Initialize connection
            self.connection = Connection(self.sock.getsockname(), self.sock)
            server_addr = (self.host, self.port)
            self.connection.connect(server_addr)

            # Start client
            self.running = True

            # Start background threads
            input_thread = threading.Thread(target=self._handle_user_input)
            heartbeat_thread = threading.Thread(target=self._send_heartbeat)
            input_thread.daemon = True
            heartbeat_thread.daemon = True
            input_thread.start()
            heartbeat_thread.start()

            # Show welcome message
            self._add_message(f"Connected to chat room as {self.display_name}", is_system=True)

            # Main receive loop
            while self.running:
                try:
                    if self.connection:
                        data = self.connection.receive()
                        if data:
                            message = data.decode('utf-8')
                            self._add_message(message)
                except Exception as e:
                    self._add_message(f"Connection error: {e}", is_system=True)
                    break
        except Exception as e:
            if self.running:
                self._add_message(f"Fatal error: {e}", is_system=True)
        finally:
            self.stop()

    def stop(self):
        """Stop the chat client"""
        self.running = False
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
        self._cleanup_curses()

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Chat Room Client')
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=12345, help='Server port')
    parser.add_argument('--name', default='Anonymous', help='Display name')

    args = parser.parse_args()

    client = ChatClient(args.host, args.port, args.name)
    try:
        client.start()
    except KeyboardInterrupt:
        client.stop()