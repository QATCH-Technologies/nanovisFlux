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
    def send_command(self, command: str, wait_for_ok: bool = True) -> str:
        pass

    @abstractmethod
    def reset_input_buffer(self) -> None:
        pass
