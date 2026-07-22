from __future__ import annotations
import socket
from .base import Transport


class EthernetTransport(Transport):
    """TCP/ethernet transport -- the network sibling of SerialTransport,
    same four methods, wrapping a socket instead of a serial port."""

    def __init__(self, host: str, port: int, timeout: float = 30.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._reader = None

    def open(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._reader = self._sock.makefile("r", newline="\n")

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def write_line(self, line: str) -> None:
        assert self._sock is not None, "transport not open"
        self._sock.sendall((line + "\n").encode("ascii"))

    def read_line(self, timeout: float | None = None) -> str:
        assert self._sock is not None, "transport not open"
        if timeout is not None:
            self._sock.settimeout(timeout)
        try:
            line = self._reader.readline()
        except OSError:
            return ""  # timed out / connection dropped
        return line.rstrip("\n") if line else ""
