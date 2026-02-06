# import io
import socket
import threading
# import time

from serial.serialutil import SerialException

try:
    from demo.TcpSerialServerPort import TcpSerialServerPort, Signal
except ImportError:
    from TcpSerialServerPort import TcpSerialServerPort, Signal

DEBUG_WHOAMI = False

WHO_AM_I = "WHOAMI"
CTRL_CMDS = [WHO_AM_I]


class TcpSerialServer:
    def __init__(
            self,
            host="127.0.0.1",
            port=31950,
            timeout=None,
            write_timeout=None,
            heartbeat_interval=5):
        self.host = host
        self.port = port

        # timeouts (in seconds)
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.heartbeat_interval = heartbeat_interval

        # TX and RX signals to transact with the client
        self.broadcast_tx_line = Signal()
        self.tx_line = Signal()
        self.rx_line = Signal()

        # Add handlers for server to process lines to/from clients
        self.broadcast_tx_line.connect(self._on_broadcast_tx_event)
        self.tx_line.connect(self._on_tx_event)
        self.rx_line.connect(self._on_client_rx_event)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # -----------------------------
    # Socket server methods
    # -----------------------------

    def listen(self):
        if self.write_timeout is not None:
            self._sock.settimeout(self.write_timeout)
        self._sock.bind((self.host, self.port))
        self._sock.listen(1)

    def accept(self):
        conn, addr = self._sock.accept()
        return (TcpSerialServerPort(
            conn=conn,
            host=self.host,
            port=self.port,
            timeout=self.timeout,
            write_timeout=self.write_timeout,
            heartbeat_interval=self.heartbeat_interval),
            addr)

    def close(self):
        self._sock.close()

    # -----------------------------
    # Start / Stop
    # -----------------------------

    def start(self):
        """
        Start client connection and data handling loop in background thread.
        """
        if not hasattr(self, '_server_thread'):
            self._server_thread = threading.Thread(
                target=self.run,
                daemon=True,
            )
        if not self._server_thread.is_alive():
            self._server_thread.start()

    def stop(self):
        """
        Stop client connection and data handling loop.
        """
        for client in self.clients:
            if client and not client.closed:
                client.stop()  # Stop all client connections

        self._exit = True
        if hasattr(self, '_server_thread'):
            self._server_thread.join()

    # -----------------------------
    # Client management
    # -----------------------------

    def connected(self):
        """
        Get list of connected clients, and their IDs.
        """
        return [(i+1, c) for i, c in enumerate(self.clients) if c and not c.closed]

    def disconnect(self, i):
        """
        Disconnect current client (if any).
        """
        self._disconnect_client = i

    def disconnect_all(self):
        """
        Disconnect all clients.
        """
        self._disconnect_client = float('inf')

    # -----------------------------
    # TX/RX line handlers
    # -----------------------------

    def _on_broadcast_tx_event(self, line):
        """
        Handle broadcast TX line event by sending line to all clients.
        """
        for client in self.clients:
            if client and not client.closed:
                client.tx_line.emit(line)

    def _on_tx_event(self, client_id, line):
        """
        Handle TX line event by sending line to client.
        """
        print(f"Sending to client {client_id}: {line}")
        client = self.clients[client_id - 1]
        if client and not client.closed:
            client.tx_line.emit(line)

    def _on_client_rx_event(self, client_id, line):
        """
        Handle RX line event by processing line from client.
        """
        if line.upper() == WHO_AM_I:
            if DEBUG_WHOAMI:
                print(f"Received WHOAMI query from client {client_id}")
            # Respond to this client with their registered client ID
            self.tx_line.emit(client_id, "CLIENT #{}".format(client_id))

            # -----------------------------
            # Main client handling loop
            # -----------------------------

    def run(self):
        def handle_client(client, i):
            try:
                while not client.closed and not self._exit:
                    if self._disconnect_client == i or self._disconnect_client == float('inf'):
                        print(f"Disconnecting client {i} as requested.")
                        remaining_clients = [
                            c for c in self.clients if c and not c.closed]
                        if self._disconnect_client == i or len(remaining_clients) == 1:
                            self._disconnect_client = None
                        client.close()
            except SerialException as e:
                print(f"Serial exception in client {i} handler: {e}")
            finally:
                print(f"Client {i} handler exiting.")
                try:
                    client.close()
                except (OSError, SerialException):
                    pass
                try:
                    self.clients[i - 1] = None
                except ValueError:
                    pass
            print(f"Client {i} connection closed.")

        # Initialize state
        self._exit = False
        self._disconnect_client = None
        self.threads = []
        self.clients = []
        self.addrs = []

        try:
            print("Starting TCP serial server...")
            self.listen()
            print("Server started.")

            while not self._exit:
                print("Waiting for client...")
                client, addr = self.accept()
                print("Connected:", addr)

                # Forward RX lines from client to server rx_line signal w/ client ID
                client.rx_line.connect(
                    lambda line, i=len(self.clients)+1: self.rx_line.emit(i, line))

                client.start()
                self.clients.append(client)
                self.addrs.append(addr)
                self.threads.append(threading.Thread(
                    target=handle_client, args=(client, len(self.clients),), daemon=True))
                self.threads[-1].start()

                # Send welcome message via server with client ID
                self.tx_line.emit(
                    len(self.clients), "CLIENT #{}".format(len(self.clients)))

        except (OSError, SerialException) as e:
            print(f"Serial exception: {e}")
            print("Exception occurred, listening for client...")
            # Send RESET command on reconnect
            self.broadcast_tx_line.emit("RESET")

        finally:
            print("Shutting down server...")
            self._exit = True
            for t in self.threads:
                t.join()
            self.close()
            print("Server shut down.")


if __name__ == "__main__":

    # Simple test of TCP serial server
    server = TcpSerialServer(
        host="localhost", port=31950,
        timeout=None, write_timeout=None,
        heartbeat_interval=5)

    server.rx_line.connect(
        lambda i, line: print(f"Received from client {i}: {line}"))

    server.start()

    # Listen for user input
    while not server._exit:
        line = input("Enter line to send (or 'close' or 'exit')...\n")
        if line.lower() in ["connected", "clients"]:
            print("Connected clients:")
            client_count = 0
            for i, client in server.connected():
                print(f"Client ID: {i}, Address: {server.addrs[i-1]}")
                client_count += 1
            print(f"{client_count} connected clients.")
        elif line.lower() == "close":
            # Mark current client for closing (if one exists)
            print("Close command received.")
            server.disconnect_all()
        elif line.lower() == 'exit':
            print("Exit command received.")
            server.close()  # Close server socket
            server.stop()  # Stop all clients and main run loop
        elif len(line):
            server.broadcast_tx_line.emit(line)

    print("Exiting server demo.")
