import time
from typing import Optional

import serial

from src.hardware.base_connection import BaseConnection
from src.utils.logger import logger


class SerialConnection(BaseConnection):
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0) -> None:
        super().__init__(timeout)
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self.connect()

    def connect(self) -> None:
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(2.0)
            self.serial.reset_input_buffer()
            logger.info(
                f"Connected to OT-2 via Serial on port {self.port} at {self.baudrate} baud."
            )
        except serial.SerialException as e:
            logger.error(f"Failed to connect to OT-2 on {self.port}: {e}")
            raise

    def disconnect(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()
            logger.info(f"Disconnected from OT-2 on {self.port}.")

    def send_command(
        self, command: str, wait_for_ok: bool = True, timeout: Optional[float] = None
    ) -> str:
        if not self.serial or not self.serial.is_open:
            raise RuntimeError(f"Cannot send command. Port {self.port} is closed.")

        formatted_command = f"{command.strip()}\n".encode("utf-8")

        with self.lock:
            self.serial.write(formatted_command)
            logger.debug(f"Sent: {command.strip()}")
            if wait_for_ok:
                return self._wait_for_response(timeout)
            return ""

    def reset_input_buffer(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.reset_input_buffer()

    def _wait_for_response(self, timeout: Optional[float] = None) -> str:
        response_lines = []
        previous_timeout = self.serial.timeout
        if timeout is not None:
            self.serial.timeout = timeout

        try:
            while True and self.serial is not None:
                line = self.serial.readline().decode("utf-8").strip()

                if line:
                    response_lines.append(line)
                    logger.debug(f"Received: {line}")
                    line_lower = line.lower()
                    if (
                        line_lower == "ok"
                        or line_lower.startswith("not ok")
                        or line_lower.startswith("error")
                    ):
                        break
                else:
                    logger.warning(f"Timeout waiting for response from OT-2 on {self.port}.")
                    break
        finally:
            self.serial.timeout = previous_timeout

        return "\n".join(response_lines)
