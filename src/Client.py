import curses
import textwrap
import threading
import json
import time
from datetime import datetime
import os
import sys # Added for stderr
import collections # Added for deque
import queue # Added for message queue between threads

from tou.Connection import BetterUDPSocket

DEST_PORT = 34112 # Default server port

class ChatClientCurses:
    def __init__(self, name, server_ip_str, resolved_server_ip, client_port, dest_port=DEST_PORT):
        self.CLIENT_NAME = name
        self.SERVER_ADDR_STR = server_ip_str # For display
        self.SERVER_ADDR = (resolved_server_ip, dest_port)
        self.SRC_PORT = client_port
        self.sock = BetterUDPSocket()
        self.running = True
        self.KILLED_BY_SERVER = False # Flag to check if server initiated termination

        self.messages = collections.deque(maxlen=200)  # Store (message_text, color_pair_id, sender, timestamp)
        self.message_queue = queue.Queue() # For thread-safe message passing to curses
        self.input_buffer = ""
        self.placeholder = "Type your message or !help"



        try:
            self.sock.bind(("0.0.0.0", self.SRC_PORT))
            self.sock.connect(self.SERVER_ADDR, self.SRC_PORT, dest_port)
            self.message_queue.put(("system_info", f"Handshake successful. Connected as '{self.CLIENT_NAME}'."))
        except Exception as e:
            # This message will print to stderr before curses starts
            print(f"Critical Connection Error: {e}\nExiting.", file=sys.stderr)
            self.running = False # Prevent main_loop from starting
            return

        # Start background threads
        self.listen_thread = threading.Thread(target=self.listen_for_messages, daemon=True)
        self.listen_thread.start()
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_sender, daemon=True)
        self.heartbeat_thread.start()

    def run(self):
        if not self.running: # If __init__ failed (e.g., connection error)
            return
        try:
            curses.wrapper(self._main_loop)
        except curses.error as e:
            print(f"Curses error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Unhandled error in main loop: {e}", file=sys.stderr)
        finally:
            # Ensure cleanup, even if wrapper fails or threads are stuck
            self.running = False # Signal threads to stop
            if hasattr(self, 'sock') and self.sock:
                self.sock.close()
            if hasattr(self, 'listen_thread') and self.listen_thread.is_alive():
                # Threads are daemonic, will exit with main, but try to join
                # self.listen_thread.join(timeout=0.5) # Potentially blocking
                pass
            if hasattr(self, 'heartbeat_thread') and self.heartbeat_thread.is_alive():
                # self.heartbeat_thread.join(timeout=0.5)
                pass
            print("Client shut down.", file=sys.stderr)


    def _setup_windows(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)  # Hide cursor generally
        stdscr.nodelay(True) # Make getch non-blocking for stdscr

        # Colors
        curses.start_color()
        if curses.has_colors():
            curses.use_default_colors() # Allow use of default terminal bg
            # Color pairs: (id, foreground, background (-1 for default))
            curses.init_pair(1, curses.COLOR_CYAN, -1)    # Self messages
            curses.init_pair(2, curses.COLOR_GREEN, -1)   # Other messages
            curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Server/System messages
            curses.init_pair(4, curses.COLOR_WHITE, -1)   # Input text
            curses.init_pair(5, curses.A_DIM if hasattr(curses, 'A_DIM') else curses.COLOR_WHITE, -1) # Placeholder (dim white or white)
            curses.init_pair(6, curses.COLOR_RED, -1)     # Error messages
            curses.init_pair(7, curses.COLOR_MAGENTA, -1) # Timestamp/Name prefix
            curses.init_pair(10, curses.COLOR_BLUE, -1)   # Window Borders/Titles
        else: # Basic fallback for no color support
            curses.init_pair(1, curses.A_BOLD, -1)
            curses.init_pair(2, curses.A_NORMAL, -1)
            curses.init_pair(3, curses.A_BOLD, -1)
            curses.init_pair(4, curses.A_NORMAL, -1)
            curses.init_pair(5, curses.A_DIM if hasattr(curses, 'A_DIM') else curses.A_NORMAL, -1)
            curses.init_pair(6, curses.A_BOLD, -1)
            curses.init_pair(7, curses.A_UNDERLINE if hasattr(curses, 'A_UNDERLINE') else curses.A_NORMAL, -1)
            curses.init_pair(10, curses.A_BOLD, -1)


        # Layout dimensions
        self.term_height, self.term_width = stdscr.getmaxyx()

        status_bar_height = 1
        input_area_height = 3 # Border + 1 line text + border
        output_area_height = self.term_height - input_area_height - status_bar_height

        # Status Bar (bottom)
        self.status_bar_win = stdscr.derwin(status_bar_height, self.term_width, self.term_height - status_bar_height, 0)

        # Input Area (above status bar)
        # Border window for input
        self.input_border_win = stdscr.derwin(input_area_height, self.term_width, self.term_height - status_bar_height - input_area_height, 0)
        # Actual input window (inside border)
        self.input_win = self.input_border_win.derwin(input_area_height - 2, self.term_width - 2, 1, 1)
        self.input_win.keypad(True)    # Enable special keys (arrow, backspace)
        self.input_win.nodelay(True)   # Non-blocking getch for input window

        # Output Area (top)
        # Border window for output
        self.output_border_win = stdscr.derwin(output_area_height, self.term_width, 0, 0)
        # Actual output window (inside border) - this is where text will be drawn
        self.output_win = self.output_border_win.derwin(output_area_height - 2, self.term_width - 2, 1, 1)
        self.output_win.scrollok(True) # Not strictly needed if we redraw manually


    def _main_loop(self, stdscr):
        self._setup_windows(stdscr)
        self._redraw_windows() # Initial draw

        while self.running:
            # Process message queue from other threads
            try:
                msg_type, msg_content = self.message_queue.get_nowait()
                if msg_type == "display":
                    self._add_message_to_display(msg_content)
                elif msg_type == "system_info":
                     self._add_message_to_display( (f"{msg_content}", 3, "SYSTEM", datetime.now().strftime("%I:%M %p")) )
                elif msg_type == "terminate":
                    self.KILLED_BY_SERVER = True
                    self._add_message_to_display( (f"Termination: {msg_content}. Exiting...", 6, "SYSTEM", datetime.now().strftime("%I:%M %p")) )
                    self._redraw_windows() # Show final message
                    time.sleep(2) # Brief pause to see message
                    self.running = False
                    break # Exit main loop
                elif msg_type == "input_text":
                    if self.input_buffer == self.placeholder:
                        self.input_buffer = ""
                    self.input_buffer += msg_content
            except queue.Empty:
                pass # No new messages from threads

            # Handle user input
            try:
                key = self.input_win.getch()
            except curses.error: # Can happen if window is too small during resize
                key = curses.ERR

            if key != curses.ERR:
                if self._handle_input_key(key): # True if message sent/command processed
                    self.input_buffer = "" # Clear buffer

            self._redraw_windows()
            time.sleep(0.05) # Reduce CPU usage

        # Cleanup before exiting wrapper (though wrapper handles endwin)
        if not self.KILLED_BY_SERVER:
            self._send_disconnect_message() # Politely inform server

    def _add_message_to_display(self, msg_tuple):
        # msg_tuple = (text, color_pair_id, sender_name, timestamp_str)
        self.messages.append(msg_tuple)


    def _redraw_windows(self):
        self.stdscr.erase() # Clear entire screen

        # Status Bar
        self.status_bar_win.erase()
        status_text = f" {self.CLIENT_NAME} | {self.SERVER_ADDR_STR} | AFK: {AFK_COUNTDOWN if 'AFK_COUNTDOWN' in globals() else 'N/A'}s | Help: !help"
        try:
            self.status_bar_win.addstr(0, 0, status_text[:self.term_width -1], curses.A_REVERSE)
        except curses.error: pass # Ignore if too small
        self.status_bar_win.noutrefresh()


        # Output Area
        self.output_border_win.erase()
        try:
            self.output_border_win.border()
            self.output_border_win.addstr(0, 2, " Chat Messages ", curses.color_pair(10) | curses.A_BOLD)
        except curses.error: pass
        self.output_border_win.noutrefresh()

        self.output_win.erase()
        max_y, max_x = self.output_win.getmaxyx()

        displayable_lines = []
        for full_text, color_idx, sender, ts in list(self.messages): # Iterate copy
            prefix = ""
            if sender and ts:
                 prefix = f"[{ts}] {sender}: "
            elif sender:
                 prefix = f"{sender}: "

            # Wrap lines
            wrapped_lines = textwrap.wrap(prefix + full_text, max_x if max_x > 0 else 1, drop_whitespace=False, replace_whitespace=False)
            for line_text in wrapped_lines:
                displayable_lines.append((line_text, color_idx))

        start_line_idx = max(0, len(displayable_lines) - max_y)
        for i, (line, color_idx) in enumerate(displayable_lines[start_line_idx:]):
            if i < max_y : # Ensure we don't write past the window height
                try:
                    self.output_win.addstr(i, 0, line, curses.color_pair(color_idx))
                except curses.error: pass # Writing outside window (e.g. line too long after wrap, or small window)
        self.output_win.noutrefresh()

        # Input Area
        self.input_border_win.erase()
        try:
            self.input_border_win.border()
            self.input_border_win.addstr(0, 2, " Type Message (Enter to send) ", curses.color_pair(10) | curses.A_BOLD)
        except curses.error: pass
        self.input_border_win.noutrefresh()

        self.input_win.erase()
        current_input_display = self.input_buffer
        current_color = curses.color_pair(4) # Normal input color

        is_placeholder_active = (not self.input_buffer)
        if is_placeholder_active:
             current_input_display = self.placeholder
             current_color = curses.color_pair(5) # Placeholder color

        input_max_x = self.input_win.getmaxyx()[1]
        if input_max_x <=0 : input_max_x = 1 # Avoid zero or negative width

        # Simple scroll for input text if too long
        start_char_idx = 0
        if len(current_input_display) >= input_max_x:
            start_char_idx = len(current_input_display) - input_max_x + 1

        try:
            self.input_win.addstr(0, 0, current_input_display[start_char_idx:], current_color)
        except curses.error: pass

        # Manage cursor
        if not is_placeholder_active: # Only show cursor if not placeholder
            curses.curs_set(1)
            cursor_x_pos = len(self.input_buffer) - start_char_idx
            try:
                self.input_win.move(0, cursor_x_pos)
            except curses.error: pass # If cursor tries to go out of bounds
        else:
            curses.curs_set(0) # Hide cursor if placeholder

        self.input_win.noutrefresh()
        curses.doupdate() # Refresh all windows marked with noutrefresh


    def _handle_input_key(self, key): # Returns True if buffer should clear
        if key == curses.KEY_RESIZE:
            self.term_height, self.term_width = self.stdscr.getmaxyx()
            # Re-initialize windows based on new size
            # This is complex; simpler is to tell user to restart or live with it.
            # For now, we'll just let it redraw with old subwindow sizes, which might clip.
            # A more robust solution would re-call _setup_windows or parts of it.
            self.stdscr.clear() # Clear screen on resize
            self._setup_windows(self.stdscr) # Attempt to recreate windows
            return False


        if self.input_buffer == self.placeholder and key != curses.KEY_ENTER and key != 10 and key != 13:
            if 32 <= key <= 126 or (key > 126 and chr(key).isprintable()) or key == curses.KEY_BACKSPACE or key == 127 or key == 8: # Check if printable or backspace
                self.input_buffer = "" # Clear placeholder on first valid key

        if key == curses.KEY_BACKSPACE or key == 127 or key == 8: # Backspace
            self.input_buffer = self.input_buffer[:-1]
        elif key == curses.KEY_ENTER or key == 10 or key == 13: # Enter
            if self.input_buffer and self.input_buffer != self.placeholder:
                self._process_typed_message(self.input_buffer)
                return True # Clear buffer after processing
        # Check if the key corresponds to a printable character
        # Curses getch() returns an int. For printable chars, it's the ASCII value.
        # For other keys, it's a special curses constant (e.g., curses.KEY_UP)
        # So, we first check if it's in the basic printable ASCII range,
        # then for extended characters, we can use chr(key).isprintable()
        # but ensure key is within a valid range for chr() first.
        elif (32 <= key <= 126) or \
             (key > 126 and key <= 255 and chr(key).isprintable()) or \
             (key > 255 and chr(key).isprintable()): # For potential wider character codes
             self.input_buffer += chr(key)
        return False # Buffer not cleared by default

    def _process_typed_message(self, message):
        if not message: return

        if message == "!disconnect":
            self.message_queue.put(("system_info", "Disconnecting..."))
            self.running = False # Signal main loop to stop
            # _send_disconnect_message will be called at the end of _main_loop
            return

        if message.startswith("!change "):
            new_name = message.split(" ", 1)[1].strip()
            if new_name:
                self.CLIENT_NAME = new_name
                self.message_queue.put(("system_info", f"Name changed to {new_name} locally."))
                # Heartbeat will send the new name. Server needs to handle name changes.
            else:
                self.message_queue.put(("system_info", "Usage: !change <new_name>"))
            return

        if message.startswith("!kill "):
            password = message.split(" ", 1)[1] if len(message.split(" ", 1)) > 1 else ""
            payload = self.create_json_payload(self.CLIENT_NAME, "kill_server", password)
            self.sock.send(payload.encode())
            self.message_queue.put(("system_info", "Kill command sent."))
            return


        if message == "!help":
            self._show_help()
            return

        # Regular message
        payload_json = self.create_json_payload(self.CLIENT_NAME, "message", message)
        self.sock.send(payload_json.encode())
        # Local echo of the sent message
        self._add_message_to_display( (message, 1, self.CLIENT_NAME, datetime.now().strftime("%I:%M %p")) )

    def _show_help(self):
        help_text = [
            "Available commands:",
            "  !disconnect          - Disconnect from the server.",
            "  !change <new_name>   - Change your display name.",
            "  !kill <password>     - Attempt to shut down the server.",
            "  !help                - Show this help message."
        ]
        for line in help_text:
            self.message_queue.put(("system_info", line))

    def create_json_payload(self, name, msg_type, payload_content):
        return json.dumps({
            "name": name,
            "type": msg_type,
            "payload": payload_content,
            # Timestamp is added by server for consistency, but can be added here too
            # "timestamp": datetime.now().strftime("%I:%M %p")
        })

    def heartbeat_sender(self):
        while self.running:
            time.sleep(1) # Send heartbeat every 1 second
            payload = self.create_json_payload(self.CLIENT_NAME, "heartbeat", "")
            try:
                if self.sock and self.running: # Check if socket is still valid and running
                    self.sock.send(payload.encode())
            except Exception: # Ignore errors if socket closed or network issue
                if self.running: # Only log if we are supposed to be running
                    # self.message_queue.put(("system_info", "Heartbeat failed. Connection issue?"))
                    pass # Avoid flooding with messages
                break # Stop heartbeat if error occurs and still running

    def listen_for_messages(self):
        while self.running:
            try:
                if not self.sock or not self.running: break # Exit if socket closed or not running

                # Set a timeout for receive so this loop can check self.running periodically
                # This requires better_udp_socket.receive to handle timeouts or be non-blocking.
                # For now, assuming receive() might block for a while.
                # A more robust way is for self.sock.receive() to accept a timeout.
                # If BetterUDPSocket's receive is blocking indefinitely, this thread won't exit cleanly
                # without sock.close() being called from another thread, which might raise an error here.
                msg_bytes = self.sock.receive() # This might block

                if not msg_bytes:
                    if self.running: # If we got None but are supposed to be running, it's an issue
                        time.sleep(0.1) # Avoid busy-looping on potential errors
                    continue

                msg_str = msg_bytes.decode().strip()
                msg_json = json.loads(msg_str)

                name = msg_json.get("name")
                msg_type = msg_json.get("type")
                timestamp = msg_json.get("timestamp", datetime.now().strftime("%I:%M %p"))
                payload = msg_json.get("payload")

                if msg_type == "terminate_connection":
                    self.message_queue.put(("terminate", f"Server disconnected: {payload}"))
                    return # Stop listener thread

                elif msg_type == "terminate_afk":
                    self.message_queue.put(("terminate", f"Kicked for AFK: {payload}"))
                    return # Stop listener thread

                else: # Regular message or server broadcast
                    color_pair_id = 3 # Default for server/system
                    if name == self.CLIENT_NAME:
                        pass # Already echoed locally, server shouldn't echo back our own messages
                    elif name == "SERVER":
                        color_pair_id = 3 # Yellow for server
                        self.message_queue.put(("display", (payload, color_pair_id, name, timestamp)))
                    else: # Other clients
                        color_pair_id = 2 # Green for others
                        self.message_queue.put(("display", (payload, color_pair_id, name, timestamp)))

            except json.JSONDecodeError:
                if msg_bytes and self.running: # Check msg_bytes to avoid error on empty/None
                     self.message_queue.put(("system_info", f"Received malformed JSON: {msg_bytes[:100]}"))
            except OSError as e: # Socket closed likely
                if self.running: # If we are supposed to be running, this is an unexpected closure
                    self.message_queue.put(("terminate", f"Connection error: {e}"))
                break # Exit loop
            except Exception as e:
                if self.running: # Only log if unexpected
                    self.message_queue.put(("system_info", f"Error in listen_for_messages: {e}"))
                time.sleep(0.1) # Brief pause after an error

    def _send_disconnect_message(self):
        try:
            if self.sock:
                payload = self.create_json_payload(self.CLIENT_NAME, "disconnect", "")
                self.sock.send(payload.encode())
                time.sleep(0.1) # Give it a moment
        except Exception as e:
            # Cannot use message_queue here as curses might be down
            print(f"Error sending disconnect message: {e}", file=sys.stderr)



# --- Initial Setup Window (Curses based) ---
def get_initial_input_curses(stdscr):
    curses.curs_set(1) # Show cursor for input
    stdscr.clear()

    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1) # Prompt text
        curses.init_pair(2, curses.COLOR_WHITE, -1) # Input text
        curses.init_pair(3, curses.COLOR_RED, -1) # Error text
        prompt_color = curses.color_pair(1)
        input_color = curses.color_pair(2)
        error_color = curses.color_pair(3)
    else: # Fallback for no colors
        prompt_color = curses.A_BOLD
        input_color = curses.A_NORMAL
        error_color = curses.A_BOLD

    def get_string_from_curses(y, x, prompt, max_len=30):
        stdscr.addstr(y, x, prompt, prompt_color)
        stdscr.refresh()
        curses.echo() # Echo typed characters
        s = stdscr.getstr(y, x + len(prompt), max_len).decode('utf-8').strip()
        curses.noecho()
        return s

    name = ""
    while not name:
        name = get_string_from_curses(1, 1, "Your Name: ")
        if not name: stdscr.addstr(6,1, "Name cannot be empty. ", error_color)

    server_ip_str_default = "127.0.0.1" # Default server IP
    server_ip_str = get_string_from_curses(2, 1, f"Server IP [:Port] (default {server_ip_str_default}): ", 40)
    if not server_ip_str: server_ip_str = server_ip_str_default

    client_port_str_default = "50000" # Default client port
    client_port_str = get_string_from_curses(3, 1, f"Your UDP Port (default {client_port_str_default}): ", 5)
    if not client_port_str: client_port_str = client_port_str_default

    # Validate client port
    try:
        client_port_int = int(client_port_str)
        if not (1024 <= client_port_int <= 65535):
            raise ValueError("Port out of range")
    except ValueError:
        stdscr.addstr(6, 1, f"Invalid client port: {client_port_str}. Must be 1024-65535. Press any key.", error_color)
        stdscr.getch()
        return None

    # Resolve server IP and port
    ip_to_resolve = server_ip_str
    server_dest_port = DEST_PORT # Default from global

    if ':' in server_ip_str:
        parts = server_ip_str.rsplit(':', 1)
        ip_to_resolve = parts[0]
        try:
            server_dest_port = int(parts[1])
            if not (1 <= server_dest_port <= 65535):
                 raise ValueError("Server port out of range")
        except ValueError:
            stdscr.addstr(6, 1, f"Invalid server port in address: {parts[1]}. Press any key.", error_color)
            stdscr.getch()
            return None

    try:
        resolved_server_ip = socket.gethostbyname(ip_to_resolve if ip_to_resolve else "127.0.0.1")
    except socket.gaierror: # getaddrinfo error
        stdscr.addstr(6, 1, f"Could not resolve server address: {ip_to_resolve}. Press any key.", error_color)
        stdscr.getch()
        return None
    except Exception as e:
        stdscr.addstr(6, 1, f"Error resolving server: {e}. Press any key.", error_color)
        stdscr.getch()
        return None

    stdscr.addstr(5, 1, "Connecting...", prompt_color)
    stdscr.refresh()

    return name, server_ip_str, resolved_server_ip, client_port_int, server_dest_port


if __name__ == "__main__":
    # This import is here because server.py might also have AFK_COUNTDOWN
    # and we only need it on client side for status display if available.
    try:
        from Server import AFK_COUNTDOWN
    except ImportError:
        AFK_COUNTDOWN = "N/A" # Fallback if server.py or variable not found

    import socket # For gethostbyname in init

    init_data = curses.wrapper(get_initial_input_curses)

    if init_data:
        name, server_display_addr, resolved_ip, client_port, dest_server_port = init_data
        client = ChatClientCurses(name, server_display_addr, resolved_ip, client_port, dest_server_port)
        client.run()
    else:
        print("Initialization failed or was cancelled by the user.", file=sys.stderr)