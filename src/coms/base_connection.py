import socket
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

import serial

from src.utils.logger import logger


class BaseConnection(ABC):
    """Abstract interface enforcing the contract for all connection types."""

    def __init__(self, timeout: float = 1.0) -> None:
        self.timeout = timeout
        self.lock = threading.Lock()

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def send_command(
        self, command: str, wait_for_ok: bool = True, timeout: Optional[float] = None
    ) -> str:
        """
        timeout overrides the connection's default read timeout for this call
        only. Some commands (e.g. G28) stream one response line per axis with
        real hardware delays between them that can exceed the default
        short-command timeout, so callers that know this (MotionController)
        can widen the window without affecting every other command.
        """
        pass

    @abstractmethod
    def reset_input_buffer(self) -> None:
        pass
