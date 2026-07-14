from typing import Optional

from src.core.motion import MotionController
from src.hardware.dispatcher import Dispatcher
from src.utils.logger import logger


class TouchSensor:
    def __init__(self, mount_axis: str, motion: MotionController):
        self.mount_axis = mount_axis.upper()
        self.motion = motion

    def probe(self, target_depth: int, speed: float = 100.0) -> Optional[float]:
        logger.info(f"Probing on axis {self.mount_axis} towards {target_depth}...")
        self.motion._set_absolute_mode()

        probe_cmd = Dispatcher.build_probe_command(self.mount_axis, target_depth, speed)
        response = self.motion.connection.send_command(probe_cmd)

        if "error" in response.lower():
            logger.error(f"Probe failed to find surface before reaching {target_depth}.")
            return None

        logger.info("Surface detected.")

        self.motion.move_relative({self.mount_axis: 5}, speed=500.0)
        return self.motion.current_position[self.mount_axis]

    def is_active(self) -> bool:
        query_cmd = Dispatcher.build_endstop_query_command()
        response = self.motion.connection.send_command(query_cmd)
        is_active = "triggered" in response.lower()
        state_str = "TRIGGERED" if is_active else "OPEN"
        logger.debug(f"Sensor state on {self.mount_axis}: {state_str}")
        return is_active
