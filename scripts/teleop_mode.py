from src.core.robot import Robot
from src.interfaces.keyboard_teleop import KeyboardTeleop
from src.utils.logger import logger
from tests.mock_connection import MockConnection


def run_mock_session():
    mock_conn = MockConnection()
    robot = Robot(port="MOCK", connection_override=mock_conn)
    logger.info("Starting Mock Teleop Session")

    try:
        robot.connect()
        teleop = KeyboardTeleop(robot)
        teleop.start()
    except Exception as e:
        logger.error(f"Session crashed: {e}")
    finally:
        robot.disconnect()


if __name__ == "__main__":
    run_mock_session()
