import struct

'''
Header of a TCP over UDP segment

Format:
- source port       (16 bits)
- destination port  (16 bits)
- sequence number   (32 bits)
- ack number        (32 bits)
- flags             (16 bits)
- checksum          (16 bits)
- window size       (16 bits)
- payload size      (16 bits)

Total size = 160 bits / 20 bytes

Note: Flag size is 16 bits just for alignment
'''

SYN = 1
FIN = 2
ACK = 4

# PORT_BITS = 16
# SEQ_BITS = 32
# ACK_BITS = 32
# CHECKSUM_BITS = 32
# WINDOW_BITS = 16
# FLAGS_BITS = 8

# MAX_PORT = 2**PORT_BITS - 1
# MAX_SEQ_NUM = 2**SEQ_BITS - 1
# MAX_ACK_NUM = 2**ACK_BITS - 1
# MAX_CHECKSUM = 2**CHECKSUM_BITS - 1
# MAX_WINDOW = 2**WINDOW_BITS - 1
# MAX_FLAGS = 2**FLAGS_BITS - 1

MAX_PORT = 0xFFFF
MAX_SEQ_NUM = 0xFFFFFFFF
MAX_ACK_NUM = 0xFFFFFFFF
MAX_FLAGS = 0xFF
MAX_CHECKSUM = 0xFFFFFFFF
MAX_WINDOW = 0xFFFF

MAX_HEADER_SIZE = 20
MAX_PAYLOAD_SIZE = 64
RECV_BUFFER = MAX_HEADER_SIZE + MAX_PAYLOAD_SIZE

class Segment:
    def __init__(self, src_port, dest_port, seq_num=0, ack_num=0, checksum=0, window=0, flags=0, payload=b''):
        '''Creates a segment header'''
        self.src_port = src_port & MAX_PORT
        self.dest_port = dest_port & MAX_PORT
        self.seq_num = seq_num & MAX_SEQ_NUM
        self.ack_num = ack_num & MAX_ACK_NUM
        self.checksum = checksum & MAX_CHECKSUM
        self.window = window & MAX_WINDOW
        self.flags = flags & MAX_FLAGS
        self.payload = payload

    def _pack_header(self):
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
        checksum = 0
        header = self._pack_header()
        for i in range(0, len(header), 2):
            word = (header[i] << 8) + (header[i + 1] if i + 1 < len(header) else 0)
            checksum += word
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
        return ~checksum & 0xFFFF

    def pack(self, include_checksum=True):
        '''Pack a segment into bytes'''

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
        '''unpacks binary data into a segment'''

        header = data[:20]
        payload = data[20:]

        src_port, dest_port, seq_num, ack_num, checksum, window, flags, _ = struct.unpack('!HHIIIHBB', header)

        return cls(
            src_port,
            dest_port,
            seq_num,
            ack_num,
            checksum,
            window,
            flags,
            payload)

    def check_sum(self):
        return self.checksum == self.calculate_checksum()
