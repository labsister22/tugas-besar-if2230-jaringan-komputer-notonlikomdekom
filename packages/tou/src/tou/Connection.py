import socket
import threading
import time
import random
from enum import Enum, auto
from tou.Segments import Segments
from tou.FlowControl import FlowControl

class ConnectionState(Enum):
    """Connection states for the TOU protocol"""
    CLOSED = auto()
    LISTEN = auto()
    SYN_SENT = auto()
    SYN_RECEIVED = auto()
    ESTABLISHED = auto()
    FIN_WAIT = auto()
    CLOSE_WAIT = auto()
    CLOSING = auto()
    LAST_ACK = auto()
    TIME_WAIT = auto()

class Connection:
    def __init__(self, local_addr: tuple[str, int], socket: socket.socket):
        self.local_addr = local_addr
        self.remote_addr = None
        self.socket = socket
        self.state = ConnectionState.CLOSED
        self.local_seq_num = 0
        self.remote_seq_num = 0
        self.local_window = Segments.window_max
        self.remote_window = 0
        self.flow_control = FlowControl()
        self.send_buffer = []
        self.receive_buffer = []
        self.send_thread = None
        self.receive_thread = None
        self.running = False
        
    def listen(self) -> None:
        """Start listening for incoming connections"""
        if self.state != ConnectionState.CLOSED:
            raise RuntimeError("Connection must be closed before listening")
            
        self.state = ConnectionState.LISTEN
        
    def accept(self) -> 'Connection':
        """Accept an incoming connection request"""
        if self.state != ConnectionState.LISTEN:
            raise RuntimeError("Connection must be listening to accept connections")
            
        # Wait for SYN
        while True:
            try:
                data, addr = self.socket.recvfrom(Segments.MAX_HEADER_SIZE + Segments.MAX_PAYLOAD_SIZE)
            except BlockingIOError:
                time.sleep(0.01)
                continue
            try:
                segment = Segments.unpack(data)
                if segment.flags & Segments.SYN_flag:
                    break
            except ValueError:
                continue  # Ignore invalid Segments
                
        self.remote_addr = addr
        self.remote_seq_num = segment.seq_num
        self.local_seq_num = random.randint(0, Segments.seq_max)
        
        # Send SYN-ACK
        syn_ack = Segments(
            source_port=self.local_addr[1],
            dest_port=self.remote_addr[1],
            seq_num=self.local_seq_num,
            ack_num=self.remote_seq_num + 1,
            flags=Segments.SYN_flag | Segments.ACK_flag,
            window=self.local_window
        )
        self.socket.sendto(syn_ack.pack(), self.remote_addr)
        self.state = ConnectionState.SYN_RECEIVED
        
        # Wait for ACK
        while True:
            try:
                data, addr = self.socket.recvfrom(Segments.MAX_HEADER_SIZE + Segments.MAX_PAYLOAD_SIZE)
            except BlockingIOError:
                time.sleep(0.01)
                continue
            if addr != self.remote_addr:
                continue
            try:
                segment = Segments.unpack(data)
                if segment.flags & Segments.ACK_flag and segment.ack_num == self.local_seq_num + 1:
                    self.remote_window = segment.window
                    self.state = ConnectionState.ESTABLISHED
                    break
            except ValueError:
                continue  # Ignore invalid Segments
                
        self.start_background_threads()
        return self
        
    def connect(self, remote_addr: tuple[str, int]) -> None:
        """Initiate connection to remote address"""
        if self.state != ConnectionState.CLOSED:
            raise RuntimeError("Connection must be closed before connecting")
            
        self.remote_addr = remote_addr
        self.local_seq_num = random.randint(0, Segments.seq_max)
        
        # Send SYN
        syn = Segments(
            source_port=self.local_addr[1],
            dest_port=self.remote_addr[1],
            seq_num=self.local_seq_num,
            flags=Segments.SYN_flag,
            window=self.local_window
        )
        self.socket.sendto(syn.pack(), self.remote_addr)
        self.state = ConnectionState.SYN_SENT
        
        # Wait for SYN-ACK
        while True:
            try:
                data, addr = self.socket.recvfrom(Segments.MAX_HEADER_SIZE + Segments.MAX_PAYLOAD_SIZE)
            except BlockingIOError:
                time.sleep(0.01)
                continue
            if addr != self.remote_addr:
                continue
            try:
                segment = Segments.unpack(data)
                if (segment.flags & (Segments.SYN_flag | Segments.ACK_flag) and 
                    segment.ack_num == self.local_seq_num + 1):
                    self.remote_seq_num = segment.seq_num
                    self.remote_window = segment.window
                    break
            except ValueError:
                continue  # Ignore invalid Segments
                
        # Send ACK
        ack = Segments(
            source_port=self.local_addr[1],
            dest_port=self.remote_addr[1],
            seq_num=self.local_seq_num + 1,
            ack_num=self.remote_seq_num + 1,
            flags=Segments.ACK_flag,
            window=self.local_window
        )
        self.socket.sendto(ack.pack(), self.remote_addr)
        self.state = ConnectionState.ESTABLISHED
        self.start_background_threads()
        
    def start_background_threads(self):
        """Start background threads for sending and receiving"""
        self.running = True
        self.send_thread = threading.Thread(target=self._send_loop)
        self.receive_thread = threading.Thread(target=self._receive_loop)
        self.send_thread.daemon = True
        self.receive_thread.daemon = True
        self.send_thread.start()
        self.receive_thread.start()
        
    def stop_background_threads(self):
        """Stop background threads"""
        self.running = False
        if self.send_thread:
            self.send_thread.join()
        if self.receive_thread:
            self.receive_thread.join()
            
    def _send_loop(self):
        """Background thread for sending data"""
        while self.running:
            if self.send_buffer and self.flow_control.can_send():
                data = self.send_buffer[0]
                Segments = Segments(
                    source_port=self.local_addr[1],
                    dest_port=self.remote_addr[1],
                    seq_num=self.local_seq_num,
                    flags=Segments.ACK_flag,
                    window=self.flow_control.get_window_size(),
                    payload=data
                )
                
                if self.flow_control.send(Segments.pack(), self.local_seq_num):
                    self.local_seq_num += len(data)
                    self.send_buffer.pop(0)
                    
            time.sleep(0.01)  # Small delay to prevent CPU hogging
            
    def _receive_loop(self):
        """Background thread for receiving data"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(Segments.MAX_HEADER_SIZE + Segments.MAX_PAYLOAD_SIZE)
                if addr != self.remote_addr:
                    continue
                    
                Segments = Segments.unpack(data)
                
                # Handle data Segments
                if Segments.payload:
                    if received_data := self.flow_control.receive(Segments.payload, Segments.seq_num):
                        self.receive_buffer.append(received_data)
                        
                        # Send ACK
                        ack = Segments(
                            source_port=self.local_addr[1],
                            dest_port=self.remote_addr[1],
                            seq_num=self.local_seq_num,
                            ack_num=Segments.seq_num + len(Segments.payload),
                            flags=Segments.ACK_flag,
                            window=self.flow_control.get_window_size()
                        )
                        self.socket.sendto(ack.pack(), self.remote_addr)
                        
                # Handle ACKs
                if Segments.flags & Segments.ACK_flag:
                    self.flow_control.receive_ack(Segments.ack_num)
                    
                # Handle FIN
                if Segments.flags & Segments.FIN_flag:
                    self._handle_fin(Segments)
                    
            except BlockingIOError:
                time.sleep(0.01)
                continue
            except Exception as e:
                print(f"Error in receive loop: {e}")
                continue
                
    def _handle_fin(self, Segments: Segments):
        """Handle received FIN Segments"""
        if self.state == ConnectionState.ESTABLISHED:
            # Send FIN-ACK
            fin_ack = Segments(
                source_port=self.local_addr[1],
                dest_port=self.remote_addr[1],
                seq_num=self.local_seq_num,
                ack_num=Segments.seq_num + 1,
                flags=Segments.FIN_flag | Segments.ACK_flag,
                window=self.flow_control.get_window_size()
            )
            self.socket.sendto(fin_ack.pack(), self.remote_addr)
            self.state = ConnectionState.CLOSE_WAIT
            
    def send(self, data: bytes):
        """Send data using flow control"""
        if self.state != ConnectionState.ESTABLISHED:
            raise RuntimeError("Connection must be established to send data")
            
        # Split data into Segments
        Segments = Segments.split_data(data)
        self.send_buffer.extend(Segments)
        
    def receive(self, max_size: int = 4096) -> bytes:
        """Receive data from the connection"""
        if self.state != ConnectionState.ESTABLISHED:
            raise RuntimeError("Connection must be established to receive data")
            
        while not self.receive_buffer and self.running:
            time.sleep(0.01)
            
        if self.receive_buffer:
            return self.receive_buffer.pop(0)
        return b''
        
    def close(self) -> None:
        """Close the connection with graceful shutdown"""
        if self.state not in (ConnectionState.ESTABLISHED, ConnectionState.CLOSE_WAIT):
            raise RuntimeError("Connection must be established or in close wait to close")
            
        # Wait for send buffer to be empty
        while self.send_buffer:
            time.sleep(0.1)
            
        # Send FIN
        fin = Segments(
            source_port=self.local_addr[1],
            dest_port=self.remote_addr[1],
            seq_num=self.local_seq_num,
            flags=Segments.FIN_flag,
            window=self.flow_control.get_window_size()
        )
        self.socket.sendto(fin.pack(), self.remote_addr)
        
        if self.state == ConnectionState.ESTABLISHED:
            self.state = ConnectionState.FIN_WAIT
            
            # Wait for FIN-ACK
            timeout = time.time() + 10  # 10 second timeout
            while self.state == ConnectionState.FIN_WAIT and time.time() < timeout:
                time.sleep(0.1)
                
        self.stop_background_threads()
        self.flow_control.reset()
        self.state = ConnectionState.CLOSED