# Server side
import socket
host = '127.0.0.1'
port = 5000

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((host, port))
server_socket.listen(5)

conn, addr = server_socket.accept()
while True:
    data = conn.recv(1024).decode()
    if not data:
        break
    conn.send('Hello, client'.encode())
conn.close()