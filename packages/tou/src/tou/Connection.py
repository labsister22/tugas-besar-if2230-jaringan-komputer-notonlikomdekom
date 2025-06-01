from abc import abstractmethod, ABCMeta
from time import time, sleep
from threading import Thread, Lock
from enum import Enum, auto
from tou.segment import Segment, SegmentHeader

class Connection(metaclass=ABCMeta):
    '''TCP over UDP connection class for a 1-to-1 connection'''


    class State(Enum):
        HANDSHAKE = auto(),
        CONNECTED = auto(),
        CLOSING = auto(),
        CLOSED = auto()


    def __init__(self, local_ip_addr: str, local_port: int, remote_ip_addr: str, remote_port: int, incoming_window_size: int, outgoing_window_size: int, resend_delay: float, timeout: float):
        '''Creates a connection object'''

        self.remote_addr = (remote_ip_addr, remote_port)
        self.local_addr = (local_ip_addr, local_port)

        # Timing attributes
        self.resend_delay = resend_delay
        self.timeout = timeout
        self._last_ack_time = time()

        # Attributes for outgoing data
        self._unsent_data: bytes = b''
        self._unsent_data_lock = Lock()
        self._queued_segments: list[Segment] = []
        self._queued_segments_size: int = 0
        self.outgoing_window_size: int = outgoing_window_size

        # Attributes for incoming data
        self.incoming_window_size: int = incoming_window_size
        self._incoming_window: list[Segment] = []
        self._received_data: bytes = b''
        self._received_data_lock = Lock()

        # Current seq and ack numbers
        self._highest_sent_seq = 0
        self._highest_accepted_seq = 0
        self._highest_received_ack = 0
        self._need_send_ack = False


    def send(self, data: bytes):
        '''Sends data through the connection'''

        if self.state != Connection.State.CONNECTED:
            return
            # raise RuntimeError("Connection not in connected state!")

        with self._unsent_data_lock:
            self._unsent_data = self._unsent_data + data


    def recv(self, min_size: int, max_size: int) -> bytes:
        '''Receives incoming data from the connection'''

        if self.state != Connection.State.CONNECTED:
            return self._received_data[:max_size]
            # raise RuntimeError("Connection not in connected state!")

        while len(self._received_data) < min_size:
            sleep(self.resend_delay)

        with self._received_data_lock:
            if len(self._received_data) < max_size:
                data = self._received_data
                self._received_data = b''
            else:
                data = self._received_data[:max_size]
                self._received_data = self._received_data[max_size:]

        return data


    def close(self):
        '''Closes the connection, disables further sends and receives'''

        if self.state != Connection.State.CONNECTED:
            raise RuntimeError("Connection not in connected state!")

        self.state = Connection.State.CLOSING
        self._flow_control_thread.join()

        self.state = Connection.State.CLOSED


    def _connect(self):
        '''Starts the connection'''

        self.state = Connection.State.CONNECTED
        self._flow_control_thread = Thread(target=self._background_task)
        self._flow_control_thread.start()

    def _background_task(self):
        '''Task that runs in the background, responsible for sending and receiving data from the socket'''

        while self.state == Connection.State.CONNECTED:
            self._background_recv()
            self._background_send()
            sleep(self.resend_delay)

        # Handle closing locally
        if self.state == Connection.State.CLOSING:
            while self._unsent_data or self._queued_segments:
                self._background_recv()
                self._background_send()
                sleep(self.resend_delay)

            fin_segment = Segment(
                    self.local_addr[1],
                    self.remote_addr[1],
                    self._highest_sent_seq,
                    self._highest_accepted_seq + 1,
                    SegmentHeader.FIN_FLAG,
                    self.incoming_window_size,
                    b''
                )
            self._internal_send(fin_segment.pack())

        # Respond to FIN from peer with FIN ACK
        if self.state == Connection.State.CLOSED:
            fin_segment = Segment(
                    self.local_addr[1],
                    self.remote_addr[1],
                    self._highest_sent_seq,
                    self._highest_accepted_seq + 1,
                    SegmentHeader.FIN_FLAG | SegmentHeader.ACK_FLAG,
                    self.incoming_window_size,
                    b''
                )
            self._internal_send(fin_segment.pack())

        self._after_disconnect()


    def _background_send(self):
        '''Background procedure for sending segments'''

        # Move unsent data into segment queue if space is available
        with self._unsent_data_lock:
            if self._unsent_data:
                if not self._queued_segments:
                    self._last_ack_time = time()

                while self._queued_segments_size + SegmentHeader.SIZE < self.outgoing_window_size and self._unsent_data:
                    # Get data that will be sent
                    data_size = min(len(self._unsent_data), min(self.outgoing_window_size - self._queued_segments_size, Segment.MAX_SIZE + SegmentHeader.SIZE))
                    data = self._unsent_data[:data_size]
                    self._unsent_data = self._unsent_data[data_size:]

                    self._highest_sent_seq += 1

                    segment = Segment(
                        self.local_addr[1],
                        self.remote_addr[1],
                        self._highest_sent_seq,
                        self._highest_accepted_seq + 1,
                        0,
                        self.incoming_window_size,
                        data
                    )

                    self._queued_segments.insert(-1, segment)
                    self._queued_segments_size += SegmentHeader.SIZE + len(data)

        # Send all segments in queue
        if self._queued_segments:
            # Check if other side is actually responding to sent segments
            if time() - self._last_ack_time > self.timeout:
                self.state = Connection.State.CLOSING
                return

            for segment in self._queued_segments:
                segment.header.ack_num = self._highest_accepted_seq + 1

                # Piggyback ACK if needed
                if self._need_send_ack:
                    self._need_send_ack = False
                    segment.header.flags = segment.header.flags | SegmentHeader.ACK_FLAG

                self._internal_send(segment.pack())


    def _background_recv(self):
        '''Background procedure for receiving segments'''

        if self.state != Connection.State.CONNECTED:
            return

        # First, attempt to receive a segment and verify it before processing, closes the connection on an error
        try:
            data = self._internal_recv(self.incoming_window_size)

            if not data:
                return

            segment = Segment.unpack(data)
        except Exception as e:
            return # Ignore errors, move on to next segment

        # Remove all queued segments that have a sequence number lower than the highest received ack
        if segment.header.flags & SegmentHeader.ACK_FLAG:
            if segment.header.ack_num > self._highest_received_ack:
                self._highest_received_ack = segment.header.ack_num
                self._last_ack_time = time()

                while self._queued_segments:
                    if self._queued_segments[0].header.seq_num < self._highest_received_ack:
                        self._queued_segments_size -= SegmentHeader.SIZE + self._queued_segments[0].header.size
                        self._queued_segments.pop(0)
                    else:
                        break

        # Handle receiving data and sending acknowledgement
        if segment.payload:
            if segment.header.seq_num <= self._highest_accepted_seq:
                # ACK for this segment has already been sent, OK to send again
                self._need_send_ack = True
            else:
                # Need to check if ACK for this segment can be sent
                total_size = SegmentHeader.SIZE + segment.header.size
                index = 0

                while index < len(self._incoming_window):
                    if self._incoming_window[index].header.seq_num == segment.header.seq_num:
                        index = -1
                        self._need_send_ack = True
                        break
                    elif self._incoming_window[index].header.seq_num > segment.header.seq_num:
                        break

                    total_size += SegmentHeader.SIZE + self._incoming_window[index].header.size
                    index += 1

                if index != -1 and total_size < self.incoming_window_size:
                    self._incoming_window.insert(index, segment)

                    # Enforce incoming window size limit
                    for i in range(index + 1, len(self._incoming_window)):
                        total_size += SegmentHeader.SIZE + self._incoming_window[i].header.size
                        if total_size >= self.incoming_window_size:
                            while len(self._incoming_window) > i:
                                self._incoming_window.pop(-1)

                    # Check if segment was next expected sequence number, flush consecutive segments and send ACK if so
                    with self._received_data_lock:
                        while self._incoming_window:
                            if self._incoming_window[0].header.seq_num == self._highest_accepted_seq + 1:
                                self._highest_accepted_seq += 1
                                self._received_data += self._incoming_window[0].payload
                                self._incoming_window.pop(0)
                                self._need_send_ack = True
                            else:
                                break

            # Send ACK immediately if piggybacking is not available
            # print("mau ack", self._need_send_ack)
            if self._need_send_ack and not (self._queued_segments or self._unsent_data):
                self._need_send_ack = False
                ack_segment = Segment(
                    self.local_addr[1],
                    self.remote_addr[1],
                    self._highest_sent_seq,
                    self._highest_accepted_seq + 1,
                    SegmentHeader.ACK_FLAG,
                    self.incoming_window_size,
                    b''
                )
                self._internal_send(ack_segment.pack())

            # Handle FIN from remote
            if segment.header.flags & SegmentHeader.FIN_FLAG:
                self.state = Connection.State.CLOSED

    def _after_disconnect(self):
        pass

    @abstractmethod
    def _internal_send(self, data: bytes):
        '''Internal implementation of send that should be overriden by inheriting classes'''

        raise NotImplementedError(self._internal_send)

    @abstractmethod
    def _internal_recv(self, buf_size: int) -> bytes:
        '''Internal implementation of recv that should be overriden by inheriting classes'''

        raise NotImplementedError(self._internal_recv)
