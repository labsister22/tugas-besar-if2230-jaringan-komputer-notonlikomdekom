import threading
import time
import json
from tou import BetterUDPSocket

HOST = '0.0.0.0'
PORT = 41234
HEARTBEAT_TIMEOUT = 4
MAX_MESSAGES = 20

users = {}  # (ip, port): {'display_name': str, 'last_seen': float}
chat_log = []  # list of dict: {'display_name', 'timestamp', 'message'}

sock = BetterUDPSocket()

def cleanup_inactive():
    while True:
        now = time.time()
        inactive = [addr for addr, info in users.items() if now - info['last_seen'] > HEARTBEAT_TIMEOUT]
        for addr in inactive:
            print(f"[SERVER] Removing inactive user {users[addr]['display_name']} {addr}")
            del users[addr]
        time.sleep(5)

def handle_clients():
    while True:
        try:
            data, addr = sock.receive()
        except Exception as e:
            print(f"[ERROR] Receiving from {addr}: {e}")
            continue
        print(f"Receiving from {addr}")
        try:
            msg = json.loads(data.decode())
        except Exception as e:
            print(f"[ERROR] Failed to parse message from {addr}: {e}")
            continue

        now = time.time()
        print("receiving ", msg.get('type'))

        # Register/update user
        if 'display_name' in msg:
            users[addr] = {'display_name': msg['display_name'], 'last_seen': now}
        elif addr not in users:
            print(f"[WARN] Message from unknown client {addr}")
            continue
        else:
            users[addr]['last_seen'] = now

        if msg.get('type') == 'heartbeat':
            last_msgs = chat_log[-MAX_MESSAGES:]
            sock.connected_addr = addr
            # sock.send(json.dumps({'type': 'chat', 'messages': last_msgs}).encode(), window_size=4)

        elif msg.get('type') == 'chat':
            entry = {
                'display_name': users[addr]['display_name'],
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)),
                'message': msg['message']
            }
            chat_log.append(entry)
            print(f"[CHAT] {entry['display_name']}: {entry['message']}")
            # Broadcast to all users
            for uaddr in users:
                sock.connected_addr = uaddr
                sock.send(json.dumps({'type': 'chat', 'messages': [entry]}).encode(), window_size=4)

def main():
    sock.sock.bind((HOST, PORT))
    print(f"[SERVER] Listening on {HOST}:{PORT}")
    sock.listen()
    print("[SERVER] Ready to accept clients!")
    threading.Thread(target=cleanup_inactive, daemon=True).start()
    handle_clients()