import argparse
import time
from datetime import datetime
from tou.host import Host
from tou.host_connection import HostConnection
from tou.connection import Connection

class ChatServer:
    '''Server instance for chat application'''

    class Connection:
        '''A connection to a chat client'''

        def __init__(self, connection: HostConnection):
            '''Creates a connection instance to a chat client'''

            self.connection = connection
            self.username = "Unknown"
            self.msg_len = 0
            self.buffer = b''
            self.last_seen = time.time()

    def __init__(self, address: str, port: int, password: str, idle_timeout: float, disconnect_timeout: float):
        '''Creates a chat server instance in the specified address and port'''

        self.address = address
        self.port = port
        self.password = password
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
                print("New connection found")
                new_connection = self._host.listen()

            # Process open but unnamed connections
            for connection in self._unnamed_connections:
                if connection.connection.state != Connection.State.CONNECTED:
                    self._unnamed_connections.remove(connection)
                    continue

                if connection.msg_len == 0:
                    buffer = connection.connection.recv(0, 4 - len(connection.buffer))

                    if buffer:
                        connection.buffer += buffer
                        connection.last_seen = time.time()

                        if len(connection.buffer) == 4:
                            connection.msg_len = int.from_bytes(buffer, 'little')
                            connection.buffer = b''
                        else:
                            # msg_len is still incomplete, do not process any further
                            continue
                    elif connection.buffer and time.time() - connection.last_seen > self.disconnect_timeout:
                        # disconnect because stopped sending message mid stream
                        connection.close()
                        self._unnamed_connections.remove(connection)
                        continue
                    elif time.time() - connection.last_seen > self.idle_timeout:
                        # disconnect for being idle for too long
                        connection.close()
                        self._unnamed_connections.remove(connection)
                        continue

                if len(connection.buffer) < connection.msg_len:
                    buffer = connection.connection.recv(0, connection.msg_len - len(connection.buffer))
                    if buffer:
                        connection.buffer += buffer
                        connection.last_seen = time.time()
                    elif time.time() - connection.last_seen > self.disconnect_timeout:
                        # disconnect because stopped sending message mid stream
                        connection.close()
                        self._unnamed_connections.remove(connection)
                        continue

                # Process complete message
                if len(connection.buffer) == connection.msg_len:
                    connection.last_seen = time.time()
                    message = connection.buffer.decode("utf-8")

                    if message.startswith("!change"):
                        # process name change command
                        new_name = message[8:].strip()
                        connection.username = new_name
                        print(f"{new_name} joined the room!")
                        self._unnamed_connections.remove(connection)

                        # broadcast to other members
                        msg = ChatServer.generate_message("SERVER", f"{connection.username} has joined, say hi!").encode("utf-8")
                        data = len(msg).to_bytes(4, 'little') + msg
                        self.broadcast(data)

                        # send message to new user
                        msg = ChatServer.generate_message("SERVER", f"Welcome, {connection.username}!").encode("utf-8")
                        data = len(msg).to_bytes(4, 'little') + msg
                        connection.connection.send(data)

                        # add user as established connection
                        self._connections.append(connection)

                    connection.msg_len = 0
                    connection.buffer = b''

            # Process current open connections
            for connection in self._connections:
                if connection.connection.state != Connection.State.CONNECTED:
                    # process disconnection
                    print(f"{connection.username} was disconnected")
                    self._connections.remove(connection)
                    msg = ChatServer.generate_message("SERVER", f"{connection.username} has disconnected").encode("utf-8")
                    data = len(msg).to_bytes(4, 'little') + msg
                    self.broadcast(data)
                    continue

                if connection.msg_len == 0:
                    buffer = connection.connection.recv(0, 4 - len(connection.buffer))

                    if buffer:
                        connection.buffer += buffer
                        connection.last_seen = time.time()

                        if len(connection.buffer) == 4:
                            connection.msg_len = int.from_bytes(buffer, 'little')
                            connection.buffer = b''

                        else:
                            # msg_len is still incomplete, do not process any further
                            continue

                    elif connection.buffer and time.time() - connection.last_seen > self.disconnect_timeout:
                        # disconnect because stopped sending message mid stream
                        print(f"{connection.username} was disconnected")
                        connection.close()
                        self._connections.remove(connection)
                        msg = ChatServer.generate_message("SERVER", f"{connection.username} has disconnected").encode("utf-8")
                        data = len(msg).to_bytes(4, 'little') + msg
                        self.broadcast(data)
                        continue

                    elif time.time() - connection.last_seen > self.idle_timeout:
                        # disconnect for being idle for too long
                        connection.close()
                        self._connections.remove(connection)
                        continue

                if len(connection.buffer) < connection.msg_len:
                    buffer = connection.connection.recv(0, connection.msg_len - len(connection.buffer))

                    if buffer:
                        connection.buffer += buffer
                        connection.last_seen = time.time()

                    elif time.time() - connection.last_seen > self.disconnect_timeout:
                        # disconnect because stopped sending message mid stream
                        print(f"{connection.username} was disconnected")
                        connection.close()
                        self._connections.remove(connection)
                        continue

                # Process complete message
                if len(connection.buffer) == connection.msg_len and connection.msg_len > 0:
                    connection.last_seen = time.time()
                    message = connection.buffer.decode("utf-8")

                    # !disconnect should be handled on the client and should just close the connection

                    if message.startswith("!kill "):
                        # verify password
                        password = message[6:]
                        if self.password == password:

                            # process server shutdown command
                            msg = ChatServer.generate_message("SERVER", f"Shutting down...").encode("utf-8")
                            data = len(msg).to_bytes(4, 'little') + msg
                            self.broadcast(data)
    
                            # close the server
                            self._host.close()
                            return
                        
                        else:
                            
                            # notify failure to client
                            msg = ChatServer.generate_message("SERVER", f"Invalid password!").encode("utf-8")
                            data = len(msg).to_bytes(4, 'little') + msg
                            connection.connection.send(data)
                    
                    elif message.startswith("!change "):
                        # process name change command
                        new_name = message[8:]
                        old_name = connection.username
                        connection.username = new_name

                        # notify others
                        msg = ChatServer.generate_message("SERVER", f"{old_name} renamed themselves to {new_name}").encode("utf-8")
                        data = len(msg).to_bytes(4, 'little') + msg
                        self.broadcast(data)

                    elif message.startswith("!heartbeat"):
                        # echo back heartbeat
                        print(f"heartbeat received from {connection.username}")
                        msg = f"!heartbeat".encode("utf-8")
                        data = len(msg).to_bytes(4, 'little') + msg
                        connection.connection.send(data)

                    else:
                        # process normal message
                        msg = ChatServer.generate_message(connection.username, message).encode("utf-8")
                        data = len(msg).to_bytes(4, 'little') + msg
                        self.broadcast(data)
                                

                    connection.msg_len = 0
                    connection.buffer = b''
    

    @staticmethod
    def generate_message(sender: str, message: str) -> str:
        '''Generates a message string using the current time'''

        return f"({datetime.now().strftime("%H:%M")}) [{sender}] : {message}"
    

    def broadcast(self, data: bytes):
        '''Broadcasts information to all connected clients'''
        for connection in self._connections:
            connection.connection.send(data)


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

    server = ChatServer(args.host, args.port, args.password, 30, 1)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()