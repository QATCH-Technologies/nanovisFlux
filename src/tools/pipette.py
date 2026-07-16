from typing import Optional

from src.common.motion import MotionController
from src.tools.base import Tool, register_tool
from src.utils.logger import logger


@register_tool("pipette")
class Pipette(Tool):
    DEFAULT_DROP_TIP_SPEED = 500.0

    def __init__(
        self,
        mount_axis: str,
        plunger_axis: str,
        max_volume: float,
        steps_per_ul: float,
        motion: MotionController,
        blowout_distance: float = 2.0,
        plunger_max_steps: Optional[float] = None,
        tip_pickup_presses: int = 3,
        tip_pickup_press_depth: float = 300.0,
        tip_pickup_press_speed: float = 300.0,
    ):
        super().__init__(mount_axis=mount_axis, motion=motion)
        self.axis = plunger_axis.upper()
        self.max_volume = max_volume
        self.steps_per_ul = steps_per_ul
        self.blowout_distance = blowout_distance
        self.plunger_max_steps = plunger_max_steps
        self.tip_pickup_presses = tip_pickup_presses
        self.tip_pickup_press_depth = tip_pickup_press_depth
        self.tip_pickup_press_speed = tip_pickup_press_speed
        self.current_volume: float = 0.0
        self.has_tip: bool = False

    @classmethod
    def from_config(cls, tool_data: dict, motion: MotionController) -> "Pipette":
        return cls(
            mount_axis=tool_data.get("mount_axis", ""),
            plunger_axis=tool_data.get("plunger_axis", ""),
            max_volume=tool_data.get("max_volume", 0.0),
            steps_per_ul=tool_data.get("steps_per_ul", 0),
            blowout_distance=tool_data.get("blowout_distance", 0),
            plunger_max_steps=tool_data.get("plunger_max_steps"),
            tip_pickup_presses=tool_data.get("tip_pickup_presses", 3),
            tip_pickup_press_depth=tool_data.get("tip_pickup_press_depth", 300.0),
            tip_pickup_press_speed=tool_data.get("tip_pickup_press_speed", 300.0),
            motion=motion,
        )

    def _check_plunger_limit(self, delta_steps: float) -> None:
        if self.plunger_max_steps is None:
            return
        current = self.motion.current_position.get(self.axis)
        if current is None:
            return  # not homed; MotionController's own homed-state check will raise on the move

        projected = current + delta_steps
        if projected >= self.plunger_max_steps:
            raise RuntimeError(
                f"Aspirate on axis {self.axis} would drive to {projected} steps, at or beyond "
                f"the tip-eject limit ({self.plunger_max_steps}). This position is reserved for "
                "drop_tip()."
            )

    def aspirate(self, volume: float, speed: Optional[float] = 300.0) -> None:

        if volume <= 0:
            raise ValueError("Aspiration volume must be greater than zero.")

        # TODO: Bring back once we know step to ul conversion!
        # if self.current_volume + volume > self.max_volume:
        #     raise ValueError(
        #         f"Cannot aspirate {volume}uL. Exceeds max volume "
        #         f"({self.max_volume}uL). Current: {self.current_volume}uL."
        #     )

        distance_steps = volume * self.steps_per_ul
        self._check_plunger_limit(distance_steps)
        logger.info(f"Aspirating {volume}uL ({distance_steps:.3f} steps) on axis {self.axis}.")

        self.motion.move_relative({self.axis: distance_steps}, speed=speed)
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
        distance_steps = -(volume * self.steps_per_ul)
        logger.info(f"Dispensing {volume}uL ({distance_steps:.3f} steps) on axis {self.axis}.")
        self.motion.move_relative({self.axis: distance_steps}, speed=speed)
        self.current_volume -= volume

    def blowout(self, speed: Optional[float] = 500.0) -> None:
        logger.info(f"Executing blowout on axis {self.axis}.")
        self.motion.move_relative({self.axis: -self.blowout_distance}, speed=speed)
        self.motion.move_absolute({self.axis: 0.0}, speed=speed)
        self.current_volume = 0.0

    def pick_up_tip(self, presses: Optional[int] = None) -> None:
        presses = presses if presses is not None else self.tip_pickup_presses
        logger.info(f"Picking up tip on {self.mount_axis} axis ({presses} presses).")

        for _ in range(presses):
            self.motion.move_relative(
                {self.mount_axis: self.tip_pickup_press_depth}, speed=self.tip_pickup_press_speed
            )
            self.motion.move_relative(
                {self.mount_axis: -self.tip_pickup_press_depth}, speed=self.tip_pickup_press_speed
            )

        self.has_tip = True
        logger.debug(f"Tip picked up on {self.mount_axis} axis.")

    def drop_tip(self, speed: Optional[float] = None) -> None:
        if self.plunger_max_steps is None:
            raise RuntimeError(
                f"plunger_max_steps not configured for axis {self.axis}; cannot execute drop_tip()."
            )

        logger.info(
            f"Dropping tip: driving axis {self.axis} to eject limit ({self.plunger_max_steps})."
        )
        self.motion.move_absolute(
            {self.axis: self.plunger_max_steps}, speed=speed or self.DEFAULT_DROP_TIP_SPEED
        )
        self.has_tip = False
        self.current_volume = 0.0
        logger.debug(f"Tip dropped on {self.axis} axis.")
