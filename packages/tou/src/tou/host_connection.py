from tou.connection import Connection


class HostConnection(Connection):
    '''Established TCP over UDP connection on host side'''


    def __init__(self, host, connection_request):
        '''Creates a host connection from a host and a connection request to the host'''

        super().__init__(
            host.address[0],
            host.address[1],
            connection_request.ip_addr,
            connection_request.port,
            connection_request.incoming_window,
            connection_request.outgoing_window,
            host.resend_delay,
            host.timeout
        )

        self._highest_accepted_seq = connection_request.remote_seq_num
        self._highest_sent_seq = connection_request.local_seq_num
        self._highest_received_ack = self._highest_sent_seq + 1

        self._recv_buffer: list[bytes] = []
        self.host = host

        super()._connect()


    def _internal_recv(self, buf_size) -> bytes:
        if self._recv_buffer:
            data = self._recv_buffer[0]
            self._recv_buffer.pop(0)
            return data[:max(buf_size, len(data))]
        else:
            return b''


    def _after_disconnect(self):
        self.host._internal_disconnect(self)


    def _internal_send(self, data):
        return self.host._internal_sendto(self.remote_addr[0], self.remote_addr[1], data)


    def _internal_recvfrom(self, data: bytes):
        '''Sends data to this connection, used by the host class to distribute incoming segments'''

        self._recv_buffer.append(data)
