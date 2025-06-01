from tou.Connections import BetterUDPSocket
from tou.Segment import Segment, SYN, ACK, FIN, RECV_BUFFER, MAX_PAYLOAD_SIZE

from datetime import datetime

import json
import time
import os

import threading
import socket
import queue

SRC_PORT = 34112
TIMEOUT = 30
AFK_COUNTDOWN = 30

SERVER_PASSWORD = "admin123"

is_server_killed = False

server_socket = None
clients = {}
client_lock = threading.Lock()

def _afk_thread(client_addr):
    while True:

        time.sleep(1)
        if client_addr not in clients:
            break

        clients[client_addr]['afk_countdown'] += 1

        if clients[client_addr]['afk_countdown'] == AFK_COUNTDOWN:
            client_name = clients[client_addr]['name']
            queue_payload_single_client(client_addr, "SERVER", "terminate_afk", "")
            dispatch_messages(client_addr)
            if client_addr in clients:
                del clients[client_addr]
            broadcast("SERVER", "message", f"Client {client_name} Disconnected for being AFK too long")
            break


def _heartbeat_thread(client_addr):
    while True:

        time.sleep(1)
        if client_addr not in clients:
            break

        clients[client_addr]['time_out'] -= 1

        if clients[client_addr]['time_out'] <= 0:
            print(f"[SERVER] Client {client_addr} timed out, removing.")
            if client_addr in clients:
                del clients[client_addr]
            broadcast("SERVER", "message", f"Client {client_addr} timed out and has been removed.")
            break


def handle_receive(sock_obj, client_addr):
    global is_server_killed
    try:
        data = sock_obj.recv()
        if data and client_addr in clients:
            decoded = data.decode(errors='ignore')
            msg_json = json.loads(decoded)

            name = msg_json.get("name")
            payload = msg_json.get("payload")
            msg_type = msg_json.get("type")

            client = clients[client_addr]

            if client['name'] is None:
                client['name'] = name
                broadcast("SERVER", "message", f"- {name} has joined!")
                return

            match  msg_type:
                case "heartbeat":
                    if client['name'] is not None:
                        client['name'] = name

                    # referesh timeout
                    client['time_out'] = TIMEOUT
                    print(f"[SERVER] Heartbeat ACK received from {client_addr}")
                    dispatch_messages(client_addr)
                    return
                case "kill":
                    if payload == SERVER_PASSWORD:
                        is_server_killed = True
                        broadcast(f"SERVER", "message", "[SERVER] Received kill command from {name}, shutting down SERVER...")
                        broadcast("SERVER", "terminate_connection", "")
                    else:
                        print(f"[SERVER] Invalid kill password attempt by {name}.")
                        broadcast("SERVER", "message", f"[SERVER] {name} attempted to use !kill with an invalid password.")
                case "disconnect":
                    if client_addr in clients:
                        disconnect_name = clients[client_addr].get("name")
                        if client_addr in clients:
                            del clients[client_addr]
                        broadcast("SERVER", "message",f"- {disconnect_name} has left the chat!")
                        print(f"[SERVER] Client {client_addr} disconnected and removed from list.")
                        return
                case _:
                    if payload.startswith("!"):
                        queue_payload_single_client(client_addr, "SERVER", "message", "Invalid command!")
                    else:
                        client['afk_countdown'] = 0
                        broadcast(name, "message", payload)

    except Exception as e:
        print(f"[SERVER] Receive error from {client_addr}: {e}")

def add_client(sock, addr, segment, result_queue) :
        client_thread = threading.Thread(target=sock.listen, args=(sock.socket, SRC_PORT, addr, segment, result_queue))
        client_thread.daemon = True

        client_thread.start()
        client_thread.join()

        client_isn = result_queue.get()
        client_info = {'name': None, 'port': sock.dest_port, 'client_isn': client_isn, 'time_out': TIMEOUT, 'is_sending': False, 'queue': queue.Queue(), 'afk_countdown': 0 }
        clients[addr] = client_info

        queue_payload_single_client(addr, "SERVER", "message", f"- ({len(clients.keys())} Online Users)")

def queue_payload_single_client(client_addr, name, msg_type, payload):
    with client_lock:
        json_message = create_json_payload(name, msg_type, payload)
        print("Queueing for client", client_addr)
        if client_addr in clients:
            clients[client_addr]['queue'].put(json_message)
            print("Queue succeed")

def broadcast(name, msg_type, payload):
    json_message = create_json_payload(name, msg_type, payload)
    print("Queueing for all clients")
    with client_lock:
        for addr, info in clients.items():
            info['queue'].put(json_message)
            print(f"Queue succeed for {addr}")

def dispatch_messages(client_addr):
    client = clients.get(client_addr)
    if not client:
        return

    while not client['queue'].empty():
        try:
            msg = client['queue'].get()
            data = msg.encode()

            seq = 0
            for i in range(0, len(data), MAX_PAYLOAD_SIZE):
                chunk = data[i:i + MAX_PAYLOAD_SIZE]
                seg = Segment(
                    SRC_PORT,
                    client_addr[1],
                    seq_num=seq,
                    payload=chunk
                )
                server_socket.socket.sendto(seg.pack(), client_addr)
                seq += len(chunk)

            fin_seg = Segment(SRC_PORT, client_addr[1], seq_num=seq, flags=FIN)
            for _ in range(3):
                server_socket.socket.sendto(fin_seg.pack(), client_addr)

            print(f"[SERVER] Sent {len(data)} bytes to {client_addr}")

        except Exception as e:
            print(f"[SERVER] Error sending to {client_addr}: {e}")

    if is_server_killed:
        if client_addr in clients:
            del clients[client_addr]
        if not clients:
            os._exit(0)

def create_json_payload(name, msg_type, payload):
    message = {
        "name": name,
        "type": msg_type,
        "timestamp": datetime.now().strftime("%I:%M %p"),
        "payload": payload
    }
    return json.dumps(message)

def main():

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
            segment = Segment.unpack(data)

            if (segment.flags & ACK) or (segment.flags & FIN):
                continue

            if segment.flags & SYN:

                if client_addr in clients:
                    continue

                add_client(main_sock, client_addr, segment, result_queue)

                threading.Thread(target=_heartbeat_thread, args=(client_addr,), daemon=True).start()
                threading.Thread(target=_afk_thread, args=(client_addr,), daemon=True).start()

            elif segment.flags == 0:
                if client_addr not in clients:
                    print(f"[SERVER] Unknown sender, starting receive thread: {client_addr}")
                    continue

                client_info = clients[client_addr]
                if not client_info['is_sending']:
                    client_info['is_sending'] = True
                    t_receive = threading.Thread(target=handle_receive, args=(main_sock, client_addr), daemon=True)
                    t_receive.start()
                    t_receive.join()
                    client_info['is_sending'] = False
                else:
                    continue
        except TimeoutError:
            continue
        except Exception as e:
            print(e)

if __name__ == "__main__":
    main()