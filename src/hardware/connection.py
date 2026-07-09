import threading
import time
from typing import Dict, Optional

import serial

from utils.logger import logger


class Connection:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None
        self.lock = threading.Lock()

    def connect(self) -> None:
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(2.0)
            self.serial.reset_input_buffer()
            logger.info(f"Connected to {self.port} at {self.baudrate} baud.")
        except serial.SerialException as e:
            logger.error(f"Failed to connect to {self.port}: {e}")
            raise

    def disconnect(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()
            logger.info(f"Disconnected from {self.port}.")

    def send_command(self, command: str, wait_for_ok: bool = True) -> str:
        if not self.serial or not self.serial.is_open:
            raise RuntimeError(f"Cannot send command. Port {self.port} is closed.")
        formatted_command = f"{command.strip()}\n".encode("utf-8")

        with self.lock:
            self.serial.write(formatted_command)
            logger.debug(f"Sent to {self.port}: {command.strip()}")

            if wait_for_ok:
                return self._wait_for_response()
            return ""

    def _wait_for_response(self) -> str:
        """Reads from the serial buffer until an 'ok' or 'error' is received."""
        response_lines = []
        while True:
            line = self.serial.readline().decode("utf-8").strip()

            if line:
                response_lines.append(line)
                logger.debug(f"Received from {self.port}: {line}")

                # Standard G-code controller success/failure markers
                if line.lower().startswith("ok") or line.lower().startswith("error"):
                    break
            else:
                # Readline timeout occurred
                logger.warning(f"Timeout waiting for response on {self.port}.")
                break

        return "\n".join(response_lines)


class ConnectionManager:
    def __init__(self, hardware_config: Dict[str, Dict[str, any]]):
        """
        Initializes the manager with a configuration dictionary.

        Example config format:
        {
            'X': {'port': '/dev/ttyUSB0', 'baudrate': 115200},
            'Y': {'port': '/dev/ttyUSB1', 'baudrate': 115200},
            'Z': {'port': '/dev/ttyUSB2', 'baudrate': 115200},
            'P': {'port': '/dev/ttyUSB3', 'baudrate': 115200}
        }
        """
        self.controllers: Dict[str, Connection] = {}

        for axis, settings in hardware_config.items():
            self.controllers[axis] = Connection(
                port=settings["port"], baudrate=settings.get("baudrate", 115200)
            )

    def connect_all(self) -> None:
        """Iterates through all configured axes and establishes connections."""
        for axis, conn in self.controllers.items():
            logger.info(f"Initializing {axis}-axis controller...")
            conn.connect()

    def disconnect_all(self) -> None:
        """Safely disconnects all controllers."""
        for axis, conn in self.controllers.items():
            conn.disconnect()

    def get_axis(self, axis: str) -> Connection:
        """Retrieves the connection object for a specific axis."""
        if axis not in self.controllers:
            raise ValueError(f"No connection configured for axis: '{axis}'. Check config.")
        return self.controllers[axis]
