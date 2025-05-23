import socket
import threading
import time
import json
from packages.tou.src.tou import BetterUDPSocket

HEARTBEAT_INTERVAL = 1
MAX_MESSAGES = 20

def input_thread(send_queue):
    while True:
        msg = input()
        send_queue.append(msg)

def main():
    server_ip = input("Server IP: ")
    server_port = int(input("Server Port: "))
    display_name = input("Display Name: ")
    sock = BetterUDPSocket()
    sock.connect(server_ip, server_port)
    print(f"[CLIENT] Connected to {server_ip}:{server_port}")
    send_queue = []
    threading.Thread(target=input_thread, args=(send_queue,), daemon=True).start()
    last_msgs = []
    while True:
        # Kirim heartbeat & request chat log
        heartbeat = json.dumps({'type': 'heartbeat', 'display_name': display_name}).encode()
        sock.send(heartbeat, window_size=4)
        # Terima chat log
        try:
            data = sock.receive()
            if data:
                payload, header, addr = data
                msg = json.loads(payload.decode())
                if msg.get('type') == 'chat':
                    last_msgs = msg['messages']
        except Exception:
            pass
        # Tampilkan pesan terakhir
        if last_msgs:
            print("\033c", end="")  # clear screen
            for entry in last_msgs[-MAX_MESSAGES:]:
                print(f"{entry['display_name']} [{entry['timestamp']}]: {entry['message']}")
        # Kirim pesan user jika ada
        while send_queue:
            user_msg = send_queue.pop(0)
            chat = json.dumps({'type': 'chat', 'display_name': display_name, 'message': user_msg}).encode()
            sock.send(chat, window_size=4)
        time.sleep(HEARTBEAT_INTERVAL)

if __name__ == "__main__":
    main()
