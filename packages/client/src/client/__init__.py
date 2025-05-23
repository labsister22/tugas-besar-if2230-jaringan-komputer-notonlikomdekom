from packages.tou.src.tou import BetterUDPSocket
import socket

# Create socket
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Send message to server
client_socket.sendto(b"Hello, server!", ('127.0.0.1', 41234))

# Close socket
client_socket.close()

def main() -> None:
    print("Hello from client!")
