import argparse
import struct
import time
from tou.host import Host
from tou.host_connection import HostConnection

class ChatServer:
    '''Server instance for chat application'''

    class Connection:
        '''A connection to a chat client'''

        def __init_(self, connection: HostConnection):
            '''Creates a connection instance to a chat client'''

            self.connection = connection
            self.username = "Unknown"
            self.msg_len = 0
            self.buffer = b''
            self.last_seen = time.time()

    def __init__(self, address: str, port: int, idle_timeout: float, disconnect_timeout: float):
        '''Creates a chat server instance in the specified address and port'''

        self.address = address
        self.port = port
        self.idle_timeout = idle_timeout
        self.disconnect_timeout = disconnect_timeout
        self._host: Host | None = None
        self._connections: list[ChatServer.Connection] = []
        self._unnamed_connections: list[ChatServer.Connection] = []


    def start(self):
        '''Starts server instance'''

        self._host = Host(self.address, self.port)

        while self._host.state == Host.State.LISTENING:

            # Check for new listeners
            new_connection = self._host.listen()
            while new_connection:
                self._unnamed_connections.append(ChatServer.Connection(new_connection))
                new_connection = self._host.listen()

            # Process open but unnamed connections
            for connection in self._unnamed_connections:
                if connection.msg_len == 0:
                    buffer = connection.connection.recv(0, 4 - len(connection.buffer))

                    if buffer:
                        connection.buffer += buffer

                        if len(connection.buffer) == 4:
                            connection.msg_len = struct.unpack("I", connection.buffer)
                            connection.buffer = b''
                        else:
                            # msg_len is still incomplete, do not process any further
                            continue
                    elif connection.buffer and time.time() - connection.last_seen < self.disconnect_timeout:
                        self._unnamed_connections.remove(connection)
                        # disconnect because stopped sending message mid stream
                        continue
                    elif time.time() - connection.last_seen < self.idle_timeout:
                        self._unnamed_connections.remove(connection)
                        # disconnect for being idle for too long
                        continue

                if len(connection.buffer) < connection.msg_len:
                    buffer = connection.connection.recv(0, connection.msg_len - len(connection.buffer))
                    if buffer:
                        connection.buffer += buffer
                    elif time.time() - connection.last_seen < self.disconnect_timeout:
                        self._unnamed_connections.remove(connection)
                        # disconnect because stopped sending message mid stream
                        continue

                # Process complete message
                if len(connection.buffer) == connection.msg_len:
                    message = connection.buffer.decode("utf-8")
                    if message.startswith("!change"):
                        # process name change command
                        pass

                    connection.msg_len = 0
                    connection.buffer = b''

            # Process current open connections
            for connection in self._connections:
                if connection.msg_len == 0:
                    buffer = connection.connection.recv(0, 4 - len(connection.buffer))

                    if buffer:
                        connection.buffer += buffer

                        if len(connection.buffer) == 4:
                            connection.msg_len = struct.unpack("I", connection.buffer)
                            connection.buffer = b''
                        else:
                            # msg_len is still incomplete, do not process any further
                            continue
                    elif connection.buffer and time.time() - connection.last_seen < self.disconnect_timeout:
                        # disconnect because stopped sending message mid stream
                        self._connections.remove(connection)
                        continue
                    elif time.time() - connection.last_seen < self.idle_timeout:
                        # disconnect for being idle for too long
                        self._connections.remove(connection)
                        continue

                if len(connection.buffer) < connection.msg_len:
                    buffer = connection.connection.recv(0, connection.msg_len - len(connection.buffer))
                    if buffer:
                        connection.buffer += buffer
                    elif time.time() - connection.last_seen < self.disconnect_timeout:
                        # disconnect because stopped sending message mid stream
                        self._connections.remove(connection)
                        continue

                # Process complete message
                if len(connection.buffer) == connection.msg_len:
                    message = connection.buffer.decode("utf-8")

                    # !disconnect should be handled on the client and should just close the connection

                    if message.startswith("!kill"):
                        self._host.close()
                        # process server shutdown command
                        return
                    if message.startswith("!change"):
                        new_name = message[8:].strip()
                        connection.username = new_name
                        # process name change command
                    if message == "!heartbeat":

                        # process heartbeat
                        # echo heartbeat back to client to inform that the server is still open
                        pass
                    else:
                        # process normal message
                        for other in self._connections:
                            if other is not connection:
                                msg = f"[{connection.username}] {message}".encode("utf-8")
                                other.connection.send(struct.pack("<I", len(msg)) + msg)

                    connection.msg_len = 0
                    connection.buffer = b''

    def stop(self):
        """Stop the chat server"""
        self._host.close()
        print("Server stopped.")

def main():
    parser = argparse.ArgumentParser(description='Chat Room Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=12345, help='Port to bind to')
    parser.add_argument('--password', default='admin123', help='Admin password for !kill command')

    args = parser.parse_args()

    server = ChatServer(args.host, args.port, 30, 60)
    try:
        server.start();
    except KeyboardInterrupt:
        server.stop();


if __name__ == "__main__":
    main()