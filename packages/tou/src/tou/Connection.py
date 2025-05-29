# Make sure these imports are present
import socket
import threading
import time
import random
from typing import Optional
from enum import Enum, auto
from tou.Segments import Segments #
from tou.FlowControl import FlowControl #

class ConnectionState(Enum):
    """Connection states for the TOU protocol"""
    CLOSED = auto()
    LISTEN = auto() # Kept for conceptual completeness, less used by server directly
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
        self.state = ConnectionState.CLOSED # Ensure ConnectionState is defined/imported
        self.local_seq_num = 0
        self.remote_seq_num = 0
        self.local_window = Segments.window_max
        self.remote_window = 0
        self.flow_control = FlowControl() #

        # VVV THIS IS THE CRUCIAL FIX VVV
        # Ensure this line is present and correctly assigns the callback:
        self.flow_control.set_retransmit_callback(self._retransmit_segment_callback)

        self.send_buffer = []
        self.receive_buffer = []
        self.send_thread = None
        self.receive_thread = None
        self.running = False

    # VVV ENSURE THIS METHOD IS DEFINED IN YOUR Connection CLASS VVV
    def _retransmit_segment_callback(self, seq_num: int, packed_segment_data: bytes):
        """
        Callback for FlowControl to retransmit a segment.
        'packed_segment_data' is the actual bytes of the segment that was originally sent.
        'seq_num' is the sequence number of that segment.
        """
        # Check if connection is in a state where sending is appropriate
        if self.running and self.remote_addr and self.state not in [ConnectionState.CLOSED, ConnectionState.TIME_WAIT, ConnectionState.CLOSING, ConnectionState.LAST_ACK]:
            print(f"Connection ({self.local_addr[1]}): Retransmitting segment (Seq: {seq_num}) to {self.remote_addr}")
            try:
                self.socket.sendto(packed_segment_data, self.remote_addr)
            except Exception as e:
                print(f"Connection ({self.local_addr[1]}): Error during retransmission of segment (Seq: {seq_num}): {e}")
        else:
            print(f"Connection ({self.local_addr[1]}): Suppressed retransmission for segment (Seq: {seq_num}). Connection state: {self.state}, Running: {self.running}")


    # listen() and accept() are largely superseded by server's direct handling
    # but kept for conceptual reference or potential other uses if API evolves.
    def listen(self) -> None:
        """Conceptually prepare to listen for incoming connections."""
        if self.state != ConnectionState.CLOSED:
            raise RuntimeError("Connection must be closed before listening")
        self.state = ConnectionState.LISTEN

    def accept(self) -> 'Connection':
        """
        Original accept logic. Not recommended for the main server loop with a shared UDP socket.
        The server should handle handshake steps more directly.
        """
        if self.state != ConnectionState.LISTEN:
            raise RuntimeError("Connection must be listening to accept connections")
        # This blocking logic is problematic for a single server socket handling multiple clients.
        # Retained for reference but should not be directly used by ChatServer as previously discussed.
        print("Warning: Connection.accept() called, which might be problematic for shared server socket.")
        # ... (original accept logic) ...
        # For this exercise, we assume ChatServer's _handle_client_message handles handshake.
        raise NotImplementedError("Connection.accept() should not be used directly by the server in this revised model.")


    def connect(self, remote_addr: tuple[str, int]) -> None:
        """Initiate connection to remote address (Client-side)"""
        if self.state != ConnectionState.CLOSED:
            raise RuntimeError("Connection must be closed before connecting")

        try:
            # Resolve hostname to IP address for consistent comparison
            # This ensures 'localhost' becomes '127.0.0.1' (or equivalent)
            resolved_host = socket.gethostbyname(remote_addr[0])
            self.remote_addr = (resolved_host, remote_addr[1])
            print(f"Client ({self.local_addr[1]}): Original remote address {remote_addr} resolved to {self.remote_addr}")
        except socket.gaierror:
            print(f"Client ({self.local_addr[1]}): ERROR - Could not resolve hostname {remote_addr[0]}")

        self.local_seq_num = random.randint(0, Segments.seq_max)

        # Send SYN
        syn_segment = Segments(
            source_port=self.local_addr[1],
            dest_port=self.remote_addr[1],
            seq_num=self.local_seq_num,
            flags=Segments.SYN_flag,
            window=self.local_window
        )
        # Client socket is usually blocking by default unless set otherwise.
        # If it was set to non-blocking by ChatClient, this is fine.
        # self.socket.setblocking(False) # Let's assume it's set by the caller if needed, or blocking is fine for connect() parts

        print(f"Client ({self.local_addr[1]}): Sending SYN to {self.remote_addr}. Seq: {syn_segment.seq_num}, Flags: {syn_segment.flags}")
        self.socket.sendto(syn_segment.pack(), self.remote_addr)
        self.state = ConnectionState.SYN_SENT
        print(f"Client ({self.local_addr[1]}): SYN sent. State: {self.state}")

        connection_timeout = time.time() + 10 # 10 seconds timeout for connection
        syn_ack_received_and_final_ack_sent = False

        # Temporarily make socket blocking for this crucial part, or ensure non-blocking loop is robust
        original_blocking_state = self.socket.getblocking()
        if not original_blocking_state: # If it was non-blocking
            self.socket.settimeout(0.1) # Timeout for individual recvfrom calls in non-blocking mode simulation

        while time.time() < connection_timeout:
            try:
                # Forcing a blocking read with timeout for simplicity here, adjust if client socket is meant to be non-blocking always
                if original_blocking_state: # if it was already blocking, recvfrom will block
                     pass # No need to change timeout if it was blocking and might have its own system timeout
                # If it was non-blocking, timeout was set to 0.1 above.

                data, addr = self.socket.recvfrom(Segments.MAX_HEADER_SIZE + Segments.MAX_PAYLOAD_SIZE)

                if addr != self.remote_addr:
                    print(f"Client ({self.local_addr[1]}): Received packet from unexpected address {addr}. Ignoring.")
                    continue

                received_segment = Segments.unpack(data)
                print(f"Client ({self.local_addr[1]}): Received segment from {addr}. Flags={received_segment.flags}, Seq={received_segment.seq_num}, Ack={received_segment.ack_num}, Win={received_segment.window}")

                if (self.state == ConnectionState.SYN_SENT and
                    received_segment.flags & Segments.SYN_flag and    # SYN flag must be set
                    received_segment.flags & Segments.ACK_flag and    # ACK flag must be set
                    received_segment.ack_num == self.local_seq_num + 1): # Must ack our ISN+1

                    print(f"Client ({self.local_addr[1]}): SYN-ACK received and validated. Our ISN was {self.local_seq_num}.")
                    self.remote_seq_num = received_segment.seq_num # Server's ISN
                    self.remote_window = received_segment.window
                    self.local_seq_num = (self.local_seq_num + 1) & Segments.seq_max # Advance our sequence number

                    # Send final ACK for the server's SYN-ACK
                    ack_segment = Segments(
                        source_port=self.local_addr[1],
                        dest_port=self.remote_addr[1],
                        seq_num=self.local_seq_num,               # Our new sequence number (ISN+1)
                        ack_num=(self.remote_seq_num + 1) & Segments.ack_max, # Acknowledging server's ISN+1
                        flags=Segments.ACK_flag,                 # Only ACK flag
                        window=self.local_window
                    )
                    print(f"Client ({self.local_addr[1]}): Preparing to send final ACK. Seq={ack_segment.seq_num}, Ack={ack_segment.ack_num}, Flags={ack_segment.flags}")

                    try:
                        packed_ack = ack_segment.pack()
                        self.socket.sendto(packed_ack, self.remote_addr)
                        print(f"Client ({self.local_addr[1]}): >>> FINAL ACK SENT to {self.remote_addr}. Handshake should complete.")
                    except Exception as e_send:
                        print(f"Client ({self.local_addr[1]}): CRITICAL ERROR - Failed to send final ACK: {e_send}")
                        self.state = ConnectionState.CLOSED # Mark as closed due to failure
                        # Restore socket blocking state before raising
                        if not original_blocking_state: self.socket.setblocking(False) # Or settimeout(None)
                        else: self.socket.setblocking(True)
                        raise TimeoutError(f"Failed to send final ACK for connection: {e_send}") from e_send

                    self.state = ConnectionState.ESTABLISHED
                    syn_ack_received_and_final_ack_sent = True
                    print(f"Client ({self.local_addr[1]}): Handshake complete. State: {self.state}")
                    break # Exit while loop, connection established

            except socket.timeout: # Specific for self.socket.settimeout(0.1)
                # This is normal in a non-blocking style poll
                # print(f"Client ({self.local_addr[1]}): recvfrom timeout (non-blocking poll). Retrying.")
                continue
            except BlockingIOError: # If socket was set to non-blocking elsewhere without timeout
                # print(f"Client ({self.local_addr[1]}): recvfrom would block (non-blocking). Retrying.")
                time.sleep(0.05) # Brief pause before retrying
                continue
            except ValueError as e_unpack: # Segments.unpack error
                print(f"Client ({self.local_addr[1]}): Error unpacking segment during connect: {e_unpack}")
                continue # Try to get next packet
            except Exception as e_loop:
                print(f"Client ({self.local_addr[1]}): Unexpected error in connect recv loop: {e_loop}")
                # Restore socket blocking state before breaking or raising
                if not original_blocking_state: self.socket.setblocking(False)
                else: self.socket.setblocking(True)
                self.state = ConnectionState.CLOSED
                raise # Re-raise the unexpected error

        # Restore original socket blocking state
        if not original_blocking_state: self.socket.setblocking(False) # Or settimeout(None) for non-blocking
        else: self.socket.setblocking(True)


        if not syn_ack_received_and_final_ack_sent:
            self.state = ConnectionState.CLOSED
            print(f"Client ({self.local_addr[1]}): Failed to complete handshake (Timeout or other issue). State: {self.state}")
            raise TimeoutError("Connection attempt timed out (SYN-ACK not processed or final ACK not sent).")

        # If handshake succeeded, start background threads for data transfer
        self.start_background_threads() # is_server_instance defaults to False for client


    def start_background_threads(self, is_server_instance: bool = False):
        """Start background threads for sending and (conditionally) receiving"""
        self.running = True
        if not self.send_thread or not self.send_thread.is_alive():
            self.send_thread = threading.Thread(target=self._send_loop)
            self.send_thread.daemon = True
            self.send_thread.start()

        if not is_server_instance: # Server instances fed segments by ChatServer
            if not self.receive_thread or not self.receive_thread.is_alive():
                self.receive_thread = threading.Thread(target=self._receive_loop)
                self.receive_thread.daemon = True
                self.receive_thread.start()
        # FlowControl timer is started by flow_control.send() when needed.

    def stop_background_threads(self):
        """Stop background threads"""
        self.running = False
        if self.send_thread and self.send_thread.is_alive():
            self.send_thread.join(timeout=1.0)
        if self.receive_thread and self.receive_thread.is_alive(): # Only relevant if started
            self.receive_thread.join(timeout=1.0)
        self.flow_control.stop_timer() # Ensure FC timer is stopped


    def _send_loop(self):
        """Background thread for sending data with flow control and retransmissions"""
        while self.running:
            # This loop should be driven by FlowControl's retransmission timer and send_buffer
            # For simplicity, let's assume flow_control.send will block/wait if window is full
            # or retransmit based on its internal timer triggered by handle_timeout
            # The current flow_control.send is not designed to be called in a tight loop like this for data.
            # It's called when app calls Connection.send().
            # This loop is more for retransmissions handled by FlowControl.

            # Let's refine this: _send_loop primarily ensures data in buffer is attempted.
            # FlowControl handles retransmissions via its timer mechanism.

            if self.send_buffer: # Data application wants to send
                data_to_send = self.send_buffer[0] # Get the first chunk

                # Segmenting data if too large for MAX_PAYLOAD_SIZE
                payload_chunks = []
                if len(data_to_send) > Segments.MAX_PAYLOAD_SIZE:
                    for i in range(0, len(data_to_send), Segments.MAX_PAYLOAD_SIZE):
                        payload_chunks.append(data_to_send[i:i+Segments.MAX_PAYLOAD_SIZE])
                else:
                    payload_chunks.append(data_to_send)

                all_chunks_sent_or_buffered = True
                for chunk in payload_chunks:
                    if self.flow_control.can_send(): # Check if flow control allows sending
                        # Create segment for this chunk
                        data_segment = Segments(
                            source_port=self.local_addr[1],
                            dest_port=self.remote_addr[1],
                            seq_num=self.local_seq_num, # FC will use this as base for sending
                            ack_num=self.flow_control.expected_seq_num, # Acknowledging received data
                            flags=Segments.ACK_flag, # Piggyback ACK if possible
                            window=self.local_window, # Our current receive window size
                            payload=chunk
                        )

                        # flow_control.send buffers the data and manages seq numbers for transmission
                        # It returns the data if successfully buffered/sent, or None/raises error
                        # The seq_num argument to flow_control.send is the actual sequence number for this segment.
                        # self.local_seq_num is the *next* sequence number for *new* data.
                        # FlowControl's send method needs to use and increment its own next_seq_num.

                        # Correcting use of local_seq_num and flow_control
                        # The Connection's local_seq_num is the start of the next block of data the application sends.
                        # FlowControl has its own next_seq_num for segments within its window.

                        # Let's simplify: flow_control.send() itself should use the correct sequence number.
                        # Connection.send() will add to a conceptual stream, and _send_loop + FlowControl will segment and send.
                        # The current flow_control.send needs data and an *optional* sequence_num.
                        # If not provided, it uses its self.next_seq_num.

                        try:
                            # Pass actual data, FC handles seq num internally if not specified
                            if self.flow_control.send(data_segment.pack()): # Pass the packed segment
                                self.local_seq_num = (self.local_seq_num + len(chunk)) & Segments.seq_max # Advance for this chunk
                            else:
                                all_chunks_sent_or_buffered = False # Cannot send this chunk now
                                break
                        except Exception as e: # e.g., TimeoutError from flow_control.send if it blocks too long
                            print(f"Error in _send_loop during flow_control.send: {e}")
                            all_chunks_sent_or_buffered = False
                            break
                    else:
                        all_chunks_sent_or_buffered = False # Window is full
                        break

                if all_chunks_sent_or_buffered:
                    self.send_buffer.pop(0) # Remove the fully processed data block

            time.sleep(0.01) # Prevent tight loop if buffer is empty or window full


    def _receive_loop(self):
        """Background thread for receiving data (Client-side or dedicated socket)"""
        # This loop should only run if the connection has its own socket and is not server-side shared.
        if self.remote_addr is None: # Not connected
            return

        while self.running:
            try:
                data, addr = self.socket.recvfrom(Segments.MAX_HEADER_SIZE + Segments.MAX_PAYLOAD_SIZE)
                if addr != self.remote_addr:
                    continue

                segment = Segments.unpack(data)
                self.handle_received_segment(segment) # Process using the common logic

            except BlockingIOError:
                time.sleep(0.01) # Wait a bit before trying again
                continue
            except ValueError: # Invalid segment
                print(f"Connection ({self.local_addr} -> {self.remote_addr}): Invalid segment received.")
                continue
            except Exception as e:
                if self.running: # Avoid printing errors if we are shutting down
                    print(f"Error in _receive_loop ({self.local_addr} -> {self.remote_addr}): {e}")
                break # Exit loop on other errors
        print(f"Exiting _receive_loop for {self.local_addr} -> {self.remote_addr}")


    def handle_received_segment(self, segment: Segments):
        """Processes an incoming segment. (Called by _receive_loop or by server dispatcher)"""
        #print(f"({self.local_addr[1]}->{self.remote_addr[1] if self.remote_addr else 'N/A'}) Handling segment: flags={segment.flags}, seq={segment.seq_num}, ack={segment.ack_num}, payload_len={len(segment.payload)}")

        # Handle data payload
        if segment.payload:
            # flow_control.receive will buffer out-of-order packets and return in-order data
            # It needs the raw payload and its sequence number
            # The seq_num of the segment IS the sequence number of its payload's first byte
            received_app_data = self.flow_control.receive(segment.payload, segment.seq_num)
            if received_app_data:
                self.receive_buffer.append(received_app_data)
                #print(f"App data received and buffered. Total buffer: {len(self.receive_buffer)} items.")

            # Send ACK for received data segment, even if it's a duplicate or out of order (for cumulative ACK part)
            # The ACK number should be the next expected sequence number by FlowControl
            if self.state == ConnectionState.ESTABLISHED : # Only ACK data if established
                ack_for_data = Segments(
                    source_port=self.local_addr[1],
                    dest_port=self.remote_addr[1],
                    seq_num=self.local_seq_num, # Our current send sequence number (for piggybacking if we send data)
                    ack_num=self.flow_control.expected_seq_num, # Acknowledges all data up to this point
                    flags=Segments.ACK_flag,
                    window=self.local_window # Our current receive window
                )
                self.socket.sendto(ack_for_data.pack(), self.remote_addr)
                #print(f"Sent ACK for data: ack_num={ack_for_data.ack_num}")


        # Handle pure ACKs (acknowledging data we sent)
        if segment.flags & Segments.ACK_flag:
            # This ACK could also be part of a segment carrying data (piggybacked)
            # flow_control.receive_ack updates the send window based on this ACK
            acked_segments_count = self.flow_control.receive_ack(segment.ack_num)
            if acked_segments_count:
                 pass
                #print(f"Processed ACK: ack_num={segment.ack_num}. {len(acked_segments_count)} segments acked.")

        # Handle FIN
        if segment.flags & Segments.FIN_flag:
            self._handle_fin(segment)


    def _handle_fin(self, fin_segment: Segments):
        """Handle received FIN Segments"""
        print(f"FIN received. Current state: {self.state}. FIN segment seq: {fin_segment.seq_num}")
        # Acknowledge the FIN
        # Our ACK number should be FIN's seq_num + 1 (if FIN consumes a sequence number, typically yes)
        ack_num_for_fin = fin_segment.seq_num + 1

        if self.state == ConnectionState.ESTABLISHED:
            # This is the first FIN received from the peer (active close initiated by peer)
            self.remote_seq_num = fin_segment.seq_num # Update remote sequence number

            # Send ACK for their FIN
            fin_ack_reply = Segments(
                source_port=self.local_addr[1],
                dest_port=self.remote_addr[1],
                seq_num=self.local_seq_num, # Our current sending sequence number
                ack_num=ack_num_for_fin,
                flags=Segments.ACK_flag,
                window=self.local_window
            )
            self.socket.sendto(fin_ack_reply.pack(), self.remote_addr)
            print(f"Sent ACK for peer's FIN. Ack num: {ack_num_for_fin}")

            # Application should be notified that no more data will come.
            # Transition to CLOSE_WAIT: we wait for local application to close.
            self.state = ConnectionState.CLOSE_WAIT
            print(f"State changed to {self.state}")
            # The application running on top of this connection should now call close() on this connection.

        elif self.state == ConnectionState.FIN_WAIT: # We sent FIN, they sent FIN back (simultaneous close)
            self.remote_seq_num = fin_segment.seq_num
            # Send ACK for their FIN
            ack_reply = Segments(
                source_port=self.local_addr[1],
                dest_port=self.remote_addr[1],
                seq_num=self.local_seq_num,
                ack_num=ack_num_for_fin,
                flags=Segments.ACK_flag,
                window=self.local_window
            )
            self.socket.sendto(ack_reply.pack(), self.remote_addr)
            print(f"Sent ACK for peer's FIN (simultaneous close). Ack num: {ack_num_for_fin}")
            self.state = ConnectionState.CLOSING # Or TIME_WAIT if their FIN was an ACK to our FIN
            # TCP state machine can be complex here. For simplicity, moving towards closed.
            # More accurately: if their FIN also ACKs our FIN, then TIME_WAIT.
            # If their FIN is separate, then CLOSING, then wait for their ACK to our FIN.

            # If this FIN also ACKs our previously sent FIN (segment.ack_num corresponds to our FIN's seq_num + 1)
            # This check is complex as we need to remember our FIN's seq_num.
            # For now, simplifying:
            self.state = ConnectionState.TIME_WAIT # Assume their FIN implies ACK or will be followed by ACK
            print(f"State changed to {self.state}. Entering TIME_WAIT.")
            # Start TIME_WAIT timer (not implemented here, but important for real TCP)
            # For this example, we'll just allow closure.
            self.running = False # Stop loops

        elif self.state == ConnectionState.LAST_ACK: # We sent FIN (after being in CLOSE_WAIT), waiting for their ACK
            # This FIN is unexpected here. Usually we expect an ACK.
            # Could be a retransmitted FIN from them. Re-send ACK.
            if fin_segment.seq_num == self.remote_seq_num : # If it's the same FIN
                ack_reply = Segments(
                    source_port=self.local_addr[1],
                    dest_port=self.remote_addr[1],
                    seq_num=self.local_seq_num,
                    ack_num=ack_num_for_fin,
                    flags=Segments.ACK_flag,
                    window=self.local_window
                )
                self.socket.sendto(ack_reply.pack(), self.remote_addr)
                print(f"Resent ACK for peer's FIN while in LAST_ACK. Ack num: {ack_num_for_fin}")


    def send(self, data: bytes):
        """Add data to the send buffer for transmission."""
        if self.state != ConnectionState.ESTABLISHED:
            raise RuntimeError("Connection must be established to send data")
        if not data:
            return
        self.send_buffer.append(data) # _send_loop will pick this up

    def receive(self, max_size: int = 4096) -> Optional[bytes]: # max_size currently not used by this impl.
        """Receive data from the connection (application layer call)"""
        if self.state not in [ConnectionState.ESTABLISHED, ConnectionState.FIN_WAIT, ConnectionState.CLOSE_WAIT]:
            # Allow receiving data even if remote has sent FIN (FIN_WAIT) or we are closing (CLOSE_WAIT)
            if not (self.state == ConnectionState.CLOSED and not self.receive_buffer): # Allow draining buffer if closed
                 pass # raise RuntimeError("Connection not in a state to receive data") -> too strict if buffer has data

        if self.receive_buffer:
            return self.receive_buffer.pop(0)

        # If connection is closing or closed and buffer is empty
        if not self.running and not self.receive_buffer:
            return None # Or b'' to signal EOF

        # To make this non-blocking or with timeout for application:
        # This current version relies on _receive_loop (client) or server dispatcher filling the buffer.
        # An application might want a timeout here.
        # For now, it's effectively polling self.receive_buffer.
        # A more robust version might use a Condition variable.
        # For now, returning None if no data.
        return None


    def close(self) -> None:
        """Close the connection gracefully."""
        print(f"Close called. Current state: {self.state}")
        if self.state in [ConnectionState.CLOSED, ConnectionState.LISTEN, ConnectionState.SYN_SENT]:
            self.state = ConnectionState.CLOSED
            self.stop_background_threads()
            return

        if self.state == ConnectionState.ESTABLISHED:
            # Application initiates close
            # Wait for send buffer to be processed by _send_loop (optional, or with timeout)
            # For simplicity, we send FIN immediately.
            fin_segment = Segments(
                source_port=self.local_addr[1],
                dest_port=self.remote_addr[1],
                seq_num=self.local_seq_num, # Our current sending sequence number
                ack_num=self.flow_control.expected_seq_num, # Acknowledge any pending received data
                flags=Segments.FIN_flag | Segments.ACK_flag, # Send FIN+ACK
                window=self.local_window
            )
            self.socket.sendto(fin_segment.pack(), self.remote_addr)
            self.local_seq_num = (self.local_seq_num + 1) & Segments.seq_max # FIN consumes a sequence number
            self.state = ConnectionState.FIN_WAIT
            print(f"Sent FIN+ACK. Seq: {fin_segment.seq_num}. State changed to {self.state}")

        elif self.state == ConnectionState.CLOSE_WAIT:
            # Application confirms close after peer sent FIN
            fin_segment = Segments(
                source_port=self.local_addr[1],
                dest_port=self.remote_addr[1],
                seq_num=self.local_seq_num,
                ack_num=self.flow_control.expected_seq_num, # Should be remote_fin_seq + 1
                flags=Segments.FIN_flag | Segments.ACK_flag,
                window=self.local_window
            )
            self.socket.sendto(fin_segment.pack(), self.remote_addr)
            self.local_seq_num = (self.local_seq_num + 1) & Segments.seq_max
            self.state = ConnectionState.LAST_ACK # Wait for ACK of our FIN
            print(f"Sent FIN+ACK from CLOSE_WAIT. Seq: {fin_segment.seq_num}. State changed to {self.state}")

        # Wait for state to become CLOSED (e.g. after LAST_ACK gets ACK, or FIN_WAIT gets ACK)
        # This requires the ACK processing for FINs to eventually set state to CLOSED or TIME_WAIT then CLOSED.
        # For now, we rely on stop_background_threads and eventual garbage collection.
        # A proper close would wait for ACK to FIN in FIN_WAIT or LAST_ACK.

        # Let's simulate waiting for the state to change or timeout
        close_timeout = time.time() + 5 # 5 seconds for peer to ACK our FIN
        while self.state not in [ConnectionState.CLOSED, ConnectionState.TIME_WAIT] and time.time() < close_timeout:
            if self.state == ConnectionState.FIN_WAIT:
                # Waiting for ACK or FIN+ACK from peer
                # This ACK would be processed by handle_received_segment, potentially changing state.
                pass
            elif self.state == ConnectionState.LAST_ACK:
                # Waiting for ACK from peer
                pass
            time.sleep(0.1)

        if self.state != ConnectionState.CLOSED and self.state != ConnectionState.TIME_WAIT :
            print(f"Close: Timed out waiting for final ACK. Forcing state to CLOSED. Current state: {self.state}")

        if self.state == ConnectionState.TIME_WAIT:
            print("Close: Connection in TIME_WAIT. Will close after timeout (simulated).")
            # Actual TIME_WAIT would last for 2*MSL. Here, we just proceed to close.

        self.state = ConnectionState.CLOSED
        self.stop_background_threads()
        print(f"Connection closed. State: {self.state}")