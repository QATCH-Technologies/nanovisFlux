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
        self.connection.send_command(command)
        axes_to_update = axes if axes else AXES
        for axis in axes_to_update:
            self.current_position[axis.upper()] = 0.0

        logger.info(f"Homed axes: {axes_to_update}. Current position reset to 0.")

        # Always revert to absolute mode after a homing cycle
        self._set_absolute_mode()

    def move_absolute(self, positions: Dict[str, float], speed: Optional[float] = None) -> None:
        self._check_homed_state(positions.keys())

        if not self._is_absolute_mode:
            self._set_absolute_mode()

        command = Dispatcher.build_move_command(positions, speed)
        self.connection.send_command(command)
        for axis, value in positions.items():
            self.current_position[axis.upper()] = value

        logger.info(f"Absolute move complete. New position: {self.current_position}")

    def move_relative(self, offsets: Dict[str, int], speed: Optional[float] = None) -> None:
        self._check_homed_state(offsets.keys())

        if self._is_absolute_mode:
            self._set_relative_mode()

        command = Dispatcher.build_move_command(offsets, speed)
        self.connection.send_command(command)
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
        if self.connection.serial:
            self.connection.serial.reset_input_buffer()

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

    def _check_homed_state(self, requested_axes: iter) -> None:
        unhomed = [axis for axis in requested_axes if self.current_position[axis.upper()] is None]
        if unhomed:
            raise RuntimeError(
                f"Safety Interlock: Axes {unhomed} have not been homed. "
                "Call home() before attempting to move."
            )
