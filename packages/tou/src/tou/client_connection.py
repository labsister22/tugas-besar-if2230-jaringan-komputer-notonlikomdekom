import socket
from time import time, sleep
from tou.segment import Segment, SegmentHeader
from tou.connection import Connection

class ClientConnection(Connection):
    '''TCP over UDP connection class for a 1-to-1 connection from a client to a remote host.'''


    def __init__(self, ip_addr: str, port: int, window_size: int = 4096, resend_delay: float = 0.1, timeout: float = 10):
        '''Creates a connection object and establishes a handshake with the remote host'''

        # Internal socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(('', 0))
        self._socket.connect((ip_addr, port))

        super().__init__(
            self._socket.getsockname()[0],
            self._socket.getsockname()[1],
            ip_addr,
            port,
            window_size,
            SegmentHeader.SIZE,
            resend_delay,
            timeout
        )

        self.state = ClientConnection.State.HANDSHAKE
        self._socket.settimeout(timeout)
        self._three_way_handshake()
        self._socket.setblocking(False)

        super()._connect()


    def _internal_recv(self, buf_size) -> bytes:
        try:
            return self._socket.recv(buf_size)
        except socket.error as e:
            if e.errno == socket.EWOULDBLOCK:
                return b''
            else:
                raise e
        except Exception as e:
            raise e


    def _internal_send(self, data):
        self._socket.send(data)


    def _three_way_handshake(self):
        '''Establishes a three-way-handshake with the remote host of this connection'''

        self._last_ack_time = time()
        while (time() - self._last_ack_time <= self.timeout):
            # 1. Send SYN
            print("sending SYN")
            self._highest_sent_seq = Segment.generate_random_syn()

            syn_segment = Segment(
                self.local_addr[1],
                self.remote_addr[1],
                self._highest_sent_seq,
                0,
                SegmentHeader.SYN_FLAG,
                self.incoming_window_size,
                b''
            )

            self._socket.send(syn_segment.pack())

            # 2. Wait for SYN ACK
            print("waitin SYN ACK")
            reply = self._internal_recv(SegmentHeader.SIZE)
            print("received packet")

            synack_segment = Segment.unpack(reply)

            self._highest_received_ack = synack_segment.header.ack_num
            self._highest_accepted_seq = synack_segment.header.seq_num
            self._outgoing_window_size = synack_segment.header.window

            print("OUTGOING WINDOW SIZE: ", self._outgoing_window_size)

            syn_valid = synack_segment.header.flags & SegmentHeader.SYN_FLAG
            ack_valid = synack_segment.header.flags & SegmentHeader.ACK_FLAG
            synack_valid = syn_valid and ack_valid

            if not (synack_valid and self._highest_received_ack == self._highest_sent_seq + 1):
                print("not SYN ACK")
                # retry handshake
                sleep(self.resend_delay)
                continue

            # 3. Reply with ACK
            ack_segment = Segment(
                self.local_addr[1],
                self.remote_addr[1],
                self._highest_sent_seq,
                self._highest_accepted_seq + 1,
                SegmentHeader.ACK_FLAG,
                self.incoming_window_size,
                b''
            )

            self._socket.send(ack_segment.pack())
            break

        self._last_ack_time = time()

