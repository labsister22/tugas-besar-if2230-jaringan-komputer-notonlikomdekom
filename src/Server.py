import threading
import socket
from datetime import datetime
from tou.Connection import BetterUDPSocket
from tou.Segment import Segment, SYN, ACK, FIN, RECV_BUFFER, MAX_PAYLOAD_SIZE
import queue
import json
import time
import os

# GLOBAL VARIABLES
SRC_PORT = 34112
TIMEOUT = 30
AFK_COUNTDOWN = 30
SERVER_PASSWORD = "admin123"
KILLED = False

server_socket = None
clients = {}
client_lock = threading.Lock()

# Json payload formatted
def create_json_payload(name, msg_type, payload):
    message = {
        "name": name,
        "type": msg_type,
        "timestamp": datetime.now().strftime("%I:%M %p"),
        "payload": payload
    }
    return json.dumps(message)

# AFK countdown (thread)
def afk_countdown(client_addr):
    global clients
    global AFK_COUNTDOWN
    while True:
        time.sleep(1)
        if client_addr not in clients:
            break
        clients[client_addr]['afk_countdown'] += 1
        if clients[client_addr]['afk_countdown'] == AFK_COUNTDOWN:
            client_name = clients[client_addr]['name']
            queue_payload_single_client(client_addr, "SERVER", "terminate_afk", "")
            send_queued_messages(client_addr)
            if client_addr in clients:
                del clients[client_addr]
            queue_payload_clients("SERVER", "message", f"Client {client_name} AFK too long lol, BYEEE!!")
            break


# Heartbeat countdown (thread)
def heartbeat_countdown(client_addr):
    global clients
    while True:
        time.sleep(1)
        if client_addr not in clients:
            break
        clients[client_addr]['time_out'] -= 1
        if clients[client_addr]['time_out'] <= 0:
            print(f"[SERVER] Client {client_addr} timed out, removing.")
            if client_addr in clients:
                del clients[client_addr]
            queue_payload_clients("SERVER", "message", f"Client {client_addr} timed out and has been removed.")
            break

# Add Payload to a single client's queue
def queue_payload_single_client(client_addr, name, msg_type, payload):
    with client_lock:
        json_message = create_json_payload(name, msg_type, payload)
        print("Queueing for client", client_addr)
        if client_addr in clients:
            clients[client_addr]['queue'].put(json_message)
            print("Queue succeed")

# Add Payload to all clients' queues
def queue_payload_clients(name, msg_type, payload):
    global clients
    json_message = create_json_payload(name, msg_type, payload)
    print("Queueing for all clients")
    with client_lock:
        for addr, info in clients.items():
            info['queue'].put(json_message)
            print(f"Queue succeed for {addr}")

def send_queued_messages(client_addr):
    """Kirim semua payload di antrean ke client_addr.

    Format      : UDP datagram berisi Segment custom.
    Reliabilitas: Kirim ulang FIN beberapa kali; tidak menunggu ACK.
    """
    global clients, server_socket
    client = clients.get(client_addr)
    if not client:
        return

    while not client['queue'].empty():
        try:
            # --- Ambil payload JSON ---
            msg = client['queue'].get()
            data = msg.encode()

            # --- Pecah <= MAX_PAYLOAD_SIZE (64 byte) ---
            seq = 0
            for i in range(0, len(data), MAX_PAYLOAD_SIZE):
                chunk = data[i:i + MAX_PAYLOAD_SIZE]
                seg = Segment(
                    SRC_PORT,                 # src_port  = 42234
                    client_addr[1],           # dest_port = port si klien
                    seq_num=seq,
                    payload=chunk
                )
                server_socket.socket.sendto(seg.pack(), client_addr)
                seq += len(chunk)

            # --- Kirim FIN beberapa kali agar klien tahu EoM ---
            fin_seg = Segment(SRC_PORT, client_addr[1], seq_num=seq, flags=FIN)
            for _ in range(3):
                server_socket.socket.sendto(fin_seg.pack(), client_addr)

            print(f"[SERVER] Sent {len(data)} bytes to {client_addr}")

        except Exception as e:
            print(f"[SERVER] Error sending to {client_addr}: {e}")

    # shutdown housekeeping
    if KILLED:
        if client_addr in clients:
            del clients[client_addr]
        if not clients:
            os._exit(0)




# Receiving messages from single client (thread)
def handle_receive(sock_obj, client_addr):
    global TIMEOUT
    global AFK_COUNTDOWN
    global KILLED
    try:
        global clients
        data = sock_obj.receive()
        if data and client_addr in clients:
            client = clients[client_addr]
            decoded = data.decode(errors='ignore')
            msg_json = json.loads(decoded)
            name = msg_json.get("name")
            payload = msg_json.get("payload")
            msg_type = msg_json.get("type")

            # Notify Client joined
            if client['name'] is None:
                client['name'] = name
                queue_payload_clients("SERVER", "message", f"- {name} has joined the chat!")
                return

            # Client send heartbeat
            if msg_type == "heartbeat":
                if client['name'] is not None:
                    client['name'] = name

                client['time_out'] = TIMEOUT
                print(f"[SERVER] Heartbeat ACK received from {client_addr}")
                send_queued_messages(client_addr)
                return

            # Client attempt to kill server
            if msg_type == "kill_server":
                if payload == SERVER_PASSWORD:
                    KILLED = True
                    queue_payload_clients(f"SERVER", "message", "[SERVER] Received kill command from {name}, shutting down SERVER...")
                    queue_payload_clients("SERVER", "terminate_connection", "")
                else:
                    print(f"[SERVER] Invalid kill password attempt by {name}.")
                    queue_payload_clients("SERVER", "message", f"[SERVER] {name} attempted to use !kill with an invalid password.")

            # Client wants to disconnect
            elif msg_type == "disconnect":
                if client_addr in clients:
                    disconnect_name = clients[client_addr].get("name")
                    if client_addr in clients:
                        del clients[client_addr]
                    queue_payload_clients("SERVER", "message",f"- {disconnect_name} has left the chat!")
                    print(f"[SERVER] Client {client_addr} disconnected and removed from list.")
                    return
            else:
                if payload.startswith("!"):
                    queue_payload_single_client(client_addr, "SERVER", "message", "Invalid command!")
                else:
                    client['afk_countdown'] = 0
                    queue_payload_clients(name, "message", payload)

    except Exception as e:
        print(f"[SERVER] Receive error from {client_addr}: {e}")

def main():
    global TIMEOUT
    main_sock = BetterUDPSocket()
    main_sock.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    main_sock.bind(('0.0.0.0', SRC_PORT))
    global server_socket
    server_socket = main_sock
    print(f"[SERVER] Listening on port {SRC_PORT}...")
    result_queue = queue.Queue()

    while True:
        try:
            data, client_addr = main_sock.socket.recvfrom(RECV_BUFFER)
            seg = Segment.unpack(data)

            # Ignore unecessary FLAG segment
            if (seg.flags & ACK) or (seg.flags & FIN):
                continue

            # Synchronize new Client
            if seg.flags & SYN:

                # Avoid duplicate handshake from same client
                if client_addr in clients:
                    continue

                # Spawn a thread to handle this client's handshake
                client_thread = threading.Thread(target=main_sock.listen, args=(main_sock.socket, SRC_PORT, client_addr, seg, result_queue))
                client_thread.daemon = True
                client_thread.start()
                client_thread.join()

                # Create new enty dict
                client_isn = result_queue.get()
                client_info = {
                    'name': None,
                    'dest_port': main_sock.dest_port,
                    'client_isn': client_isn,
                    'time_out': TIMEOUT,
                    'sending_payload': False,
                    'queue': queue.Queue(),
                    'afk_countdown': 0
                }
                clients[client_addr] = client_info
                queue_payload_single_client(client_addr, "SERVER", "message", f"- ({len(clients.keys())} Online Users)")


                # Heartbeat countdown
                threading.Thread(target=heartbeat_countdown, args=(client_addr,), daemon=True).start()

                # AFK countdown
                threading.Thread(target=afk_countdown, args=(client_addr,), daemon=True).start()

            # Handles normal message / commands from clients
            elif seg.flags == 0:
                if client_addr not in clients:
                    print(f"[SERVER] Unknown sender, starting receive thread: {client_addr}")
                    continue

                # Spawn thread to handle receive messages
                client_info = clients[client_addr]
                if not client_info['sending_payload']:
                    client_info['sending_payload'] = True
                    t_receive = threading.Thread(target=handle_receive, args=(main_sock, client_addr), daemon=True)
                    t_receive.start()
                    t_receive.join()
                    client_info['sending_payload'] = False
                else:
                    continue

        except Exception as e:
            print(e)
        except TimeoutError:
            continue

if __name__ == "__main__":
    main()