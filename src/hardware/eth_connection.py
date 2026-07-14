import socket
from typing import Optional

from src.hardware.base_connection import BaseConnection
from src.utils.logger import logger


class ETHConnection(BaseConnection):
    def __init__(self, host: str, port: int = 3333, timeout: float = 1.0) -> None:
        super().__init__(timeout)
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connect()

    def connect(self) -> None:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            logger.info(f"Connected to OT-2 via Ethernet at {self.host}:{self.port}.")
        except (socket.error, socket.timeout) as e:
            logger.error(f"Failed to connect to OT-2 at {self.host}:{self.port}: {e}")
            if self.socket:
                self.socket.close()
            raise

    def disconnect(self) -> None:
        if self.socket:
            self.socket.close()
            logger.info(f"Disconnected from OT-2 at {self.host}:{self.port}.")

    def send_command(self, command: str, wait_for_ok: bool = True) -> str:
        if not self.socket:
            raise RuntimeError(f"Cannot send command. Connection to {self.host} is closed.")

        formatted_command = f"{command.strip()}\n".encode("utf-8")

        with self.lock:
            try:
                self.socket.sendall(formatted_command)
                logger.debug(f"Sent: {command.strip()}")
                if wait_for_ok:
                    return self._wait_for_response()
            except socket.error as e:
                logger.error(f"Socket error while sending command: {e}")
                raise
            return ""

    def _wait_for_response(self) -> str:
        response_lines = []
        buffer = ""

        while True and self.socket is not None:
            try:
                data = self.socket.recv(1024).decode("utf-8")
                if not data:
                    logger.warning(f"Connection closed by server at {self.host}.")
                    break

                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if line:
                        response_lines.append(line)
                        logger.debug(f"Received: {line}")
                        if line.lower().startswith("ok") or line.lower().startswith("error"):
                            return "\n".join(response_lines)

            except socket.timeout:
                logger.warning(f"Timeout waiting for response from OT-2 at {self.host}.")
                break
            except socket.error as e:
                logger.error(f"Socket error reading response: {e}")
                break

        return "\n".join(response_lines)
