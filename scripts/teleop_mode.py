from src.core.robot import Robot
from src.interfaces.keyboard_teleop import KeyboardTeleop
from src.utils.logger import logger
from tests.mock_connection import MockConnection

SESION_TYPE = "real"  # ddwads mock or real


def run_mock_session():
    mock_conn = MockConnection()
    robot = Robot(port="MOCK", connection_override=mock_conn)
    logger.info("Starting Mock Teleop Session")

    try:
        # robot.connect()
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
        # robot.connect()
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
