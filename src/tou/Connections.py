from tou.FlowControl import *
from tou.Segment import Segment, SYN, ACK, RECV_BUFFER

import socket
import random
import select
import time

class BetterUDPSocket:
    def __init__(self, udp_socket=None):
        """Initialize the TCP-over-UDP Socket."""
        self.socket = udp_socket or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.remote_addr = None
        self.src_port = None
        self.dest_port = None
        self.client_name = None

        self.time_out = None

    def send(self, data):
        if not self.remote_addr:
            raise RuntimeError("Socket not connected")
        sender = SlidingWindowSender(self.socket, self.remote_addr)
        sender.send_data(data, self.src_port, self.dest_port)

    def recv(self):
        receiver = SlidingWindowReceiver(self.socket)
        data = receiver.recv(self.src_port, self.dest_port)
        return data

    def connect(self, server_addr, src_port, dest_port):
        """Perform a three-way handshake to establish a connection."""
        initial_seq = random.randint(0, 2**32 - 1)
        syn_seg = Segment(
            src_port,
            dest_port,
            seq_num=initial_seq,
            flags=SYN
            )

        total_timeout = 30
        retransmit_interval = 0.1
        start_time = time.time()
        last_sent = 0

        while True:
            current_time = time.time()

            if current_time - last_sent >= retransmit_interval:
                self.socket.sendto(syn_seg.pack(), server_addr)
                last_sent = current_time

            selectable_sockets, _, _ = select.select([self.socket], [], [], 0.1)
            if selectable_sockets[0]:
                data, addr = self.socket.recvfrom(RECV_BUFFER)
                if addr != server_addr:
                    continue

                synack_seg = Segment.unpack(data)
                if (synack_seg.flags & SYN) and (synack_seg.flags & ACK):
                    if synack_seg.ack_num == initial_seq + 1:
                        y = synack_seg.seq_num
                        break

            if current_time - start_time > total_timeout:
                raise TimeoutError("Handshake timeout: No valid SYN+ACK")

        ack_seg = Segment(
            src_port,
            dest_port,
            seq_num=initial_seq+1,
            ack_num=y+1,
            flags=ACK
            )
        self.socket.sendto(ack_seg.pack(), server_addr)

        self.remote_addr = server_addr
        self.src_port = src_port
        self.dest_port = dest_port
        print(f"[CLIENT] Handshake successful with ({server_addr}:{dest_port})")

        return initial_seq


    def listen(self, sock, port, client_addr, syn_seg, result_queue):
        self.src_port = port
        total_timeout = 30
        retransmit_interval = 0.1

        client_isn = syn_seg.seq_num
        y = random.randint(0, 2**32 - 1)
        synack_seg = Segment(
            syn_seg.dest_port, syn_seg.src_port,
            seq_num=y, ack_num=client_isn + 1,
            flags=SYN | ACK
        )

        start_ack_time = time.time()
        last_sent = 0

        while True:
            current_time = time.time()

            # retransmit SYN-ACK if interval passed
            if current_time - last_sent >= retransmit_interval:
                sock.sendto(synack_seg.pack(), client_addr)
                last_sent = current_time

            ready = select.select([sock], [], [], 0.1)
            if ready[0]:
                data, addr = sock.recvfrom(RECV_BUFFER)
                if addr != client_addr:
                    continue

                ack_seg = Segment.unpack(data)
                if (ack_seg.flags & ACK) and ack_seg.ack_num == y + 1:
                    self.remote_addr = client_addr
                    self.dest_port = syn_seg.src_port

                    print(f"[BetterUDPSocket] Handshake successful with {client_addr}!")
                    result_queue.put(client_isn)
                    return

            if current_time - start_ack_time > total_timeout:
                raise TimeoutError("Handshake failed: waiting for ACK")

    def close(self):
        """Close the socket."""
        self.is_closed = True
        self.socket.close()

    def bind(self, address):
        """Bind the socket to a local address."""
        self.socket.bind(address)
        self.src_port = address[1]