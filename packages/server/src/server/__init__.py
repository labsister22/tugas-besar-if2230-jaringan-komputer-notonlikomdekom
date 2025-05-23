import socket

# Create and bind socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind(('0.0.0.0', 41234))

# Wait for incoming messages
while True:
	data, addr = server_socket.recvfrom(1024)
	print(f"Received message: {data.decode()} from {addr[0]}:{addr[1]}")

def main() -> None:
    print("Hello from server!")
