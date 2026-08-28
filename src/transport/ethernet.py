"""
TCP/ethernet transport for line-oriented controller communication.

This module provides :class:`EthernetTransport`, a concrete
:class:`~.base.Transport` implementation that communicates with an
instrument controller over a TCP socket.

The transport exposes the same line-oriented interface as other transport
implementations, allowing higher-level controller code to remain independent
of the underlying communication medium. Commands are encoded as ASCII and
terminated with a newline before transmission, while received lines are
returned without their trailing newline.

The connection uses a socket-backed text reader for response handling and
supports configurable connection and read timeouts.
"""

from __future__ import annotations

import socket

from .base import Transport


class EthernetTransport(Transport):
    """Provide line-oriented communication with a controller over TCP.

    `EthernetTransport` implements the generic :class:`Transport` interface
    using a TCP socket. It is intended to provide network-based controller
    communication with the same interface used by serial and test transports.

    Commands are encoded as ASCII and transmitted with a newline terminator.
    Responses are read one line at a time and returned without the trailing
    newline.

    Args:
        host: Hostname or IP address of the controller.
        port: TCP port on which the controller is listening.
        timeout: Default socket connection timeout in seconds.

    Attributes:
        host: Controller hostname or IP address.
        port: Controller TCP port.
        timeout: Default connection timeout in seconds.
    """

    def __init__(self, host: str, port: int, timeout: float = 30.0):
        """Initialize an ethernet transport.

        The TCP connection is not established until :meth:`open` is called.

        Args:
            host: Hostname or IP address of the controller.
            port: TCP port on which the controller is listening.
            timeout: Socket connection timeout in seconds.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._reader = None

    def open(self) -> None:
        """Establish the TCP connection to the controller.

        A socket connection is created using the configured host, port, and
        timeout. A newline-delimited text reader is then created for receiving
        controller responses.

        Raises:
            OSError: If the TCP connection cannot be established.
            socket.timeout: If the connection attempt exceeds the configured
                timeout.
        """
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._reader = self._sock.makefile("r", newline="\n")

    def close(self) -> None:
        """Close the TCP connection and associated response reader.

        Closing is safe when the transport is already closed. The internal reader
        and socket references are cleared after their respective resources are
        closed.
        """
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def write_line(self, line: str) -> None:
        """Send one ASCII-encoded command line to the controller.

        A newline terminator is appended to `line` before transmission.

        Args:
            line: Command text to send without a trailing newline.

        Raises:
            AssertionError: If the transport has not been opened.
            OSError: If the command cannot be transmitted.
            UnicodeEncodeError: If `line` contains characters that cannot be
                encoded as ASCII.
        """
        assert self._sock is not None, "transport not open"
        self._sock.sendall((line + "\n").encode("ascii"))

    def read_line(self, timeout: float | None = None) -> str:
        """Read one response line from the controller.

        When a timeout is supplied, it is applied to the underlying socket before
        reading. Socket errors, including timeouts or a dropped connection, are
        treated as an empty response.

        Args:
            timeout: Optional read timeout in seconds. If omitted, the socket's
                existing timeout configuration is used.

        Returns:
            The received response line with its trailing newline removed, or an
            empty string if the read times out, fails, or the connection reaches
            EOF.

        Raises:
            AssertionError: If the transport has not been opened.
        """
        assert self._sock is not None, "transport not open"
        if timeout is not None:
            self._sock.settimeout(timeout)
        try:
            assert self._reader is not None, "_reader is not initialized"
            line = self._reader.readline()
        except OSError:
            return ""  # timed out / connection dropped
        return line.rstrip("\n") if line else ""
