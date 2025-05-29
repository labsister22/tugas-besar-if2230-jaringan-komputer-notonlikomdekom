import struct

class Segments:
    """Transport-layer Segments with integrity verification"""

    MAX_PAYLOAD_SIZE = 64  # Maximum payload size in bytes
    # Header format for struct packing
    # Format: source_port(H) dest_port(H) seq_num(Q) ack_num(Q) flags(B) window(H) checksum(H)
    HEADER_FORMAT = '!HHQQBHH'  # Network byte order (big-endian)
    # MAX_HEADER_SIZE = 18  # Maximum header size in bytes
    MAX_HEADER_SIZE = struct.calcsize(HEADER_FORMAT) # Should be 25 bytes

    # Field sizes and maximum values
    port = 16
    port_max = 2**port - 1

    seq_num = 64
    seq_max = 2**seq_num - 1
    ack_num = 64
    ack_max = 2**ack_num - 1

    # Control flags
    SYN_flag = 0b00000001  # 1 << 0
    ACK_flag = 0b00000010  # 1 << 1
    FIN_flag = 0b00000100  # 1 << 2
    flags_num = 8
    max_flags = 2**flags_num - 1

    # Flow control window
    window = 16
    window_max = 2**window - 1

    # Checksum for integrity verification
    checksum = 16
    checksum_max = 2**checksum - 1


    def __init__(self, source_port: int, dest_port: int, seq_num: int = 0,
                 ack_num: int = 0, flags: int = 0, window: int = 0,
                 checksum: int = 0, payload: bytes = b''):
        """Initialize a new segment with integrity checking capability"""
        # Validate and set port numbers
        self.source_port = source_port & self.port_max
        self.dest_port = dest_port & self.port_max

        # Sequence and acknowledgment numbers
        self.seq_num = seq_num & self.seq_max
        self.ack_num = ack_num & self.ack_max

        # Control flags and flow control
        self.flags = flags & self.max_flags
        self.window = window & self.window_max

        # Integrity verification
        self.checksum = checksum & self.checksum_max
        self.payload = payload

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

    def pack(self) -> bytes:
        """Pack the segment into bytes with integrity verification
        1. Create header with zero checksum
        2. Calculate checksum over the entire segment
        3. Create final header with calculated checksum
        4. Return complete segment
        """
        # Create initial header with zero checksum for calculation
        header = struct.pack(
            self.HEADER_FORMAT,
            self.source_port,
            self.dest_port,
            self.seq_num,
            self.ack_num,
            self.flags,
            self.window,
            0  # Initial zero checksum
        )

        # Calculate checksum over the entire segment
        self.checksum = self.calculate_checksum(header + self.payload)

        # Create final header with calculated checksum
        header = struct.pack(
            self.HEADER_FORMAT,
            self.source_port,
            self.dest_port,
            self.seq_num,
            self.ack_num,
            self.flags,
            self.window,
            self.checksum
        )

        # Return complete segment
        return header + self.payload

    @classmethod
    def unpack(cls, data):
        # Verify minimum data length
        header_size = struct.calcsize(cls.HEADER_FORMAT)
        if len(data) < header_size:
            raise ValueError("Data too short to contain a valid header")

        # Split header and payload
        header = data[:header_size]
        payload = data[header_size:]

        # Unpack header fields
        try:
            source_port, dest_port, seq_num, ack_num, flags, window, checksum = \
                struct.unpack(cls.HEADER_FORMAT, header)
        except struct.error as e:
            raise ValueError(f"Invalid header format: {e}")

        # Create segment instance
        segments = cls(
            source_port=source_port,
            dest_port=dest_port,
            seq_num=seq_num,
            ack_num=ack_num,
            flags=flags,
            window=window,
            payload=payload
        )
        segments.checksum = checksum  # Store received checksum

        # Verify data integrity
        # 1. Save original checksum
        original_checksum = segments.checksum
        # 2. Zero out checksum for calculation
        segments.checksum = 0
        # 3. Recalculate checksum on received data
        verification_header = struct.pack(
            cls.HEADER_FORMAT,
            segments.source_port,
            segments.dest_port,
            segments.seq_num,
            segments.ack_num,
            segments.flags,
            segments.window,
            0  # Zero checksum for calculation
        )
        calculated_checksum = cls.calculate_checksum(verification_header + segments.payload)

        # 4. Compare checksums
        if original_checksum != calculated_checksum:
            raise ValueError("Checksum verification failed: data integrity compromised")

        # 5. Restore original checksum
        segments.checksum = original_checksum
        return segments

