"""
Abstract transport interface for line-oriented controller communication.

This module defines the :class:`Transport` abstraction used by the controller
layer to communicate with instrument firmware. A transport is responsible
only for opening and closing the communication channel and for sending and
receiving text lines; it does not interpret G-code or other controller
protocol semantics.

Concrete implementations can provide different physical communication
mechanisms, such as serial or TCP connections, without requiring changes to
higher-level controller code. A simulated or in-memory implementation can
similarly be used for testing.

The transport also supports context-manager usage and provides an optional
input-buffer reset operation for transports that maintain unread received
data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Transport(ABC):
    """Define the abstract interface for controller communication.

    A transport provides a line-oriented byte stream between the application
    and the instrument controller. It deliberately contains no knowledge of
    G-code, command semantics, response parsing, or controller state.

    Implementations are responsible for translating the abstract line
    operations into a specific communication mechanism, such as a serial
    connection, TCP socket, or test transport.

    The class supports context-manager usage so implementations can be opened
    and closed automatically around a block of controller operations.

    Subclasses must implement :meth:`open`, :meth:`close`, :meth:`write_line`,
    and :meth:`read_line`.

    Concrete implementations may override :meth:`reset_input_buffer` when
    their underlying communication channel provides a receive buffer that can
    be explicitly flushed.
    """

    @abstractmethod
    def open(self) -> None:
        """Open the underlying communication channel.

        Implementations should establish whatever connection or resource is
        required before commands can be transmitted.

        Raises:
            Exception: Implementations may raise an appropriate transport-specific
                exception if the connection cannot be established.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the underlying communication channel.

        Implementations should release any resources associated with the active
        transport connection. Calling this method should leave the transport in a
        state where it can be opened again if the implementation supports
        reconnection.
        """
        ...

    @abstractmethod
    def write_line(self, line: str) -> None:
        """Send one command line to the controller.

        The transport is responsible for appending the line terminator required
        by its underlying communication mechanism.

        Args:
            line: Command text to send without a trailing line terminator.
        """

    @abstractmethod
    def read_line(self, timeout: float | None = None) -> str:
        """Read one response line from the controller.

        The operation blocks until a complete response line is available or the
        specified timeout is reached. The returned string does not include the
        line-ending characters.

        Args:
            timeout: Maximum time to wait for a response, in seconds. `None`
                requests the transport's default blocking behavior.

        Returns:
            The received response line with its line terminator removed.

        Raises:
            Exception: Implementations may raise a transport-specific exception
                when the read fails or times out.
        """

    def reset_input_buffer(self) -> None:
        """Discard unread data currently buffered by the transport.

        The default implementation is a no-op because not every transport has an
        independently accessible receive buffer.

        Concrete byte-stream transports may override this method to flush unread
        input. This is useful after an operation that intentionally does not wait
        for a controller response, preventing a late response from being
        interpreted as the response to a subsequent command.
        """

    def __enter__(self) -> Transport:  # noqa
        """Open the transport when entering a context manager.

        Returns:
            The opened transport instance.
        """
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        """Close the transport when leaving a context manager.

        Args:
            *exc: Exception information supplied by the context-manager protocol.
        """
        self.close()
