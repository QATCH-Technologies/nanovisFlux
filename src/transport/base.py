from __future__ import annotations
from abc import ABC, abstractmethod


class Transport(ABC):
    """A line-oriented byte pipe to the controller.

    Deliberately knows nothing about G-code: it only moves text lines.
    Swap SerialTransport for a TCPTransport (ethernet) or FakeTransport
    (tests) without touching any layer above.
    """

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def write_line(self, line: str) -> None:
        """Send one command line (the newline is appended by the transport)."""

    @abstractmethod
    def read_line(self, timeout: float | None = None) -> str:
        """Block for and return one response line, stripped of EOL."""

    def __enter__(self) -> "Transport":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
