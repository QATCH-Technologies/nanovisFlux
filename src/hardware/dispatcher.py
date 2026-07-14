import re
from typing import Dict, List, Optional

from src.utils.logger import logger

AXES = {
    "X",
    "Y",
    "Z",
    "A",
    "B",
    "C",  # Added C as protocol.md lists it in the coordinate system
}

_HOMED_AXIS_RE = re.compile(r"(?i)Homed\s+([A-Z])\.")


class CommandError(Exception):
    """Raised when the controller reports a failed or malformed response to a command."""


class Dispatcher:
    @staticmethod
    def _build_axis_args(values: Dict[str, int]) -> str:
        """Helper to build standard 'X100 Y50 Z10' argument strings."""
        parts = []
        for axis in sorted(values.keys()):
            axis_upper = axis.upper()
            if axis_upper not in AXES:
                raise ValueError(f"Invalid axis '{axis_upper}'. Must be one of {AXES}.")
            parts.append(f"{axis_upper}{values[axis]}")
        return " ".join(parts)

    # --- Motion Commands ---

    @staticmethod
    def build_rapid_move_command(positions: Dict[str, int]) -> str:
        if not positions:
            raise ValueError("Rapid move command requires at least one axis position.")

        gcode = f"G0 {Dispatcher._build_axis_args(positions)}"
        logger.debug(f"Built rapid move command: {gcode}")
        return gcode

    @staticmethod
    def build_move_command(positions: Dict[str, int], speed: Optional[int] = None) -> str:
        if not positions:
            raise ValueError("Move command requires at least one axis position.")

        command_parts = ["G1", Dispatcher._build_axis_args(positions)]

        if speed is not None:
            if speed <= 0:
                raise ValueError("Feedrate (speed) must be greater than zero.")
            command_parts.append(f"F{speed}")

        gcode = " ".join(command_parts)
        logger.debug(f"Built move command: {gcode}")
        return gcode

    # --- Homing Commands ---

    @staticmethod
    def build_home_command(axes: Optional[List[str]] = None) -> str:
        if not axes:
            gcode = "G28"
            logger.debug(f"Built home command for all axes: {gcode}")
            return gcode

        valid_axes = []
        for axis in axes:
            axis_upper = axis.upper()
            if axis_upper not in AXES:
                raise ValueError(f"Invalid axis '{axis_upper}' for homing.")
            valid_axes.append(axis_upper)

        gcode = f"G28 {' '.join(valid_axes)}"
        logger.debug(f"Built home command: {gcode}")
        return gcode

    # --- Probing Commands ---

    @staticmethod
    def build_probe_command(axis: str, target: int, speed: int, probe_type: str = "38.2") -> str:
        """
        probe_type:
        '38.2' (Toward, Error on Failure)
        '38.3' (Toward, No Error)
        '38.4' (Away, Error on Failure)
        '38.5' (Away, No Error)
        """
        valid_types = {"38.2", "38.3", "38.4", "38.5"}
        if probe_type not in valid_types:
            raise ValueError(f"Invalid probe type '{probe_type}'. Must be one of {valid_types}.")

        axis_upper = axis.upper()
        if axis_upper not in AXES:
            raise ValueError(f"Invalid probe axis '{axis_upper}'.")

        gcode = f"G{probe_type} {axis_upper}{target} F{speed}"
        logger.debug(f"Built probe command: {gcode}")
        return gcode

    # --- Configuration Commands ---

    @staticmethod
    def build_set_hard_limits_command(limits: Dict[str, int]) -> str:
        if not limits:
            raise ValueError("Requires at least one axis to set hard limits.")
        gcode = f"M201 {Dispatcher._build_axis_args(limits)}"
        logger.debug(f"Built set hard limits command: {gcode}")
        return gcode

    @staticmethod
    def build_set_accelerations_command(accels: Dict[str, int]) -> str:
        if not accels:
            raise ValueError("Requires at least one axis to set accelerations.")
        gcode = f"M204 {Dispatcher._build_axis_args(accels)}"
        logger.debug(f"Built set accelerations command: {gcode}")
        return gcode

    @staticmethod
    def build_set_homing_speeds_command(speeds: Dict[str, int]) -> str:
        if not speeds:
            raise ValueError("Requires at least one axis to set homing speeds.")
        gcode = f"M210 {Dispatcher._build_axis_args(speeds)}"
        logger.debug(f"Built set homing speeds command: {gcode}")
        return gcode

    @staticmethod
    def build_set_travel_speeds_command(speeds: Dict[str, int]) -> str:
        if not speeds:
            raise ValueError("Requires at least one axis to set travel speeds.")
        gcode = f"M220 {Dispatcher._build_axis_args(speeds)}"
        logger.debug(f"Built set travel speeds command: {gcode}")
        return gcode

    @staticmethod
    def build_set_homing_retraction_command(distances: Dict[str, int]) -> str:
        if not distances:
            raise ValueError("Requires at least one axis to set homing retraction distance.")
        gcode = f"M421 {Dispatcher._build_axis_args(distances)}"
        logger.debug(f"Built set homing retraction command: {gcode}")
        return gcode

    # --- State and Positioning Modes ---

    @staticmethod
    def set_absolute_positioning() -> str:
        logger.debug("Built absolute positioning command: G90")
        return "G90"

    @staticmethod
    def set_relative_positioning() -> str:
        logger.debug("Built relative positioning command: G91")
        return "G91"

    # --- Status Commands ---

    @staticmethod
    def build_position_query() -> str:
        return "M114"

    @staticmethod
    def build_debug_info_command(pin: str) -> str:
        gcode = f"M411 READ {pin}"
        logger.debug(f"Built debug info command: {gcode}")
        return gcode

    # --- Response Validation ---

    @staticmethod
    def validate_response(response: str, command: str = "") -> str:
        """
        Validates a raw device response against the OT2 serial protocol, which
        always terminates a command with a final 'ok' or 'NOT ok' line.
        Raises CommandError if the command failed or the response was
        truncated (e.g. by a read timeout) before a terminal line arrived.
        """
        lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
        if not lines:
            raise CommandError(
                f"No response received for command '{command}'. The device may be "
                "unreachable, or the read timed out before 'ok' was received."
            )

        last_line = lines[-1].lower()
        if last_line.startswith("not ok"):
            raise CommandError(f"Command '{command}' failed: {lines[-1]}")
        if last_line != "ok":
            raise CommandError(
                f"Command '{command}' did not terminate with 'ok'. The response may "
                f"have been truncated by a read timeout. Received: {response!r}"
            )

        return response

    @staticmethod
    def validate_home_response(response: str, requested_axes: Optional[List[str]] = None) -> List[str]:
        """
        Validates a G28 response and returns the axes the firmware actually
        confirmed via 'Homed <axis>.' lines.

        If requested_axes is given (an explicit subset was homed), every
        requested axis must be confirmed or a CommandError is raised. If
        requested_axes is None (a full 'home all' was issued), whatever the
        firmware confirms is accepted as-is, since not every axis necessarily
        has homing hardware.
        """
        Dispatcher.validate_response(response, "G28")

        homed_axes = sorted({axis.upper() for axis in _HOMED_AXIS_RE.findall(response)})

        if requested_axes:
            missing = [axis for axis in requested_axes if axis.upper() not in homed_axes]
            if missing:
                raise CommandError(
                    f"Homing did not confirm axes {missing}. Device reported: {response!r}"
                )

        return homed_axes

    # --- Emergency and Control Commands ---

    @staticmethod
    def build_quick_stop() -> str:
        logger.debug("Built quick stop command: M410")
        return "M410"

    @staticmethod
    def build_emergency_stop() -> str:
        logger.warning("Built emergency stop command: M112")
        return "M112"

    @staticmethod
    def build_reset_controller_command() -> str:
        logger.warning("Built reset controller command: M30")
        return "M30"

    @staticmethod
    def build_disable_blocking_limits_command() -> str:
        logger.warning("Built disable blocking limits command: M911")
        return "M911"
