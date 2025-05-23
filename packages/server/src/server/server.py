import socket
import threading
import time
import json
from packages.tou.src.tou import BetterUDPSocket

HOST = '0.0.0.0'
PORT = 41234
HEARTBEAT_TIMEOUT = 30
MAX_MESSAGES = 20

users = {}  # (ip, port): {'display_name': str, 'last_seen': float}
chat_log = []  # list of dict: {'display_name', 'timestamp', 'message'}

sock = BetterUDPSocket()
sock.sock.bind((HOST, PORT))
print(f"[SERVER] Listening on {HOST}:{PORT}")

sock.listen()
print("[SERVER] Ready to accept clients!")

def cleanup_inactive():
    while True:
        now = time.time()
        to_remove = []
        for addr, user in users.items():
            if now - user['last_seen'] > HEARTBEAT_TIMEOUT:
                to_remove.append(addr)
        for addr in to_remove:
            print(f"[SERVER] Removing inactive user {users[addr]['display_name']} {addr}")
            del users[addr]
        time.sleep(5)

def handle_client():
    while True:
        data = sock.receive()
        if not data:
            continue
        payload, header, addr = data
        try:
            msg = json.loads(payload.decode())
        except Exception:
            continue
        now = time.time()
        # Register or update user
        if 'display_name' in msg:
            users[addr] = {'display_name': msg['display_name'], 'last_seen': now}
        if msg.get('type') == 'heartbeat':
            users[addr]['last_seen'] = now
            # Kirim chat log terbaru
            last_msgs = chat_log[-MAX_MESSAGES:]
            sock.send(json.dumps({'type': 'chat', 'messages': last_msgs}).encode(), window_size=4)
        elif msg.get('type') == 'chat':
            # Simpan pesan dan broadcast
            chat_entry = {
                'display_name': users[addr]['display_name'],
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)),
                'message': msg['message']
            }
            chat_log.append(chat_entry)
            # Broadcast ke semua user
            for uaddr in users:
                sock.connected_addr = uaddr
                sock.send(json.dumps({'type': 'chat', 'messages': [chat_entry]}).encode(), window_size=4)

if __name__ == "__main__":
    threading.Thread(target=cleanup_inactive, daemon=True).start()
    handle_client()
