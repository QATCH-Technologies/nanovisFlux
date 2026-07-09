import threading
import time
from typing import Optional

import serial

from src.utils.logger import logger


class Connection:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0) -> None:
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
            logger.info(f"Connected to OT-2 on port {self.port} at {self.baudrate} baud.")

        except serial.SerialException as e:
            logger.error(f"Failed to connect to OT-2 on {self.port}: {e}")
            raise

    def disconnect(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()
            logger.info(f"Disconnected from OT-2 on {self.port}.")

    def send_command(self, command: str, wait_for_ok: bool = True) -> str:
        if not self.serial or not self.serial.is_open:
            raise RuntimeError(f"Cannot send command. Port {self.port} is closed.")
        formatted_command = f"{command.strip()}\n".encode("utf-8")

        with self.lock:
            self.serial.write(formatted_command)
            logger.debug(f"Sent: {command.strip()}")

            if wait_for_ok:
                return self._wait_for_response()
            return ""

    def _wait_for_response(self) -> str:
        response_lines = []
        while True and self.serial is not None:
            line = self.serial.readline().decode("utf-8").strip()

            if line:
                response_lines.append(line)
                logger.debug(f"Received: {line}")

                if line.lower().startswith("ok") or line.lower().startswith("error"):
                    break
            else:
                logger.warning(f"Timeout waiting for response from OT-2 on {self.port}.")
                break
        return "\n".join(response_lines)
