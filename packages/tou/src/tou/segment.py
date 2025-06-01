import struct
import random

class SegmentHeader:
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

    SIZE = 20

    SYN_FLAG = 1
    ACK_FLAG = 2
    FIN_FLAG = 4

    MAX_SRC_PORT = 0xFFFF
    MAX_DST_PORT = 0xFFFF
    MAX_SEQ_NUM = 0xFFFFFFFF
    MAX_ACK_NUM = 0xFFFFFFFF
    MAX_FLAGS = 0xFFFF
    MAX_CHECKSUM = 0xFFFF
    MAX_WINDOW = 0xFFFF
    MAX_SIZE = 0xFFFF

    def __init__(self, src_port: int, dst_port: int, seq_num: int, ack_num: int, flags: int, checksum: int, window: int, size: int):
        '''Creates a segment header'''

        if src_port > SegmentHeader.MAX_SRC_PORT:
            raise ValueError(f"Source port too large! ({src_port})")
        
        if dst_port > SegmentHeader.MAX_DST_PORT:
            raise ValueError(f"Destination port too large! ({src_port})")
        
        if seq_num > SegmentHeader.MAX_SEQ_NUM:
            raise ValueError(f"Sequence number too large! ({src_port})")
        
        if ack_num > SegmentHeader.MAX_ACK_NUM:
            raise ValueError(f"ACK number too large! ({src_port})")
        
        if flags > SegmentHeader.MAX_FLAGS:
            raise ValueError(f"Flag size too large! ({src_port})")
        
        if checksum > SegmentHeader.MAX_CHECKSUM:
            raise ValueError(f"Checksum size too large! ({src_port})")
        
        if window > SegmentHeader.MAX_WINDOW:
            raise ValueError(f"Window size too large! ({src_port})")
        
        if size > SegmentHeader.MAX_SIZE:
            raise ValueError(f"Payload size too large! ({src_port})")
        
        self.src_port = src_port
        self.dst_port = dst_port
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.flags = flags
        self.checksum = checksum
        self.window = window
        self.size = size
    
    def pack(self) -> bytes:
        '''Packs segment header into bytes'''

        return struct.pack("!HHIIHHHH", self.src_port, self.dst_port, self.seq_num, self.ack_num, self.flags, self.checksum, self.window, self.size)
    
    @staticmethod
    def unpack(bytes: bytes):
        '''Unpacks binary data into a segment header'''

        if len(bytes) < 20:
            raise ValueError("Header too small")
        
        try:
            src_port, dst_port, seq_num, ack_num, flags, checksum, window, size = struct.unpack("!HHIIHHHH", bytes)
        except struct.error as e:
            raise ValueError(f"Invalid header format: {e}")
        
        return SegmentHeader(src_port, dst_port, seq_num, ack_num, flags, checksum, window, size)


class Segment:
    '''
    Single TCP over UDP segment

    Format:
    - Header (20 bytes)
    - Payload (Up to 64 bytes)
    '''

    MAX_SIZE = 64

    def __init__(self, src_port: int, dst_port: int, seq_num: int, ack_num: int, flags: int, window: int, payload: bytes):
        '''Creates a segment from given header parameters and payload (checksum is 0 until packed)'''

        self.header = SegmentHeader(src_port, dst_port, seq_num, ack_num, flags, 0, window, len(payload))
        self.payload = payload
    
    def pack(self) -> bytes:
        '''Pack a segment into bytes'''

        # Reconstruct header with correct checksum
        checksum = Segment.calculate_checksum(self.header.pack() + self.payload)
        header = SegmentHeader(
            self.header.src_port,
            self.header.dst_port,
            self.header.seq_num,
            self.header.ack_num,
            self.header.flags,
            checksum,
            self.header.window,
            self.header.size
        )

        return header.pack() + self.payload
    
    @staticmethod
    def unpack(bytes: bytes):
        '''unpacks binary data into a segment'''

        header = SegmentHeader.unpack(bytes[:SegmentHeader.SIZE])

        if len(bytes) < SegmentHeader.SIZE + header.size:
            raise ValueError("Payload too small")

        payload = bytes[SegmentHeader.SIZE:(SegmentHeader.SIZE + header.size)]

        original_header = SegmentHeader(
            header.src_port,
            header.dst_port,
            header.seq_num,
            header.ack_num,
            header.flags,
            0,
            header.window,
            header.size
        )

        if Segment.calculate_checksum(original_header.pack() + payload) != header.checksum:
            raise ValueError("Checksum invalid")

        return Segment(header.src_port, header.dst_port, header.seq_num, header.ack_num, header.flags, header.window, payload)
    
    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """Calculate CRC-16-CCITT checksum for data integrity verification.
        Polynomial: x^16 + x^12 + x^5 + 1 (0x1021)
        Initial value: 0xFFFF
        """
        polynom = 0x1021  # CRC-16-CCITT polynomial
        crc = 0xFFFF      # Initial value

        for byte in data:
            # XOR the byte with the high byte of current CRC
            crc ^= (byte << 8)
            # Process each bit
            for _ in range(8):
                # If MSB is 1, shift and XOR with polynomial
                if crc & 0x8000:
                    crc = ((crc << 1) ^ polynom) & 0xFFFF
                # If MSB is 0, just shift
                else:
                    crc = (crc << 1) & 0xFFFF

        return crc
    
    @staticmethod
    def generate_random_syn() -> int:
        '''generates a random valid sequence number'''
        
        # Limit to only half because wrap aroud sequence number is not supported
        return random.randint(0, SegmentHeader.MAX_SEQ_NUM // 2)