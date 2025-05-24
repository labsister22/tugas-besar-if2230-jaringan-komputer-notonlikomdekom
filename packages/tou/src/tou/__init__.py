import socket
import struct
import random

HEADER_FORMAT = '!HHIIBBH'  # src_port, dst_port, seq, ack, flags, reserved, checksum
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_SIZE = 64

FLAG_SYN = 0b001
FLAG_ACK = 0b010
FLAG_FIN = 0b100

class BetterUDPSocket:
    def __init__(self, udp_socket=None):
        if udp_socket is not None:
            self.sock = udp_socket
        else:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.connected_addr = None
        self.is_server = False
        self.seq = random.randint(0, 2**32-1)
        self.ack = 0
        self.src_port = random.randint(1024, 65535)
        self.dst_port = 0

    def _checksum(self, data: bytes) -> int:
        # Improved checksum: one's complement sum of 16-bit words
        if len(data) % 2 == 1:
            data += b'\x00'
        s = 0
        for i in range(0, len(data), 2):
            w = (data[i] << 8) + data[i+1]
            s = s + w
            s = (s & 0xffff) + (s >> 16)
        return ~s & 0xffff

    def _pack_header(self, flags, payload, seq=None, ack=None):
        seq = self.seq if seq is None else seq
        ack = self.ack if ack is None else ack
        # Hitung checksum untuk header+payload (sementara checksum=0 dulu)
        temp_header = struct.pack(
            HEADER_FORMAT,
            self.src_port,
            self.dst_port,
            seq,
            ack,
            flags,
            0,  # reserved
            0   # checksum sementara
        )
        checksum = self._checksum(temp_header + payload)
        return struct.pack(
            HEADER_FORMAT,
            self.src_port,
            self.dst_port,
            seq,
            ack,
            flags,
            0,  # reserved
            checksum
        )

    def _unpack_header(self, header_bytes):
        src_port, dst_port, seq, ack, flags, reserved, checksum = struct.unpack(HEADER_FORMAT, header_bytes)
        return {
            'src_port': src_port,
            'dst_port': dst_port,
            'seq': seq,
            'ack': ack,
            'flags': flags,
            'checksum': checksum
        }

    def send(self, data, window_size=4, timeout=0.5):
        if self.connected_addr is None:
            raise Exception("Socket not connected")
        # Segment data
        segments = []
        offset = 0
        seq = self.seq
        while offset < len(data):
            payload = data[offset:offset+MAX_PAYLOAD_SIZE]
            is_last = offset + MAX_PAYLOAD_SIZE >= len(data)
            flags = 0
            if is_last:
                flags |= FLAG_FIN
            header = self._pack_header(flags, payload, seq=seq)
            segments.append((header + payload, seq, flags))
            seq += len(payload)
            offset += MAX_PAYLOAD_SIZE
        base = 0
        next_seq = 0
        acked = [False] * len(segments)
        while base < len(segments):
            # Kirim window
            while next_seq < base + window_size and next_seq < len(segments):
                self.sock.sendto(segments[next_seq][0], self.connected_addr)
                next_seq += 1
            # Tunggu ACK
            self.sock.settimeout(timeout)
            try:
                while True:
                    # ack_data, _ = self.sock.recvfrom(HEADER_SIZE)
                    ack_data, _ = self.sock.recvfrom(2048)  # large enough to fit full packet
                    if len(ack_data) < HEADER_SIZE:
                        continue
                    # ack_header = self._unpack_header(ack_data)
                    ack_header = self._unpack_header(ack_data[:HEADER_SIZE])
                    if not (ack_header['flags'] & FLAG_ACK):
                        continue
                    if ack_header['flags'] & FLAG_ACK:
                        # Cari segmen yang di-ACK
                        for i, (_, seg_seq, _) in enumerate(segments):
                            if ack_header['ack'] == seg_seq + MAX_PAYLOAD_SIZE or (segments[i][2] & FLAG_FIN and ack_header['ack'] == seg_seq):
                                acked[i] = True
                        # Geser base
                        while base < len(segments) and acked[base]:
                            base += 1
            except socket.timeout:
                # Retransmit window
                next_seq = base
        self.seq = seq
        # Tunggu FIN-ACK jika segmen terakhir FIN
        if segments and (segments[-1][2] & FLAG_FIN):
            while True:
                # finack_data, _ = self.sock.recvfrom(HEADER_SIZE)
                finack_data, _ = self.sock.recvfrom(2048)  # large enough to fit full packet
                if len(finack_data) < HEADER_SIZE:
                    continue
                finack_header = self._unpack_header(finack_data)
                if finack_header['flags'] & FLAG_FIN and finack_header['flags'] & FLAG_ACK:
                    break

    def receive(self, expected_len=None):
        # Sliding window receive
        received = {}
        expected_seq = None
        finished = False
        result = b''
        while not finished:
            segment, addr = self.sock.recvfrom(HEADER_SIZE + MAX_PAYLOAD_SIZE)
            if len(segment) < HEADER_SIZE:
                continue
            header = segment[:HEADER_SIZE]
            payload = segment[HEADER_SIZE:]
            header_info = self._unpack_header(header)
            # Check checksum (header+payload)
            temp_header = struct.pack(
                HEADER_FORMAT,
                header_info['src_port'],
                header_info['dst_port'],
                header_info['seq'],
                header_info['ack'],
                header_info['flags'],
                0,  # reserved
                0   # checksum sementara
            )
            calc_checksum = self._checksum(temp_header + payload)
            if header_info['checksum'] != calc_checksum:
                continue  # drop corrupt
            seq = header_info['seq']
            if expected_seq is None:
                expected_seq = seq
            if seq == expected_seq:
                result += payload
                expected_seq += len(payload)
                # Kirim ACK
                ack_header = self._pack_header(FLAG_ACK, b'', seq=self.seq, ack=expected_seq)
                self.sock.sendto(ack_header, addr)
                if header_info['flags'] & FLAG_FIN:
                    # Kirim FIN-ACK
                    finack_header = self._pack_header(FLAG_FIN | FLAG_ACK, b'', seq=self.seq, ack=expected_seq)
                    self.sock.sendto(finack_header, addr)
                    finished = True
            else:
                # Out of order, kirim ACK untuk expected_seq
                ack_header = self._pack_header(FLAG_ACK, b'', seq=self.seq, ack=expected_seq)
                self.sock.sendto(ack_header, addr)
        self.connected_addr = addr
        return result, addr

    def connect(self, ip_address, port):
        # 3-way handshake: send SYN, wait SYN-ACK, send ACK
        server_addr = (ip_address, port)
        self.dst_port = port
        self.seq = random.randint(0, 2**32-1)  # random initial sequence number
        syn_header = self._pack_header(FLAG_SYN, b'', seq=self.seq, ack=0)
        self.sock.sendto(syn_header, server_addr)
        # Wait for SYN-ACK
        data, addr = self.sock.recvfrom(HEADER_SIZE)
        header_info = self._unpack_header(data)
        if header_info['flags'] & FLAG_SYN and header_info['flags'] & FLAG_ACK:
            # Save server's initial sequence number
            server_seq = header_info['seq']
            self.ack = server_seq + 1
            self.seq += 1  # our next seq
            # Send ACK
            ack_header = self._pack_header(FLAG_ACK, b'', seq=self.seq, ack=self.ack)
            self.sock.sendto(ack_header, server_addr)
            self.connected_addr = server_addr
        else:
            raise Exception("Handshake failed")

    def listen(self):
        self.is_server = True
        while True:
            data, addr = self.sock.recvfrom(HEADER_SIZE)
            if len(data) < HEADER_SIZE:
                print("Received malformed header, ignoring")
                continue
            header_info = self._unpack_header(data)
            if header_info['flags'] & FLAG_SYN:
                self.dst_port = header_info['src_port']
                client_seq = header_info['seq']
                self.ack = client_seq + 1
                self.seq = random.randint(0, 2**32-1)
                syn_ack_header = self._pack_header(FLAG_SYN | FLAG_ACK, b'', seq=self.seq, ack=self.ack)
                self.sock.sendto(syn_ack_header, addr)
                # Wait for ACK
                data2, addr2 = self.sock.recvfrom(HEADER_SIZE)
                if len(data2) < HEADER_SIZE:
                    print("Received malformed ACK, ignoring")
                    continue
                header_info2 = self._unpack_header(data2)
                if header_info2['flags'] & FLAG_ACK and addr == addr2 and header_info2['ack'] == self.seq + 1:
                    self.connected_addr = addr
                    break
        # self.is_server = True
        # while True:
        #     data, addr = self.sock.recvfrom(HEADER_SIZE)
        #     header_info = self._unpack_header(data)
        #     if header_info['flags'] & FLAG_SYN:
        #         self.dst_port = header_info['src_port']
        #         client_seq = header_info['seq']
        #         self.ack = client_seq + 1
        #         self.seq = random.randint(0, 2**32-1)  # random initial sequence number for server
        #         # Send SYN+ACK
        #         syn_ack_header = self._pack_header(FLAG_SYN | FLAG_ACK, b'', seq=self.seq, ack=self.ack)
        #         self.sock.sendto(syn_ack_header, addr)
        #         # Wait for ACK
        #         data2, addr2 = self.sock.recvfrom(HEADER_SIZE)
        #         header_info2 = self._unpack_header(data2)
        #         if header_info2['flags'] & FLAG_ACK and addr == addr2 and header_info2['ack'] == self.seq + 1:
        #             self.connected_addr = addr
        #             break

    # Add other methods as needed

def main() -> None:
    print("Hello from tou!")
