import curses
import threading
import time
from datetime import datetime
from typing import Optional
from tou.connection import Connection
from tou.client_connection import ClientConnection


class CursesChatClient:
    def __init__(self, host: str, port: int, display_name: str):
        self.host = host
        self.port = port
        self.display_name = display_name
        self.connection: Optional[Connection] = None
        self.running = False
        self.last_heartbeat_time = time.time()
        self.waiting_for_heartbeat_response = False
        self.last_heartbeat_sent_time = 0.0

        self.messages: list[str] = []
        self.lock = threading.Lock()

    def start(self):
        try:
            self.connection = ClientConnection(self.host, self.port)
            self.running = True

            # Send display name change command
            msg = f"!change {self.display_name}".encode("utf-8")
            self.connection.send(len(msg).to_bytes(4, 'little') + msg)

            # Start background threads
            self._recv_thread = threading.Thread(target=self._receive_messages)
            self._heartbeat_thread = threading.Thread(target=self._send_heartbeat)
            self._heartbeat_monitor_thread = threading.Thread(target=self._monitor_heartbeat)

            self._recv_thread.start()
            self._heartbeat_thread.start()
            self._heartbeat_monitor_thread.start()

            # Launch curses UI
            curses.wrapper(self._run_curses_ui)

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.connection.state == Connection.State.CONNECTED:
            self.connection.close()
        self._recv_thread.join()
        self._heartbeat_thread.join()
        self._heartbeat_monitor_thread.join()

    def _monitor_heartbeat(self):
        HEARTBEAT_TIMEOUT = 5  # seconds
    
        while self.running:
            if self.waiting_for_heartbeat_response:
                if time.time() - self.last_heartbeat_sent_time > HEARTBEAT_TIMEOUT:
                    with self.lock:
                        self.messages.append("[SYSTEM] Disconnected from server")
                    self.stop()
                    break
            time.sleep(1)

    def _receive_messages(self):
        buffer = b''

        while self.running:
            try:
                # Non-blocking read, may return less than requested
                chunk = self.connection.recv(0, 4096)
                if chunk:
                    buffer += chunk
                else:
                    time.sleep(0.01)
                    continue

                # Process as many full messages as possible
                while True:
                    if len(buffer) < 4:
                        break  # Not enough data for length prefix

                    msg_length = int.from_bytes(buffer[0:4], 'little')
                    if len(buffer) < 4 + msg_length:
                        break  # Wait for full message

                    # Extract and decode message
                    msg_bytes = buffer[4:4 + msg_length]
                    message = msg_bytes.decode("utf-8")

                    # Remove processed data from buffer
                    buffer = buffer[4 + msg_length:]

                    if message.strip() == "!heartbeat":
                        self.last_heartbeat_time = time.time()
                        self.waiting_for_heartbeat_response = False
                        continue

                    with self.lock:
                        self.messages.append(message)

            except Exception as e:
                with self.lock:
                    self.messages.append(f"[ERROR] {e}")
                self.stop()
                break

    def _send_heartbeat(self):
        while self.running and self.connection.state == Connection.State.CONNECTED:
            try:
                msg = b"!heartbeat"
                self.connection.send(len(msg).to_bytes(4, 'little') + msg)
    
                self.last_heartbeat_sent_time = time.time()
                self.waiting_for_heartbeat_response = True
    
                time.sleep(10)
            except:
                self.stop()

    def _run_curses_ui(self, stdscr):
        curses.curs_set(1)
        stdscr.nodelay(True)
        stdscr.clear()

        max_y, max_x = stdscr.getmaxyx()

        input_win = curses.newwin(1, max_x, max_y - 1, 0)
        input_win.nodelay(True)
        chat_win = curses.newwin(max_y - 1, max_x, 0, 0)
        chat_win.nodelay(True)

        input_buffer = ""

        while self.running:
            chat_win.clear()

            # Display messages
            with self.lock:
                displayed_messages = self.messages[-(max_y - 2):]
                for i, msg in enumerate(displayed_messages):
                    chat_win.addstr(i, 0, msg[:max_x - 1])

            chat_win.refresh()

            # Handle user input
            input_win.clear()
            input_win.addstr(0, 0, "> " + input_buffer)
            input_win.refresh()

            c = input_win.getch()
            if c in (curses.KEY_BACKSPACE, 127, 8):
                input_buffer = input_buffer[:-1]
            elif c in (curses.KEY_ENTER, 10, 13):
                message = input_buffer.strip()
                if message:
                    if message == "!disconnect":
                        self.stop()
                        break
                    elif message.startswith("!change "):
                        self.display_name = message.split(" ", 1)[1]
                    data = message.encode("utf-8")
                    try:
                        self.connection.send(len(data).to_bytes(4, 'little') + data)
                    except:
                        self.stop()
                        break
                input_buffer = ""
            elif c >= 32 and c <= 126:
                input_buffer += chr(c)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Curses Chat Client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=12345, help="Server port")
    parser.add_argument("--name", default="Anonymous", help="Display name")

    args = parser.parse_args()

    client = CursesChatClient(args.host, args.port, args.name)
    try:
        client.start()
    except KeyboardInterrupt:
        client.stop()


if __name__ == "__main__":
    main()
