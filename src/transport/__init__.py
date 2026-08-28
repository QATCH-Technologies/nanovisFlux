"""Transport implementations for communicating with the motion controller.

This package defines the transport abstraction used by the controller layer
and provides concrete implementations for physical and simulated
communication.

The public API includes:

* :class:`Transport` -- abstract line-oriented communication interface.
* :class:`SerialTransport` -- USB/serial transport implemented with
  `pyserial`.
* :class:`SimulatedTransport` -- in-memory controller simulation for tests,
  development, and examples.

Higher-level protocol and motion code depends only on :class:`Transport`,
allowing the underlying communication mechanism to be replaced without
changing controller behavior.
"""

from .base import Transport
from .serial import SerialTransport
from .simulated import SimulatedTransport

__all__ = ["SerialTransport", "SimulatedTransport", "Transport"]
