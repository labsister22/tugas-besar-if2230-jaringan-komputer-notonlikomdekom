import threading
import time
from typing import Optional, List, Dict, Tuple
from tou import Segments

class TimeoutError(Exception):
    """Exception raised when an operation times out"""
    pass

class FlowControl:
    DEFAULT_WINDOW_SIZE = 4
    OPERATION_TIMEOUT = 5.0  # 5 seconds for send/receive operations
    RETRANSMISSION_TIMEOUT = 1.0  # 1 second for retransmission

    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE):
        self.window_size = window_size
        self.base = 0
        self.next_seq_num = 0
        self.buffer: Dict[int, Tuple[bytes, float]] = {}  # (data, timestamp)
        self.timer = None
        self.lock = threading.Lock()
        self.received_segments: Dict[int, bytes] = {}
        self.expected_seq_num = 0
        self.last_activity = time.time()

    def _update_activity_time(self):
        """Update the last activity timestamp"""
        self.last_activity = time.time()

    def _check_timeout(self) -> bool:
        """Check if operation has timed out"""
        return time.time() - self.last_activity > self.OPERATION_TIMEOUT

    def start_timer(self):
        """Start the retransmission timer"""
        if self.timer is not None:
            self.timer.cancel()
        self.timer = threading.Timer(self.RETRANSMISSION_TIMEOUT, self.handle_timeout)
        self.timer.daemon = True
        self.timer.start()

    def stop_timer(self):
        """Stop the retransmission timer"""
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def handle_timeout(self):
        """Handle retransmission timeout"""
        with self.lock:
            current_time = time.time()
            segments_to_retransmit = []
            
            # Check each segment in the window for timeout
            for seq_num in range(self.base, self.next_seq_num):
                if seq_num in self.buffer:
                    data, send_time = self.buffer[seq_num]
                    if current_time - send_time > self.RETRANSMISSION_TIMEOUT:
                        # Update timestamp and mark for retransmission
                        self.buffer[seq_num] = (data, current_time)
                        segments_to_retransmit.append((seq_num, data))
            
            # Restart timer if there are unacknowledged segments
            if segments_to_retransmit:
                self.start_timer()
            
            return segments_to_retransmit

    def can_send(self) -> bool:
        """Check if we can send more segments"""
        return self.next_seq_num < self.base + self.window_size

    def send(self, data: bytes, sequence_num: Optional[int] = None) -> Optional[bytes]:
        """Send data with timeout handling"""
        start_time = time.time()
        
        while True:
            with self.lock:
                if self._check_timeout():
                    raise TimeoutError("Send operation timed out")

                if not self.can_send():
                    time.sleep(0.1)
                    continue

                seq_num = sequence_num if sequence_num is not None else self.next_seq_num
                self.buffer[seq_num] = (data, time.time())
                
                if seq_num == self.base:
                    self.start_timer()

                self.next_seq_num += 1
                self._update_activity_time()
                return data

            if time.time() - start_time > self.OPERATION_TIMEOUT:
                raise TimeoutError("Send operation timed out")

    def receive_ack(self, ack_num: int) -> List[int]:
        """Handle received ACK with timeout"""
        with self.lock:
            if self._check_timeout():
                raise TimeoutError("ACK handling timed out")

            if ack_num >= self.base:
                acked_segments = []
                for seq_num in range(self.base, ack_num + 1):
                    if seq_num in self.buffer:
                        del self.buffer[seq_num]
                        acked_segments.append(seq_num)
                self.base = ack_num + 1

                if self.base == self.next_seq_num:
                    self.stop_timer()
                else:
                    self.start_timer()

                self._update_activity_time()
                return acked_segments
            return []

    def receive(self, data: bytes, sequence_num: int) -> Optional[bytes]:
        """Receive data with timeout handling"""
        start_time = time.time()
        
        while True:
            if time.time() - start_time > self.OPERATION_TIMEOUT:
                raise TimeoutError("Receive operation timed out")

            if sequence_num == self.expected_seq_num:
                self.received_segments[sequence_num] = data
                received_data = None

                # Process consecutive segments
                while self.expected_seq_num in self.received_segments:
                    received_data = self.received_segments.pop(self.expected_seq_num)
                    self.expected_seq_num += 1

                self._update_activity_time()
                return received_data

            elif sequence_num < self.expected_seq_num:
                # Duplicate segment, acknowledge but ignore
                self._update_activity_time()
                return None
            else:
                # Future segment, buffer it if within window
                if sequence_num < self.expected_seq_num + self.window_size:
                    self.received_segments[sequence_num] = data
                self._update_activity_time()
                return None

    def is_window_full(self) -> bool:
        """Check if the sending window is full"""
        return self.next_seq_num >= self.base + self.window_size

    def get_window_size(self) -> int:
        """Get effective window size"""
        return min(self.window_size, len(self.buffer))

    def adjust_window_size(self, new_size: int):
        """Adjust window size with bounds checking"""
        with self.lock:
            self.window_size = max(1, min(new_size, Segments.window_max))

    def reset(self):
        """Reset flow control state"""
        with self.lock:
            self.stop_timer()
            self.base = 0
            self.next_seq_num = 0
            self.buffer.clear()
            self.received_segments.clear()
            self.expected_seq_num = 0
            self._update_activity_time()