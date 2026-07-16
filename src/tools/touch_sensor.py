from typing import Optional

from src.common.motion import MotionController
from src.tools.base import Tool, register_tool
from src.utils.logger import logger

# Digital pin wired to the touch probe (PROBE_TOUCH) on the OT2 stepper
# controller firmware. Queried via the M411 debug-read command.
DEFAULT_PROBE_PIN = 35


@register_tool("touch_sensor")
class TouchSensor(Tool):
    def __init__(
        self, mount_axis: str, motion: MotionController, probe_pin: int = DEFAULT_PROBE_PIN
    ):
        super().__init__(mount_axis=mount_axis, motion=motion)
        self.probe_pin = probe_pin

    @classmethod
    def from_config(cls, tool_data: dict, motion: MotionController) -> "TouchSensor":
        kwargs = {"mount_axis": tool_data.get("mount_axis", ""), "motion": motion}
        if "probe_pin" in tool_data:
            kwargs["probe_pin"] = tool_data["probe_pin"]
        return cls(**kwargs)

    def probe(self, target_depth: int, speed: float = 100.0) -> Optional[float]:
        logger.info(f"Probing on axis {self.mount_axis} towards {target_depth}...")

        response = self.motion.probe(self.mount_axis, target_depth, speed, probe_type="38.2")

        if "not ok" in response.lower():
            logger.error(f"Probe failed to find surface before reaching {target_depth}.")
            return None

        logger.info("Surface detected.")

        self.motion.move_relative({self.mount_axis: 5}, speed=500.0)
        return self.motion.current_position[self.mount_axis]

    def is_active(self) -> bool:
        response = self.motion.query_debug_info(str(self.probe_pin))
        is_active = "high" in response.lower()
        state_str = "TRIGGERED" if is_active else "OPEN"
        logger.debug(f"Sensor state on {self.mount_axis}: {state_str}")
        return is_active
