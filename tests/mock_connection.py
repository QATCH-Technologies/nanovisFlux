"""
Mock Connection Module for Testing
"""

from src.utils.logger import logger


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

    def send_command(self, command: str, wait_for_ok: bool = True) -> str:
        logger.info(f"MOCK SEND: {command.strip()}")
        return "ok"

    def reset_input_buffer(self):
        logger.debug("MOCK: Input buffer reset.")
