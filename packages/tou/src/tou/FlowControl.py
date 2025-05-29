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
        self._retransmit_callback = None  # Initialize retransmit callback

    def _update_activity_time(self):
        """Update the last activity timestamp"""
        self.last_activity = time.time()

    def _check_timeout(self) -> bool:
        """Check if operation has timed out"""
        return time.time() - self.last_activity > self.OPERATION_TIMEOUT

    def set_retransmit_callback(self, callback):
        """Set a callback to be called with (seq_num, data) for each segment to retransmit on timeout."""
        self._retransmit_callback = callback

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

            # VVV CORRECTED ITERATION LOGIC VVV
            # Iterate over the sequence numbers of segments currently in the buffer
            # that are unacknowledged (i.e., seq_num >= self.base).
            # Sort them to typically retransmit older ones first, though any in the
            # timed-out window might need retransmission depending on strategy.

            # The timer signifies that the segment at self.base (oldest unacked) is suspected lost.
            # A simple strategy is to retransmit the segment at self.base if it's still in the buffer.
            # A more aggressive (Go-Back-N like for timeout) strategy might retransmit all from self.base.

            timed_out_segment_found = False
            if self.base in self.buffer:
                data, send_time = self.buffer[self.base]
                # Check if this specific segment's effective send_time warrants a timeout
                # The timer itself is for RETRANSMISSION_TIMEOUT based on when it was started (for self.base)
                print(f"FlowControl: Timeout event. Checking segment at base: Seq={self.base}.")
                # Update its timestamp and mark for retransmission
                self.buffer[self.base] = (data, current_time)
                segments_to_retransmit.append((self.base, data))
                timed_out_segment_found = True
            # else: Segment at self.base was ACKed and removed from buffer,
            # but timer fired. This could happen if ACKs are processed and base advances
            # just before timeout handler runs. Or base was advanced beyond next_seq_num.

            # Optional: More aggressive retransmission (retransmit all outstanding)
            # This is more like what the original range() loop might have intended if seq nums were segment indices
            # If you want to retransmit more than just self.base on a timeout:
            # if not timed_out_segment_found: # Only if self.base wasn't found (shouldn't happen if timer is for self.base)
            #     sorted_buffered_seq_nums = sorted(self.buffer.keys())
            #     for seq_num_key in sorted_buffered_seq_nums:
            #         if seq_num_key >= self.base: # Unacknowledged
            #             data, send_time = self.buffer[seq_num_key]
            #             # No individual timeout check here, as the main timer fired
            #             self.buffer[seq_num_key] = (data, current_time)
            #             segments_to_retransmit.append((seq_num_key, data))
            #             print(f"FlowControl: Adding Seq={seq_num_key} to retransmit list due to general timeout.")

            if hasattr(self, '_retransmit_callback') and self._retransmit_callback is not None and segments_to_retransmit:
                print(f"FlowControl: Retransmitting {len(segments_to_retransmit)} segment(s).")
                for seq_num_to_retransmit, data_to_retransmit in segments_to_retransmit:
                    # seq_num_to_retransmit here should be the *actual large sequence number*
                    self._retransmit_callback(seq_num_to_retransmit, data_to_retransmit)

            # Restart timer if there are still unacknowledged segments
            # self.base should point to the oldest unacknowledged segment's sequence number.
            # self.next_seq_num should point to the sequence number for the *next new segment to send*.
            # This logic for restarting timer is crucial and depends on consistent view of base and next_seq_num

            active_segments_in_buffer = False
            for seq_in_buf in self.buffer.keys():
                if seq_in_buf >= self.base:
                    active_segments_in_buffer = True
                    break

            if active_segments_in_buffer: # If there are segments >= base in buffer
                self.start_timer() # Restart timer for the (potentially new) self.base
            else:
                self.stop_timer() # No unacknowledged data left that we know of

            # return segments_to_retransmit # Not used by threading.Timer

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