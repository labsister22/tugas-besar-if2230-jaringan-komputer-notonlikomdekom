import socket
from time import sleep
from enum import Enum, auto
from threading import Thread, Lock
from tou.host_connection import HostConnection
from tou.segment import Segment, SegmentHeader

class Host:
    '''TCP over UDP host that accepts incoming connections'''


    class _ConnectionRequest:
        '''Describes state of connection request established by a client'''


        def __init__(self, ip_addr: str, port: int, local_seq_num: int, remote_seq_num: int, incoming_window: int, outgoing_window: int):
            '''Creates a host connection request that stores information about an ongoing handshake'''

            self.ip_addr = ip_addr
            self.port = port
            self.incoming_window = incoming_window
            self.outgoing_window = outgoing_window
            self.local_seq_num = local_seq_num
            self.remote_seq_num = remote_seq_num


    class State(Enum):
        LISTENING = auto(),
        CLOSED = auto()


    def __init__(self, ip_addr: str, port: int, window_size: int = 4096, resend_delay: float = 0.1, timeout: float = 1, max_connections: int = 999):
        '''Creates a host on a given ip address and port (max_connections = -1 means no limit)'''

        self.address = (ip_addr, port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(self.address)
        self._socket.setblocking(False)

        self.max_connections = max_connections
        self._queued_connections_lock = Lock()
        self._listened_connections: list[HostConnection] = []
        self._queued_connections: list[HostConnection] = []
        self._starting_connections: list[Host._ConnectionRequest] = []

        self.window_size = window_size
        self.resend_delay = resend_delay
        self.timeout = timeout

        self.state = Host.State.LISTENING
        self._worker_thread = Thread(target=self._background_recv)
        self._worker_thread.start()


    def listen(self) -> HostConnection | None:
        '''Listens to incoming connection requests and returns a HostConnection object when a connection has been established'''

        if self.state != Host.State.LISTENING:
            return None

        with self._queued_connections_lock:
            if self._queued_connections:
                connection = self._queued_connections.pop(0)
                self._listened_connections.append(connection)
                return connection
            else:
                return None


    def close(self):
        '''Closes the host and all of its connections'''

        if self.state != Host.State.LISTENING:
            raise RuntimeError("Host already closed")

        self.state = Host.State.CLOSED
        self._worker_thread.join()


    def _background_recv(self):
        '''Background procedure to receive incoming segments'''

        while self.state == Host.State.LISTENING:
            sleep(self.resend_delay)

            try:
                data, addr = self._socket.recvfrom(SegmentHeader.SIZE + Segment.MAX_SIZE)
                
                if not data:
                    continue

            except Exception:
                continue

            # If address is in listened or queued connections, dispatch
            # If address is in requested connections, verify ack and establish connection
            # If data is a syn segment, create request and reply with synack
            # Ignore otherwise

            dispatched = False

            with self._queued_connections_lock:
                for connection in self._listened_connections:
                    if connection.remote_addr == addr:
                        connection._internal_recvfrom(data)
                        dispatched = True
                        break

                if dispatched:
                    continue

                for connection in self._queued_connections:
                    if connection.remote_addr == addr:
                        connection._internal_recvfrom(data)
                        dispatched = True
                        break

                if dispatched:
                    continue

                try:
                    segment = Segment.unpack(data)
                except Exception:
                    # Drop if data is not recognizable
                    continue

                for request in self._starting_connections:
                    if request.ip_addr == addr[0] and request.port == addr[1]:
                        dispatched = True

                        self._starting_connections.remove(request)

                        # Make sure ACK is valid before connecting
                        if (segment.header.flags & SegmentHeader.ACK_FLAG) and (segment.header.ack_num == request.local_seq_num + 1):
                            new_connection = HostConnection(self, request)
                            self._queued_connections.append(new_connection)

                        break

            if dispatched:
                continue

            if segment.header.flags == SegmentHeader.SYN_FLAG and len(self._listened_connections) + len(self._queued_connections) + len(self._starting_connections) < self.max_connections:
                new_request = Host._ConnectionRequest(addr[0], addr[1], 0, 0, 0, 0)
                new_request.local_seq_num = Segment.generate_random_syn()
                new_request.remote_seq_num = segment.header.seq_num
                new_request.incoming_window = self.window_size
                new_request.outgoing_window = segment.header.window

                self._starting_connections.append(new_request)

                # Reply with SYN ACK
                try:
                    synack_segment = Segment(
                        self.address[1],
                        new_request.port,
                        new_request.local_seq_num,
                        new_request.remote_seq_num + 1,
                        SegmentHeader.SYN_FLAG | SegmentHeader.ACK_FLAG,
                        new_request.incoming_window,
                        b''
                    )
                except ValueError as e:
                    print(repr(e))

                self._socket.sendto(synack_segment.pack(), addr)


    def _internal_sendto(self, ip_addr: str, port: int, data: bytes):
        '''Sends raw UDP data to a specified ip address and port, used by host connections to send data to client'''

        self._socket.sendto(data, (ip_addr, port))

    def _internal_disconnect(self, connection: HostConnection):
        '''Used by a dispatched host connection to disconnect'''

        with self._queued_connections_lock:
            self._listened_connections.remove(connection)
            self._queued_connections.remove(connection)