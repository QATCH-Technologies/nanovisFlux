from src.common.robot import Robot
from src.core.deck import DeckLocation
from src.utils.logger import logger


def protocol_runner():

    robot = Robot()
    logger.info("Starting Protocol Session")

    try:
        loc = DeckLocation(
            slot_id="1",
        )
        robot.move_to_location(location=loc, mount="left", speed=3000.0)
    except Exception as e:
        logger.error(f"Session crashed: {e}")
    finally:
        robot.disconnect()


if __name__ == "__main__":
    protocol_runner()
