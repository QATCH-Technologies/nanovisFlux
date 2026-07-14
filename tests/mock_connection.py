"""
Mock Connection Module for Testing
"""

import time
from typing import Optional

from src.utils.logger import logger

# Matches the firmware: C has no physical motor, so a bare G28 never homes it.
HOMEABLE_AXES = ["A", "Z", "X", "Y", "B"]


# A simple helper class to mimic pyserial's behavior
class FakeSerial:
    is_open = True

    def reset_input_buffer(self):
        pass


class MockConnection:
    def __init__(self, port="MOCK", baudrate=0):
        self.port = port
        self.baudrate = baudrate
        # This simulates the pyserial object that MotionController expects
        self.serial = self
        self.is_open = True

    def connect(self) -> None:
        logger.info("MOCK: Connection established (No hardware).")

    def disconnect(self) -> None:
        logger.info("MOCK: Connection closed.")

    def send_command(
        self, command: str, wait_for_ok: bool = True, timeout: Optional[float] = None
    ) -> str:
        logger.info(f"MOCK SEND: {command.strip()}")

        if command.startswith("G28"):
            return self._simulate_home(command)

        return "ok"

    def _simulate_home(self, command: str) -> str:
        """
        Mimics the real controller: it streams one 'Homed <axis>.' line at a
        time as each axis physically reaches its endstop (not all at once),
        then a final 'ok' once every requested axis has stopped moving.
        """
        requested = command.replace("G28", "").split()
        axes = [axis for axis in HOMEABLE_AXES if axis in requested] if requested else HOMEABLE_AXES

        lines = [f"Homing {' '.join(axes)}..."]
        for axis in axes:
            time.sleep(0.05)  # simulate real per-axis homing travel time
            lines.append(f"Homed {axis}.")
        lines.append("ok")

        return "\n".join(lines)

    def reset_input_buffer(self):
        logger.debug("MOCK: Input buffer reset.")
