"""
USB/serial transport for line-oriented controller communication.

This module provides :class:`SerialTransport`, a concrete
:class:`~.base.Transport` implementation backed by a pyserial connection.

The transport communicates with the controller using newline-delimited ASCII
text. The :mod:`serial` dependency is imported lazily when the connection is
opened, allowing pyserial to remain an optional dependency for applications
that use another transport implementation.

The transport also exposes input-buffer flushing so unread controller
responses can be discarded when required by higher-level command handling.
"""

from __future__ import annotations

from .base import Transport


class SerialTransport(Transport):
    """Provide line-oriented communication with a controller over USB/serial.

    `SerialTransport` implements the generic :class:`Transport` interface
    using a pyserial connection. Commands are encoded as ASCII and terminated
    with a newline before transmission. Responses are read one line at a time
    and decoded as ASCII with replacement for invalid byte sequences.

    The pyserial dependency is imported lazily by :meth:`open`, allowing
    modules that define or use other transport implementations to operate
    without importing pyserial at module import time.

    Args:
        port: Serial port identifier, such as `"COM3"` or `"/dev/ttyUSB0"`.
        baudrate: Serial communication speed in bits per second.
        timeout: Default serial read timeout in seconds.

    Attributes:
        port: Configured serial port identifier.
        baudrate: Configured communication speed.
        timeout: Default read timeout in seconds.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 30.0):
        """Initialize a serial transport.

        The serial connection is not opened until :meth:`open` is called.

        Args:
            port: Serial port identifier.
            baudrate: Serial communication speed in bits per second.
            timeout: Default serial read timeout in seconds.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser = None

    def open(self) -> None:
        """Open the configured serial connection.

        The pyserial package is imported only when this method is called so that
        it remains an optional dependency for applications using other transport
        implementations.

        Raises:
            ImportError: If pyserial is not installed.
            serial.SerialException: If the serial port cannot be opened.
        """
        import serial

        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def close(self) -> None:
        """Close the serial connection.

        The method is safe to call when the transport is already closed. After
        closing, the internal serial connection reference is cleared.
        """
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def write_line(self, line: str) -> None:
        """Send one ASCII-encoded command line to the controller.

        A newline terminator is appended to `line` before transmission.

        Args:
            line: Command text to send without a trailing newline.

        Raises:
            AssertionError: If the transport has not been opened.
            UnicodeEncodeError: If `line` contains characters that cannot be
                encoded as ASCII.
            serial.SerialException: If the command cannot be transmitted.
        """
        assert self._ser is not None, "transport not open"
        self._ser.write((line + "\n").encode("ascii"))

    def read_line(self, timeout: float | None = None) -> str:
        """Read one response line from the controller.

        If `timeout` is provided, it temporarily updates the serial connection's
        read timeout before reading. The received bytes are decoded as ASCII,
        replacing invalid byte sequences, and surrounding whitespace is removed.

        Args:
            timeout: Optional read timeout in seconds. If omitted, the currently
                configured serial timeout is used.

        Returns:
            The decoded response line with surrounding whitespace removed.

        Raises:
            AssertionError: If the transport has not been opened.
            serial.SerialException: If the serial read fails.
        """
        assert self._ser is not None, "transport not open"
        if timeout is not None:
            self._ser.timeout = timeout
        return self._ser.readline().decode("ascii", errors="replace").strip()

    def reset_input_buffer(self) -> None:
        """Discard unread bytes currently buffered by the serial connection.

        If the transport is closed, this method performs no operation.
        """
        if self._ser is not None:
            self._ser.reset_input_buffer()
