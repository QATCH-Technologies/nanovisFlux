import re
from typing import Dict, List, Optional

from src.backend.commands import (
    AXES,
    AxisCommand,
    DebugInfoCommand,
    HomeCommand,
    ProbeCommand,
    SimpleCommand,
)
from src.utils.logger import logger

_HOMED_AXIS_RE = re.compile(r"(?i)Homed\s+([A-Z])\.")


class CommandError(Exception):
    """Raised when the controller reports a failed or malformed response to a command."""


class Dispatcher:
    @staticmethod
    def _normalize_axis_values(values: Dict[str, int]) -> Dict[str, int]:
        """Sorts on the ORIGINAL (possibly mixed-case) keys before
        uppercasing, exactly matching the legacy _build_axis_args ordering,
        then hands off an already-normalized dict for Command to validate."""
        normalized = {}
        for axis in sorted(values.keys()):
            axis_upper = axis.upper()
            if axis_upper not in AXES:
                raise ValueError(f"Invalid axis '{axis_upper}'. Must be one of {AXES}.")
            normalized[axis_upper] = values[axis]
        return normalized

    # --- Motion Commands ---

    @staticmethod
    def build_rapid_move_command(positions: Dict[str, int]) -> AxisCommand:
        if not positions:
            raise ValueError("Rapid move command requires at least one axis position.")

        command = AxisCommand(code="G0", axis_values=Dispatcher._normalize_axis_values(positions))
        logger.debug(f"Built rapid move command: {command}")
        return command

    @staticmethod
    def build_move_command(positions: Dict[str, int], speed: Optional[int] = None) -> AxisCommand:
        if not positions:
            raise ValueError("Move command requires at least one axis position.")
        if speed is not None and speed <= 0:
            raise ValueError("Feedrate (speed) must be greater than zero.")

        command = AxisCommand(
            code="G1", axis_values=Dispatcher._normalize_axis_values(positions), feed_rate=speed
        )
        logger.debug(f"Built move command: {command}")
        return command

    # --- Homing Commands ---

    @staticmethod
    def build_home_command(axes: Optional[List[str]] = None) -> HomeCommand:
        if not axes:
            command = HomeCommand()
            logger.debug(f"Built home command for all axes: {command}")
            return command

        valid_axes = []
        for axis in axes:
            axis_upper = axis.upper()
            if axis_upper not in AXES:
                raise ValueError(f"Invalid axis '{axis_upper}' for homing.")
            valid_axes.append(axis_upper)

        command = HomeCommand(axes=tuple(valid_axes))
        logger.debug(f"Built home command: {command}")
        return command

    # --- Probing Commands ---

    @staticmethod
    def build_probe_command(
        axis: str, target: int, speed: int, probe_type: str = "38.2"
    ) -> ProbeCommand:
        """
        probe_type:
        '38.2' (Toward, Error on Failure)
        '38.3' (Toward, No Error)
        '38.4' (Away, Error on Failure)
        '38.5' (Away, No Error)
        """
        axis_upper = axis.upper()
        command = ProbeCommand(axis=axis_upper, target=target, speed=speed, probe_type=probe_type)
        logger.debug(f"Built probe command: {command}")
        return command

    # --- Configuration Commands ---

    @staticmethod
    def build_set_hard_limits_command(limits: Dict[str, int]) -> AxisCommand:
        if not limits:
            raise ValueError("Requires at least one axis to set hard limits.")
        command = AxisCommand(code="M201", axis_values=Dispatcher._normalize_axis_values(limits))
        logger.debug(f"Built set hard limits command: {command}")
        return command

    @staticmethod
    def build_set_accelerations_command(accels: Dict[str, int]) -> AxisCommand:
        if not accels:
            raise ValueError("Requires at least one axis to set accelerations.")
        command = AxisCommand(code="M204", axis_values=Dispatcher._normalize_axis_values(accels))
        logger.debug(f"Built set accelerations command: {command}")
        return command

    @staticmethod
    def build_set_homing_speeds_command(speeds: Dict[str, int]) -> AxisCommand:
        if not speeds:
            raise ValueError("Requires at least one axis to set homing speeds.")
        command = AxisCommand(code="M210", axis_values=Dispatcher._normalize_axis_values(speeds))
        logger.debug(f"Built set homing speeds command: {command}")
        return command

    @staticmethod
    def build_set_travel_speeds_command(speeds: Dict[str, int]) -> AxisCommand:
        if not speeds:
            raise ValueError("Requires at least one axis to set travel speeds.")
        command = AxisCommand(code="M220", axis_values=Dispatcher._normalize_axis_values(speeds))
        logger.debug(f"Built set travel speeds command: {command}")
        return command

    @staticmethod
    def build_set_homing_retraction_command(distances: Dict[str, int]) -> AxisCommand:
        if not distances:
            raise ValueError("Requires at least one axis to set homing retraction distance.")
        command = AxisCommand(code="M421", axis_values=Dispatcher._normalize_axis_values(distances))
        logger.debug(f"Built set homing retraction command: {command}")
        return command

    # --- State and Positioning Modes ---

    @staticmethod
    def set_absolute_positioning() -> SimpleCommand:
        logger.debug("Built absolute positioning command: G90")
        return SimpleCommand("G90")

    @staticmethod
    def set_relative_positioning() -> SimpleCommand:
        logger.debug("Built relative positioning command: G91")
        return SimpleCommand("G91")

    # --- Status Commands ---

    @staticmethod
    def build_position_query() -> SimpleCommand:
        return SimpleCommand("M114")

    @staticmethod
    def build_debug_info_command(pin: str) -> DebugInfoCommand:
        command = DebugInfoCommand(pin=pin)
        logger.debug(f"Built debug info command: {command}")
        return command

    # --- Response Validation ---

    @staticmethod
    def validate_response(response: str, command: object = "") -> str:
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
    def validate_home_response(
        response: str, requested_axes: Optional[List[str]] = None
    ) -> List[str]:
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
    def build_quick_stop() -> SimpleCommand:
        logger.debug("Built quick stop command: M410")
        return SimpleCommand("M410")

    @staticmethod
    def build_emergency_stop() -> SimpleCommand:
        logger.warning("Built emergency stop command: M112")
        return SimpleCommand("M112")

    @staticmethod
    def build_reset_controller_command() -> SimpleCommand:
        logger.warning("Built reset controller command: M30")
        return SimpleCommand("M30")

    @staticmethod
    def build_disable_blocking_limits_command() -> SimpleCommand:
        logger.warning("Built disable blocking limits command: M911")
        return SimpleCommand("M911")
