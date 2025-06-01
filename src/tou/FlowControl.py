import threading
import time
from tou.Segment import Segment, ACK, FIN, MAX_PAYLOAD_SIZE, RECV_BUFFER

class GoBackNSender:
    def __init__(self, sock, dest_addr, window_size=4, timeout=None):
        self.sock = sock
        self.dest_addr = dest_addr
        self.window_size = window_size
        self.timeout = timeout
        self.stop_ack_listener = False

    def send_data(self, data, src_port, dest_port, seq_start=0):
        # Split data into segments
        chunks = [data[i:i+MAX_PAYLOAD_SIZE] for i in range(0, len(data), MAX_PAYLOAD_SIZE)]
        seq_nums = [seq_start + sum(len(c) for c in chunks[:i]) for i in range(len(chunks))]
        segments = [Segment(src_port, dest_port, seq_num=seq, payload=chunk) for seq, chunk in zip(seq_nums, chunks)]
        total = len(segments)
        base = 0
        next_seq = 0
        acked = [False] * total

        def start_timer():
            return time.time()

        def ack_listener():
            nonlocal base
            while not self.stop_ack_listener and base < total:
                try:
                    ack_data, _ = self.sock.recvfrom(RECV_BUFFER)
                    ack_seg = Segment.unpack(ack_data)
                    if ack_seg.flags & ACK:
                        ack_num = ack_seg.ack_num
                        for i, seg in enumerate(segments):
                            seg_end = seg.seq_num + len(seg.payload)
                            if seg_end <= ack_num:
                                acked[i] = True
                        while base < total and acked[base]:
                            base += 1
                except Exception:
                    continue

        ack_thread = threading.Thread(target=ack_listener, daemon=True)
        ack_thread.start()

        timeout_limit = 30
        start_time = time.time()
        timer_start = None

        try:
            while base < total:
                if time.time() - start_time > timeout_limit:
                    raise TimeoutError("Sending window timeout exceeded 30 seconds")

                while next_seq < base + self.window_size and next_seq < total:
                    self.sock.sendto(segments[next_seq].pack(), self.dest_addr)
                    if base == next_seq:
                        timer_start = start_timer()
                    next_seq += 1
                if timer_start:
                    for i in range(base, min(base + self.window_size, total)):
                        self.sock.sendto(segments[i].pack(), self.dest_addr)
                    timer_start = start_timer()
        except Exception as e:
            print(f"Exception in send_data: {e}")
            self.stop_ack_listener = True
            ack_thread.join()
            raise

        self.stop_ack_listener = True
        ack_thread.join()

        # --- Mutual FIN-ACK ---
        fin_seq = segments[-1].seq_num + len(segments[-1].payload) if segments else seq_start
        fin_seg = Segment(src_port, dest_port, seq_num=fin_seq, flags=FIN)

        start_time = time.time()

        for i in range(60):
            self.sock.sendto(fin_seg.pack(), self.dest_addr)

class GoBackNReceiver:
    def __init__(self, sock):
        self.sock = sock

    def receive_data(self, src_port, dest_port, expected_seq=0):
        received_data = []
        Rn = expected_seq
        sender_addr = None

        # --- 1. Receive all data segments ---
        start_time = time.time()
        timeout_limit = 30
        while True:
            try:
                if time.time() - start_time > timeout_limit:
                    raise

                try:
                    data, addr = self.sock.recvfrom(RECV_BUFFER)
                except TimeoutError:
                    print("timeout di reeive_data")
                    break
                except Exception:
                    break

                seg = Segment.unpack(data)
                sender_addr = addr

                if seg.flags & FIN:
                    #send ACK
                    for i in range(60):
                        ack_seg = Segment(src_port, dest_port, ack_num=seg.seq_num + 1, flags=ACK)
                        self.sock.sendto(ack_seg.pack(), sender_addr)
                    break

                if seg.seq_num == Rn and seg.verify_checksum():
                    received_data.append(seg.payload)
                    Rn += len(seg.payload)

                ack_seg = Segment(src_port, dest_port, ack_num=Rn, flags=ACK)
                self.sock.sendto(ack_seg.pack(), sender_addr)
            except TimeoutError as e:
                print(f"[Receiver] Timeout: {e}")
                break
            except Exception as e:
                break
            finally:
                self.sock.settimeout(None)

        return b''.join(received_data)
