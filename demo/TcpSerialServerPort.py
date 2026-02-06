import io
import socket
import threading
import time

from serial.serialutil import (
    SerialException,
    SerialTimeoutException,
)

DEBUG_ACKS = False
DEBUG_HEARTBEAT = False
DEBUG_WHOAMI = False

ACK = "ACK"
HEARTBEAT = "BA-BUM"
WHOAMI_REPLY = "CLIENT #"  # starts with
CTRL_CMDS = [ACK, HEARTBEAT, WHOAMI_REPLY]


class TcpSerialServerPort(io.RawIOBase):
    """
    Serial-style endpoint representing ONE accepted TCP connection.
    """

    def __init__(
            self,
            conn=None,
            host="127.0.0.1",
            port=31950,
            timeout=None,
            write_timeout=None,
            heartbeat_interval=None,
            auto_reconnect=False):
        super().__init__()

        self._running = False
        self._sock = conn
        self.host = host
        self.port = port

        # timeouts (in seconds)
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.heartbeat_interval = heartbeat_interval

        # Client auto-reconnect on disconnect (only for client use)
        self.auto_reconnect = auto_reconnect

        self._rx_buffer = bytearray()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)

        self._write_ack = False
        self._client_id = 0  # 0 means 'not assigned'

        # TX and RX signals to transact with the client
        self.tx_line = Signal()
        self.rx_line = Signal()

        self.tx_line.connect(self._on_tx_event)

        # Socket *may* already be running from server accept
        # If no socket yet, create and connect using host/port
        self.open()

    # -----------------------------
    # Properties
    # -----------------------------

    @property
    def is_open(self):
        return self._sock is not None

    @property
    def in_waiting(self):
        with self._lock:
            return len(self._rx_buffer)

    @property
    def client_id(self):
        return self._client_id

    # -----------------------------
    # RawIOBase API
    # -----------------------------

    def readable(self):
        return True

    def writable(self):
        return True

    def seekable(self):
        return False

    # -----------------------------
    # Buffer Control
    # -----------------------------

    def flush(self):
        """
        Block until outgoing data has been handed to the OS.
        TCP cannot guarantee wire-level drain.
        """
        if not self.is_open:
            raise SerialException("Attempt to flush closed port")

        try:
            self._sock.send(b"")
        except OSError as e:
            raise SerialException(str(e)) from e

    def reset_input_buffer(self):
        if not self.is_open:
            raise SerialException("Attempt to reset buffer on closed port")

        with self._lock:
            self._rx_buffer.clear()

    def reset_output_buffer(self):
        """
        TCP cannot retract already-sent bytes.
        This mirrors pySerial's best-effort semantics.
        """
        if not self.is_open:
            raise SerialException("Attempt to reset buffer on closed port")
        # No-op by design

    # -----------------------------
    # Open / Close
    # -----------------------------

    def open(self):
        if not self.is_open:
            # Socket not yet connected, create and connect
            try:
                self._sock = socket.create_connection(
                    (self.host, self.port),
                    timeout=self.timeout,
                )
                self._sock.settimeout(0.5)
            except OSError as e:
                raise SerialException(str(e)) from e

        self._running = True

        # RX loop thread
        if not hasattr(self, '_rx_thread') or not self._rx_thread.is_alive():
            self._rx_thread = threading.Thread(
                target=self._rx_loop,
                daemon=True,
            )
            self._rx_thread.start()

        # RX print thread
        if not hasattr(self, '_rx_print_thread') or not self._rx_print_thread.is_alive():
            self._rx_print_thread = threading.Thread(
                target=self._rx_print_lines,
                daemon=True,
            )
            self._rx_print_thread.start()

        # TX heartbeat thread
        if not hasattr(self, '_tx_heartbeat_thread') or not self._tx_heartbeat_thread.is_alive():
            self._tx_heartbeat_thread = threading.Thread(
                target=self._tx_heartbeat,
                daemon=True,
            )
            self._tx_heartbeat_thread.start()

    def close(self):
        super().close()

        self._running = False

        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass

        self._sock = None

        # Wait for threads to exit
        self._rx_thread.join(timeout=1)
        self._tx_heartbeat_thread.join(timeout=1)
        self._rx_print_thread.join(timeout=1)

        print("Client connection closed.")

    # -----------------------------
    # Write / Read
    # -----------------------------

    def write(self, b):
        if not self.is_open:
            raise SerialException("Attempt to write to closed port")

        if not isinstance(b, (bytes, bytearray, memoryview)):
            raise TypeError("write() argument must be bytes-like")

        view = memoryview(b)
        total = 0
        start = time.monotonic()
        self._write_ack = False

        try:
            if self.write_timeout is not None:
                self._sock.settimeout(self.write_timeout)

            while total < len(view):
                sent = self._sock.send(view[total:])
                if sent == 0:
                    raise SerialException("Socket connection broken")
                total += sent

                if self.write_timeout is not None:
                    if time.monotonic() - start > self.write_timeout:
                        raise SerialTimeoutException("Write timeout")

            return total

        except socket.timeout:
            raise SerialTimeoutException("Write timeout")
        except OSError as e:
            raise SerialException(str(e)) from e

    def read(self, size=1):
        if size is None or size < 0:
            size = float("inf")

        if not self.is_open:
            raise SerialException("Attempt to read from closed port")

        deadline = None
        if self.timeout is not None:
            deadline = time.monotonic() + self.timeout

        with self._cond:
            while len(self._rx_buffer) == 0:
                if self.timeout == 0:
                    return b""

                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return b""
                    self._cond.wait(remaining)
                else:
                    self._cond.wait()

            n = min(size, len(self._rx_buffer))
            data = self._rx_buffer[:n]
            del self._rx_buffer[:n]
            return bytes(data)

    # -----------------------------
    # Additional read helpers
    # -----------------------------

    def readinto(self, b):
        data = self.read(len(b))
        n = len(data)
        b[:n] = data
        return n

    def read_all(self):
        with self._lock:
            data = bytes(self._rx_buffer)
            self._rx_buffer.clear()
            return data

    def read_until(self, terminator=b"\n", size=None):
        if not self.is_open:
            raise SerialException("Attempt to read from closed port")

        deadline = None
        if self.timeout is not None:
            deadline = time.monotonic() + self.timeout

        with self._cond:
            while True:
                idx = self._rx_buffer.find(terminator)
                if idx != -1:
                    end = idx + len(terminator)
                    data = self._rx_buffer[:end]
                    del self._rx_buffer[:end]
                    return bytes(data)

                if size is not None and len(self._rx_buffer) >= size:
                    data = self._rx_buffer[:size]
                    del self._rx_buffer[:size]
                    return bytes(data)

                if self.timeout == 0:
                    return b""

                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return b""
                    self._cond.wait(remaining)
                else:
                    self._cond.wait()

    # -----------------------------
    # TX line handler
    # -----------------------------

    def _on_tx_event(self, line):
        """
        Handle TX line event by sending line to client.
        """
        self._pending_data = line

    # -----------------------------
    # RX loop thread
    # -----------------------------

    def _rx_loop(self):
        while self._running:
            try:
                data = self._sock.recv(4096)

                if not data:
                    continue

                # Acknowledge received data
                if data.upper() != f"{ACK}\n".encode(errors="replace"):
                    if DEBUG_ACKS:
                        print("Sending ACK...")
                    self._sock.send(f"{ACK}\n".encode(errors="replace"))
                if data.upper() == f"{ACK}\n".encode(errors="replace"):
                    if DEBUG_ACKS:
                        print("ACK received")
                    self._write_ack = True

                # Handle client id received
                if data.upper().startswith(
                        WHOAMI_REPLY.encode(errors="replace")):
                    if DEBUG_WHOAMI:
                        print(f"Received WHOAMI reply: {data}")
                    try:
                        # Store client ID from server: assigned, valid
                        self._client_id = int(data[len(WHOAMI_REPLY):])
                    except ValueError:
                        print("Failed to parse client ID passed from server")
                        self._client_id = -1  # assigned, but invalid

                with self._cond:
                    self._rx_buffer.extend(data)
                    self._cond.notify_all()
            except socket.timeout:
                continue
            except OSError as e:
                print(f"Receive error: {e}")
                break

        with self._cond:
            self._cond.notify_all()

        try:
            if self._running:
                self.close()
        except:
            pass

    # -----------------------------
    # TX heartbeat thread
    # -----------------------------

    def _tx_heartbeat(self):
        while self._running and self.heartbeat_interval:
            try:
                # Use short sleep to avoid blocking shutdown if heartbeat_interval is long
                wait_start = time.monotonic()
                while self._running and \
                        time.monotonic() - wait_start < self.heartbeat_interval:
                    time.sleep(0.1)  # Avoid spinning wheels

                if DEBUG_HEARTBEAT:
                    print("Sending heartbeat...")
                self.write(f"{HEARTBEAT}\n".encode(
                    errors="replace"))  # Send heartbeat
            except Exception as e:
                print(f"Heartbeat error: {e}")
                break
        print("Heartbeat thread exiting")
        try:
            if self._running:
                self.close()
        except:
            pass

    # -----------------------------
    # RX print thread (debug only)
    # -----------------------------

    def _rx_print_lines(self):
        while self._running:
            try:
                line = self.read_until(b"\n")
                text = line.decode(errors="replace").strip()
                if not line:
                    break
                if text.upper() not in CTRL_CMDS and \
                        not text.upper().startswith(WHOAMI_REPLY):
                    print("RX:", text)
                    self.rx_line.emit(text)  # Emit RX line event
            except Exception:
                break

    # -----------------------------
    # Start / Stop
    # -----------------------------

    def start(self):
        """
        Start client connection and data handling loop in background thread.
        """
        if not hasattr(self, '_client_thread'):
            self._client_thread = threading.Thread(
                target=self.run,
                daemon=True,
            )
        if not self._client_thread.is_alive():
            self._client_thread.start()

    def stop(self):
        """
        Stop client connection and data handling loop.
        """
        self._exit = True
        if hasattr(self, '_client_thread'):
            self._client_thread.join(timeout=1)

    # -----------------------------
    # Main client handling loop
    # -----------------------------

    def run(self):
        """
        Client connection and data handling loop.
        Manages connection attempts, retries, and data transmission.
        """
        self._exit = False
        self._pending_data = ""

        while not self._exit:
            try:
                print("Connecting to server...")
                self.open()
                if self.is_open:
                    if not self._pending_data:
                        self._pending_data = "HELLO"  # Send HELLO command on connect
                    print("Connected.")

                while not self._exit:
                    if not self.is_open:
                        if not self.auto_reconnect:
                            print("Connection closed, dropping client...")
                            self._exit = True
                            break
                        print("Re-connecting to server...")
                        try:
                            self.open()
                            if not self._pending_data:
                                self._pending_data = "HELLO"  # Send HELLO command on connect
                            print("Connected.")
                        except SerialException as e:
                            print(f"Connection failed: {e}")
                            if not self.auto_reconnect:
                                print("Exception occurred, dropping client...")
                                self._exit = True
                                break
                            if not self._pending_data:
                                self._pending_data = "RESET"  # Send RESET command on reconnect
                            time.sleep(2)
                            continue

                    if self._pending_data:
                        print("TX:", self._pending_data)
                        # Send each line up to 3 times, until bytes are waiting
                        for _ in range(3):
                            self.write(
                                (self._pending_data + "\n").encode(errors="replace"))
                            time.sleep(0.5)
                            if self._write_ack:
                                break
                        # Clear pending data after sending (whether sucessful or not)
                        if not self._write_ack:
                            print(
                                f"No ACK received for \"{self._pending_data}\". Transmission may have failed.")
                            self.rx_line.emit(f"NAK: {self._pending_data}")
                        self._pending_data = ""
                    else:
                        time.sleep(0.1)  # Avoid busy waiting

            except (OSError, SerialException) as e:
                print(f"Serial exception: {e}")
                if not self.auto_reconnect:
                    print("Exception occurred, dropping client...")
                    self._exit = True
                    break
                print("Exception occurred, restarting client...")
                if not self._pending_data:
                    self._pending_data = "RESET"  # Send RESET command on reconnect

            finally:
                try:
                    if self._running:
                        self.close()
                except:
                    pass
                    print("Connection not running.")


class Signal:
    """
    Lightweight Signal class for event handling.
    """

    def __init__(self):
        self._subscribers = []

    def connect(self, fn):
        self._subscribers.append(fn)

    def emit(self, *args, **kwargs):
        for fn in self._subscribers:
            fn(*args, **kwargs)


if __name__ == "__main__":

    try:

        # Simple test of TCP serial client
        client = TcpSerialServerPort(
            host="localhost", port=31950,
            timeout=None, write_timeout=None,
            heartbeat_interval=5, auto_reconnect=True)

        client.rx_line.connect(
            lambda line: print(f"Received line event: {line}"))

        client.start()  # Start client connection and handling loop

        # Listen for user input
        while not client._exit:
            line = input("Enter line to send (or 'close' or 'exit')...\n")
            if line.lower() == "client":
                print(f"Client ID is #{client.client_id}")
            elif line.lower() == "close":
                print("Close command received.")
                client.close()
            elif line.lower() == 'exit':
                print("Exit command received.")
                client.stop()
            elif len(line):
                client.tx_line.emit(line)

    except (OSError, SerialException) as e:
        print(f"Serial exception: {e}")
        print("Server not running?")

    finally:
        print("Exiting client demo.")
