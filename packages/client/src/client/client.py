import socket
import threading
import time
from datetime import datetime
from typing import Optional
from tou.connection import Connection
from tou.client_connection import ClientConnection


class ChatClient:
    def __init__(self, host: str, port: int, display_name: str):
        self.host = host
        self.port = port
        self.display_name = display_name
        self.connection: Optional[Connection] = None
        self.running = False

    def start(self):
        """Start the chat client."""
        try:
            # Establish connection
            # self.connection = Connection(
            #     local_ip_addr="0.0.0.0",
            #     local_port=0,
            #     remote_ip_addr=self.host,
            #     remote_port=self.port,
            #     incoming_window_size=4096,
            #     outgoing_window_size=4096,
            #     resend_delay=0.1,
            #     timeout=1.0,
            # )
            self.connection = ClientConnection(
                self.host,
                self.port
            )
    # def __init__(self, ip_addr: str, port: int, window_size: int = 4096, resend_delay: float = 0.1, timeout: float = 1):
            print("connecting")
            self.connection._connect()
            print("finish connecting")
            self.running = True
            new_name = "l4mbads"
            self.connection.send(f"!change {new_name}".encode("utf-8"))
            # self.connection._socket.send("xxxx")

            # Start background threads
            # threading.Thread(target=self._receive_messages, daemon=True).start()
            # threading.Thread(target=self._send_heartbeat, daemon=True).start()

            print(f"Connected to {self.host}:{self.port} as {self.display_name}")
            # self._handle_user_input()

        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.stop()

    def stop(self):
        """Stop the chat client."""
        self.running = False
        if self.connection:
            self.connection.close()
        print("Disconnected from the server.")

    def _receive_messages(self):
        """Receive messages from the server."""
        while self.running:
            try:
                print("sending heartbeat")
                data = self.connection.recv(min_size=1, max_size=4096)
                if data:
                    message = data.decode("utf-8")
                    print(message)
            except Exception as e:
                print(f"Error receiving message: {e}")
                self.stop()

    def _send_heartbeat(self):
        """Send periodic heartbeat to the server."""
        while self.running:
            try:
                self.connection.send(b"!heartbeat")
                time.sleep(10)
            except Exception as e:
                print(f"Error sending heartbeat: {e}")
                self.stop()

    def _handle_user_input(self):
        """Handle user input."""
        while self.running:
            try:
                message = input()
                if message.startswith("!"):
                    self._handle_command(message)
                else:
                    self.connection.send(f"{self.display_name}: {message}".encode("utf-8"))
            except Exception as e:
                print(f"Error sending message: {e}")
                self.stop()

    def _handle_command(self, command: str):
        """Handle special commands."""
        if command == "!disconnect":
            self.stop()
        elif command.startswith("!change "):
            new_name = command.split(" ", 1)[1].strip()
            if new_name:
                self.display_name = new_name
                self.connection.send(f"!change {new_name}".encode("utf-8"))
        else:
            print(f"Unknown command: {command}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Chat Room Client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=12345, help="Server port")
    parser.add_argument("--name", default="Anonymous", help="Display name")

    args = parser.parse_args()

    client = ChatClient(args.host, args.port, args.name)
    try:
        client.start()
    except KeyboardInterrupt:
        client.stop()


if __name__ == "__main__":
    main()