import struct
import zlib

SYN = 0b00000001  # 1
FIN = 0b00000010  # 2
ACK = 0b00000100  # 4

PORT_BITS = 16
SEQ_BITS = 32
ACK_BITS = 32
CHECKSUM_BITS = 32
WINDOW_BITS = 16
FLAGS_BITS = 8

PORT_MAX = 2**PORT_BITS - 1
SEQ_MAX = 2**SEQ_BITS - 1
ACK_MAX = 2**ACK_BITS - 1
CHECKSUM_MAX = 2**CHECKSUM_BITS - 1
WINDOW_MAX = 2**WINDOW_BITS - 1
FLAGS_MAX = 2**FLAGS_BITS - 1

MAX_HEADER_SIZE = 20
MAX_PAYLOAD_SIZE = 64
RECV_BUFFER = MAX_HEADER_SIZE + MAX_PAYLOAD_SIZE

class Segment:
    def __init__(self, src_port, dest_port, seq_num=0, ack_num=0, checksum=0, window=0, flags=0, payload=b''):
        self.src_port = src_port & PORT_MAX
        self.dest_port = dest_port & PORT_MAX
        self.seq_num = seq_num & SEQ_MAX
        self.ack_num = ack_num & ACK_MAX
        self.checksum = checksum & CHECKSUM_MAX
        self.window = window & WINDOW_MAX
        self.flags = flags & FLAGS_MAX
        self.payload = payload

    def _pack_raw(self):
        header = struct.pack('!HHIIIHBB',
            self.src_port,
            self.dest_port,
            self.seq_num,
            self.ack_num,
            0,
            self.window,
            self.flags,
            0
        )
        return header + self.payload

    def calculate_checksum(self):
        return zlib.crc32(self._pack_raw()) & 0xFFFFFFFF

    def pack(self, include_checksum=True):
        if include_checksum:
            self.checksum = self.calculate_checksum()

        header = struct.pack('!HHIIIHBB',
            self.src_port,
            self.dest_port,
            self.seq_num,
            self.ack_num,
            self.checksum,
            self.window,
            self.flags,
            0
        )
        return header + self.payload

    @classmethod
    def unpack(cls, data):
        header = data[:20]
        payload = data[20:]
        src_port, dest_port, seq_num, ack_num, checksum, window, flags, _ = struct.unpack('!HHIIIHBB', header)
        return cls(src_port, dest_port, seq_num, ack_num, checksum, window, flags, payload)

    def verify_checksum(self):
        return self.checksum == self.calculate_checksum()
