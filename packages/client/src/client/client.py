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
            threading.Thread(target=self._receive_messages, daemon=True).start()
            threading.Thread(target=self._send_heartbeat, daemon=True).start()

            # Launch curses UI
            curses.wrapper(self._run_curses_ui)

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.connection:
            self.connection.close()

    def _receive_messages(self):
        while self.running:
            try:
                # First read length
                length_bytes = self.connection.recv(0, 4)
                if not length_bytes:
                    continue
                length = int.from_bytes(length_bytes, 'little')

                # Then read full message
                message_bytes = self.connection.recv(0, length)
                if not message_bytes:
                    continue
                message = message_bytes.decode("utf-8")

                if message.strip() == "!heartbeat":
                    continue  # Ignore heartbeat messages in UI

                with self.lock:
                    self.messages.append(message)

            except Exception as e:
                with self.lock:
                    self.messages.append(f"[ERROR] {e}")
                self.stop()

    def _send_heartbeat(self):
        while self.running:
            try:
                msg = b"!heartbeat"
                self.connection.send(len(msg).to_bytes(4, 'little') + msg)
                time.sleep(1)
            except:
                self.stop()

    def _run_curses_ui(self, stdscr):
        curses.curs_set(1)
        stdscr.nodelay(True)
        stdscr.clear()

        max_y, max_x = stdscr.getmaxyx()

        input_win = curses.newwin(1, max_x, max_y - 1, 0)
        chat_win = curses.newwin(max_y - 1, max_x, 0, 0)

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
            if c == curses.KEY_BACKSPACE or c == 127:
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
