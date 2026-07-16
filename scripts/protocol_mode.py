from src.core.deck import DeckLocation
from src.core.robot import Robot
from src.utils.logger import logger


def protocol_runner():

    robot = Robot()
    logger.info("Starting Protocol Session")

    try:
        loc = DeckLocation(slot_id="11", x_mm=100, y_mm=100, z_mm=100)
        robot.move_to_location(location=loc, mount="left", speed=2000.0)
    except Exception as e:
        logger.error(f"Session crashed: {e}")
    finally:
        robot.disconnect()


if __name__ == "__init__":
    protocol_runner()
