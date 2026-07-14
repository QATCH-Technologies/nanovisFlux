from typing import Dict, List, Optional

from src.utils.logger import logger

AXES = {
    "X",
    "Y",
    "Z",
    "A",
    "B",
}


class Dispatcher:
    @staticmethod
    def build_move_command(
        positions: Dict[str, int], speed: Optional[float] = None
    ) -> str:
        if not positions:
            raise ValueError("Move command requires at least one axis position.")

        command_parts = ["G1"]

        for axis in sorted(positions.keys()):
            axis_upper = axis.upper()
            if axis_upper not in AXES:
                raise ValueError(f"Invalid axis '{axis_upper}'. Must be one of {AXES}.")
            command_parts.append(f"{axis_upper}{positions[axis]:.3f}")

        if speed is not None:
            if speed <= 0:
                raise ValueError("Feedrate (speed) must be greater than zero.")
            command_parts.append(f"F{speed:.1f}")

        gcode = " ".join(command_parts)
        logger.debug(f"Built move command: {gcode}")
        return gcode

    @staticmethod
    def build_home_command(axes: Optional[List[str]] = None) -> str:
        if not axes:
            logger.debug("Built home command for all axes: G28")
            return "G28"

        command_parts = ["G28"]
        for axis in axes:
            axis_upper = axis.upper()
            if axis_upper not in AXES:
                raise ValueError(f"Invalid axis '{axis_upper}' for homing.")
            command_parts.append(axis_upper)
        command_parts.append("\n")

        gcode = " ".join(command_parts)
        logger.debug(f"Built home command: {gcode}")
        return gcode

    @staticmethod
    def build_probe_command(axis: str, target: int, speed: float) -> str:
        axis_upper = axis.upper()
        if axis_upper not in AXES:
            raise ValueError(f"Invalid probe axis '{axis_upper}'.")
        gcode = f"G38.2 {axis_upper}{target:.3f} F{speed:.1f}"
        logger.debug(f"Built probe command: {gcode}")
        return gcode

    @staticmethod
    def build_endstop_query_command() -> str:
        return "M119"

    @staticmethod
    def set_absolute_positioning() -> str:
        return "G90"

    @staticmethod
    def set_relative_positioning() -> str:
        return "G91"

    @staticmethod
    def build_emergency_stop() -> str:
        return "M112"

    @staticmethod
    def build_quick_stop() -> str:
        return "M410"

    @staticmethod
    def build_position_query() -> str:
        return "M114"
