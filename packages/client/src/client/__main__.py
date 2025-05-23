# Client side
import socket

host = '127.0.0.1'
port = 5000

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((host, port))

client_socket.send(b'Hello, server!')
data = client_socket.recv(1024).decode()
client_socket.close()