from __future__ import annotations
from .base import Transport


class SerialTransport(Transport):
    """USB/serial transport (pyserial). An ethernet transport would be a
    sibling class with the same four methods, wrapping a socket."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 30.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser = None

    def open(self) -> None:
        import serial  # lazy import so pyserial is an optional dependency
        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def write_line(self, line: str) -> None:
        assert self._ser is not None, "transport not open"
        self._ser.write((line + "\n").encode("ascii"))

    def read_line(self, timeout: float | None = None) -> str:
        assert self._ser is not None, "transport not open"
        if timeout is not None:
            self._ser.timeout = timeout
        return self._ser.readline().decode("ascii", errors="replace").strip()
