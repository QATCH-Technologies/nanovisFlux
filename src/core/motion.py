import re
from typing import Dict, List, Optional

from src.hardware.connection import Connection
from src.hardware.dispatcher import AXES, Dispatcher
from src.utils.logger import logger


class MotionController:
    def __init__(self, connection: Connection):
        self.connection = connection
        self.current_position: Dict[str, Optional[float]] = {axis: None for axis in AXES}
        self._is_absolute_mode = True
        self._set_absolute_mode()

    def _set_absolute_mode(self) -> None:
        self.connection.send_command(Dispatcher.set_absolute_positioning())
        self._is_absolute_mode = True
        logger.debug("Firmware set to ABSOLUTE positioning mode.")

    def _set_relative_mode(self) -> None:
        self.connection.send_command(Dispatcher.set_relative_positioning())
        self._is_absolute_mode = False
        logger.debug("Firmware set to RELATIVE positioning mode.")

    def home(self, axes: Optional[List[str]] = None) -> None:
        command = Dispatcher.build_home_command(axes)
        response = self.connection.send_command(command)

        requested_axes = [axis.upper() for axis in axes] if axes else None
        homed_axes = Dispatcher.validate_home_response(response, requested_axes)

        for axis in homed_axes:
            self.current_position[axis] = 0.0

        logger.info(f"Homed axes: {homed_axes}. Current position reset to 0.")

        # Always revert to absolute mode after a homing cycle
        self._set_absolute_mode()

    def move_absolute(self, positions: Dict[str, float], speed: Optional[float] = None) -> None:
        self._check_homed_state(positions.keys())

        if not self._is_absolute_mode:
            self._set_absolute_mode()

        command = Dispatcher.build_move_command(positions, speed)
        response = self.connection.send_command(command)
        Dispatcher.validate_response(response, command)
        for axis, value in positions.items():
            self.current_position[axis.upper()] = value

        logger.info(f"Absolute move complete. New position: {self.current_position}")

    def rapid_move(self, positions: Dict[str, float]) -> None:
        self._check_homed_state(positions.keys())

        if not self._is_absolute_mode:
            self._set_absolute_mode()

        command = Dispatcher.build_rapid_move_command(positions)
        response = self.connection.send_command(command)
        Dispatcher.validate_response(response, command)
        for axis, value in positions.items():
            self.current_position[axis.upper()] = value

        logger.info(f"Rapid move complete. New position: {self.current_position}")

    def move_relative(self, offsets: Dict[str, int], speed: Optional[float] = None) -> None:
        self._check_homed_state(offsets.keys())

        if self._is_absolute_mode:
            self._set_relative_mode()

        command = Dispatcher.build_move_command(offsets, speed)
        response = self.connection.send_command(command)
        Dispatcher.validate_response(response, command)
        for axis, offset in offsets.items():
            current_val = self.current_position[axis.upper()]
            if current_val is not None:
                self.current_position[axis.upper()] = current_val + offset

        # Snap back to absolute mode after a relative move prevent subsequent
        # absolute commands from being interpreted as relative.
        self._set_absolute_mode()
        logger.info(f"Relative move complete. New position: {self.current_position}")

    def start_continuous_jog(self, axis: str, direction: float, speed: float) -> None:
        self._set_relative_mode()
        target = 100000 * int(direction)
        cmd = Dispatcher.build_move_command({axis: target}, speed)
        self.connection.send_command(cmd, wait_for_ok=False)

    def stop_continuous_jog(self) -> None:
        halt_cmd = Dispatcher.build_quick_stop()
        self.connection.send_command(halt_cmd, wait_for_ok=False)
        self.connection.reset_input_buffer()

        self.sync_position()

    def sync_position(self) -> None:
        self._set_absolute_mode()
        query_cmd = Dispatcher.build_position_query()
        response = self.connection.send_command(query_cmd, wait_for_ok=True)
        matches = re.findall(r"([A-Z]):([-0-9.]+)", response.upper())
        for matched_axis, val_str in matches:
            if matched_axis in AXES:
                self.current_position[matched_axis] = float(val_str)

        logger.debug(f"Position synced after interrupt: {self.current_position}")

    def probe(
        self, axis: str, target: int, speed: float, probe_type: str = "38.2"
    ) -> str:
        self._check_homed_state([axis])

        if not self._is_absolute_mode:
            self._set_absolute_mode()

        command = Dispatcher.build_probe_command(axis, target, speed, probe_type)
        response = self.connection.send_command(command)

        # Firmware only reports X/Y/A in [PRB:...]; re-query to get the
        # authoritative position for every axis instead of parsing it.
        self.sync_position()
        logger.info(f"Probe on axis {axis.upper()} complete: {response}")
        return response

    def emergency_stop(self) -> None:
        command = Dispatcher.build_emergency_stop()
        self.connection.send_command(command, wait_for_ok=False)
        self.connection.reset_input_buffer()
        self.current_position = {axis: None for axis in AXES}
        logger.warning("Emergency stop triggered. Machine must be re-homed before further motion.")

    def reset_controller(self) -> None:
        command = Dispatcher.build_reset_controller_command()
        self.connection.send_command(command)
        self.current_position = {axis: None for axis in AXES}
        self._is_absolute_mode = True
        logger.warning("Controller reset to firmware defaults. Machine must be re-homed.")

    def disable_blocking_limits(self) -> None:
        command = Dispatcher.build_disable_blocking_limits_command()
        self.connection.send_command(command)
        logger.warning("Firmware blocking limits disabled.")

    def set_hard_limits(self, limits: Dict[str, int]) -> None:
        command = Dispatcher.build_set_hard_limits_command(limits)
        self.connection.send_command(command)
        logger.info(f"Hard limits set: {limits}")

    def set_accelerations(self, accels: Dict[str, int]) -> None:
        command = Dispatcher.build_set_accelerations_command(accels)
        self.connection.send_command(command)
        logger.info(f"Accelerations set: {accels}")

    def set_homing_speeds(self, speeds: Dict[str, int]) -> None:
        command = Dispatcher.build_set_homing_speeds_command(speeds)
        self.connection.send_command(command)
        logger.info(f"Homing speeds set: {speeds}")

    def set_travel_speeds(self, speeds: Dict[str, int]) -> None:
        command = Dispatcher.build_set_travel_speeds_command(speeds)
        self.connection.send_command(command)
        logger.info(f"Travel speeds set: {speeds}")

    def set_homing_retraction(self, distances: Dict[str, int]) -> None:
        command = Dispatcher.build_set_homing_retraction_command(distances)
        self.connection.send_command(command)
        logger.info(f"Homing retraction distances set: {distances}")

    def query_debug_info(self, pin: str) -> str:
        command = Dispatcher.build_debug_info_command(pin)
        return self.connection.send_command(command)

    def _check_homed_state(self, requested_axes: iter) -> None:
        unhomed = [axis for axis in requested_axes if self.current_position[axis.upper()] is None]
        if unhomed:
            raise RuntimeError(
                f"Safety Interlock: Axes {unhomed} have not been homed. "
                "Call home() before attempting to move."
            )
