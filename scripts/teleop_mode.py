from src.core.robot import Robot
from src.interfaces.gamepad_teleop import GamepadTeleop
from src.interfaces.keyboard_teleop import KeyboardTeleop
from src.utils.logger import logger
from tests.mock_connection import MockConnection

SESION_TYPE = "real"  # mock or real
SCHEME = "gamepad"  # keyboard or gamepad


def run_mock_session():
    mock_conn = MockConnection()
    robot = Robot(port="MOCK", connection_override=mock_conn)
    logger.info("Starting Mock Teleop Session")

    try:
        if SCHEME == "gamepad":
            teleop = GamepadTeleop(robot)
        else:
            teleop = KeyboardTeleop(robot)
        teleop.start()
    except Exception as e:
        logger.error(f"Session crashed: {e}")
    finally:
        robot.disconnect()


def run_session():
    robot = Robot()
    logger.info("Starting Teleop Session")

    try:
        if SCHEME == "gamepad":
            teleop = GamepadTeleop(robot)
        else:
            teleop = KeyboardTeleop(robot)
        teleop.start()
    except Exception as e:
        logger.error(f"Session crashed: {e}")
    finally:
        robot.disconnect()


if __name__ == "__main__":
    if SESION_TYPE == "real":
        run_session()
    elif SESION_TYPE == "mock":
        run_mock_session()
