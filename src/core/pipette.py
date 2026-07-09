from typing import Optional

from src.core.motion import MotionController
from src.utils.logger import logger


class Pipette:
    def __init__(
        self,
        axis: str,
        max_volume: float,
        steps_per_ul: float,
        motion: MotionController,
        blowout_distance: float = 2.0,
    ):
        self.axis = axis.upper()
        self.max_volume = max_volume
        self.steps_per_ul = steps_per_ul
        self.motion = motion
        self.blowout_distance = blowout_distance
        self.current_volume: float = 0.0
        self.has_tip: bool = False

    def aspirate(self, volume: float, speed: Optional[float] = 300.0) -> None:

        if volume <= 0:
            raise ValueError("Aspiration volume must be greater than zero.")

        # TODO: Bring back once we know step to ul conversion!
        # if self.current_volume + volume > self.max_volume:
        #     raise ValueError(
        #         f"Cannot aspirate {volume}uL. Exceeds max volume "
        #         f"({self.max_volume}uL). Current: {self.current_volume}uL."
        #     )

        distance_mm = volume * self.steps_per_ul
        logger.info(f"Aspirating {volume}uL ({distance_mm:.3f}mm) on axis {self.axis}.")

        self.motion.move_relative({self.axis: distance_mm}, speed=speed)
        self.current_volume += volume

    def dispense(self, volume: float, speed: Optional[float] = 300.0) -> None:
        if volume <= 0:
            raise ValueError("Dispense volume must be greater than zero.")

        if volume > self.current_volume:
            logger.warning(
                f"Dispensing {volume}uL, but only {self.current_volume}uL tracked in tip. "
                "Dispensing remaining volume."
            )
            volume = self.current_volume
        distance_mm = -(volume * self.steps_per_ul)
        logger.info(f"Dispensing {volume}uL ({distance_mm:.3f}mm) on axis {self.axis}.")
        self.motion.move_relative({self.axis: distance_mm}, speed=speed)
        self.current_volume -= volume

    def blowout(self, speed: Optional[float] = 500.0) -> None:
        logger.info(f"Executing blowout on axis {self.axis}.")
        self.motion.move_relative({self.axis: -self.blowout_distance}, speed=speed)
        self.motion.move_absolute({self.axis: 0.0}, speed=speed)
        self.current_volume = 0.0

    def pick_up_tip(self) -> None:
        self.has_tip = True
        logger.debug(f"Tip picked up on {self.axis} axis.")

    def drop_tip(self) -> None:
        self.has_tip = False
        self.current_volume = 0.0
        logger.debug(f"Tip dropped on {self.axis} axis.")
