import time
from typing import Dict, Tuple

import pygame

from src.common.robot import Robot
from src.utils.logger import logger

# Axis indices for this controller/driver, as observed on real hardware: this
# driver enumerates both sticks fully in X-then-Y order (LX, LY, RX, RY)
# before the two triggers (LT, RT), unlike the SDL_GameController convention
# (LX, LY, LT, RX, RY, RT). Confirmed via live testing: axis 2 drives motion
# when the right stick is pushed left/right, so it's RX (ignored); axis 3
# fires on up/down, so it's RY (drives the active mount's Z/A axis). If
# fluidics/axes still misfire, check the DEBUG-level "Axis <n> = <value>"
# log line this file emits to find the real index instead of guessing again.
AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
AXIS_RIGHT_STICK_X = 2  # intentionally unhandled -- left/right on the right stick does nothing
AXIS_RIGHT_STICK_Y = 3  # confirmed via live hardware testing
AXIS_LEFT_TRIGGER = 4
AXIS_RIGHT_TRIGGER = 5


def normalized_magnitude(raw_value: float, deadzone: float) -> float:
    """Maps a raw stick axis value to [0, 1], zero inside the deadzone."""
    if abs(raw_value) < deadzone:
        return 0.0
    return max(0.0, min(1.0, (abs(raw_value) - deadzone) / (1.0 - deadzone)))


def magnitude_to_speed(normalized: float, min_speed: float, max_speed: float) -> float:
    """Maps a normalized [0, 1] magnitude to a jog speed between a floor and a ceiling."""
    return min_speed + normalized * (max_speed - min_speed)


def trigger_pressed_fraction(raw_value: float) -> float:
    """SDL2 reports triggers as -1.0 (released) .. 1.0 (fully pressed)."""
    return max(0.0, min(1.0, (raw_value + 1.0) / 2.0))


def should_reissue(
    prev_direction: float,
    prev_speed: float,
    new_direction: float,
    new_speed: float,
    threshold_speed: float,
) -> bool:
    """Whether a continuous jog command should be re-sent: direction changed, or
    speed changed by at least threshold_speed (avoids flooding on stick jitter)."""
    return prev_direction != new_direction or abs(new_speed - prev_speed) >= threshold_speed


class GamepadTeleop:
    def __init__(self, robot: Robot):
        self.robot = robot
        self.active_mount = "left"  # State: 'left' or 'right'

        # Velocity settings
        self.current_speed = 20_000
        self.max_speed = 100_000
        self.speed_increment = 1_000
        self.min_jog_speed = 500.0
        self.speed_reissue_threshold_fraction = 0.05

        self.is_running = True
        self.deadzone = 0.2  # Ignore slight stick drift
        self.trigger_deadzone = 0.12  # Triggers commonly report a nonzero resting baseline
        self.axis_states: Dict[str, Tuple[float, float]] = {
            "X": (0, 0.0),
            "Y": (0, 0.0),
            "Z": (0, 0.0),
            "A": (0, 0.0),
        }
        self._fluidics_state: Tuple[float, float] = (0, 0.0)
        self._left_trigger_speed = 0.0
        self._right_trigger_speed = 0.0
        self._active_pipette_jog = None  # (tool, axis, start_position) while a trigger is held

        # Initialize Pygame and Joystick
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            logger.error("No gamepad detected! Please connect a controller and try again.")
            self.is_running = False
            return

        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()

        self._print_legend()

    def _print_legend(self) -> None:
        logger.info("=" * 60)
        logger.info(f" GAMEPAD TELEOP CONTROLS - {self.controller.get_name().upper()} ")
        logger.info(" [X/Y Gantry]    Left Analog Stick (proportional speed)")
        logger.info(" [Active Z]      Right Analog Stick, Up/Down (proportional speed)")
        logger.info(
            " [Fluidic]       Left Trigger (Aspirate), Right Trigger (Dispense) - proportional"
        )
        logger.info(" [Mount Switch]  Y")
        logger.info(" [Tip]           LB (Pickup), RB (Drop)")
        logger.info("-" * 60)
        logger.info(" [Speed Control] D-Pad Up (Increase), D-Pad Down (Decrease)")
        logger.info(" [Step Size]     D-Pad Right (Larger), D-Pad Left (Smaller)")
        logger.info(" [Actions]       X (Log Pos), Back/Select (Home)")
        logger.info(" [Stops]         A (Quick Stop), Start (Emergency)")
        logger.info(" [Unused]        B")
        logger.info(
            f" Current Mount: {self.active_mount.upper()} | Speed: {self.current_speed} | Step: {self.speed_increment}"
        )
        logger.info("=" * 60 + "\n")

    def _get_active_mount_axis(self) -> str:
        return self.robot.get_mount_axis(self.active_mount)

    def _stop_all_motion(self) -> None:
        self.robot.motion.stop_continuous_jog()
        self._sync_pipette_jog_volume()
        self.axis_states = {axis: (0, 0.0) for axis in self.axis_states}
        self._fluidics_state = (0, 0.0)
        self._left_trigger_speed = 0.0
        self._right_trigger_speed = 0.0

    def _handle_axis_motion(
        self, axis: str, raw_value: float, positive_dir: float, negative_dir: float
    ) -> None:
        """Translates an analog stick value into a proportional continuous jog."""
        normalized = normalized_magnitude(raw_value, self.deadzone)
        if normalized == 0.0:
            prev_direction, _ = self.axis_states[axis]
            if prev_direction != 0:
                self.robot.motion.stop_continuous_jog()
            self.axis_states[axis] = (0, 0.0)
            return

        speed = magnitude_to_speed(normalized, self.min_jog_speed, self.current_speed)
        direction = positive_dir if raw_value > 0 else negative_dir
        prev_direction, prev_speed = self.axis_states[axis]
        threshold = self.speed_reissue_threshold_fraction * self.current_speed
        if should_reissue(prev_direction, prev_speed, direction, speed, threshold):
            self.robot.motion.start_continuous_jog(axis, direction, speed)
            self.axis_states[axis] = (direction, speed)

    def _handle_trigger_motion(self, is_left: bool, raw_value: float) -> None:
        fraction = trigger_pressed_fraction(raw_value)
        if fraction < self.trigger_deadzone:
            speed = 0.0
        else:
            normalized = (fraction - self.trigger_deadzone) / (1.0 - self.trigger_deadzone)
            speed = magnitude_to_speed(normalized, self.min_jog_speed, self.current_speed)

        if is_left:
            self._left_trigger_speed = speed
        else:
            self._right_trigger_speed = speed
        self._update_fluidics_jog()

    def _update_fluidics_jog(self) -> None:
        lt, rt = self._left_trigger_speed, self._right_trigger_speed
        if (lt > 0) == (rt > 0):
            # Both pressed (ambiguous) or neither -- refuse to act rather than guess.
            self._stop_fluidics_jog()
            return

        direction, speed = (1.0, lt) if lt > 0 else (-1.0, rt)
        tool = self.robot.get_tool(self.active_mount)
        if not hasattr(tool, "aspirate"):
            return
        axis = tool.axis

        prev_direction, prev_speed = self._fluidics_state
        threshold = self.speed_reissue_threshold_fraction * self.current_speed
        if should_reissue(prev_direction, prev_speed, direction, speed, threshold):
            if prev_direction == 0:
                self._active_pipette_jog = (
                    tool,
                    axis,
                    self.robot.motion.current_position.get(axis),
                )
            self.robot.motion.start_continuous_jog(axis, direction, speed)
            self._fluidics_state = (direction, speed)

    def _stop_fluidics_jog(self) -> None:
        if self._fluidics_state[0] != 0:
            self.robot.motion.stop_continuous_jog()
            self._sync_pipette_jog_volume()
        self._fluidics_state = (0, 0.0)

    def _sync_pipette_jog_volume(self) -> None:
        """Reconciles Pipette.current_volume after a continuous trigger hold stops."""
        if self._active_pipette_jog is None:
            return

        tool, axis, start_position = self._active_pipette_jog
        self._active_pipette_jog = None

        end_position = self.robot.motion.current_position.get(axis)
        if start_position is None or end_position is None or not tool.steps_per_ul:
            return

        delta_volume = (end_position - start_position) / tool.steps_per_ul
        tool.current_volume = max(0.0, min(tool.max_volume, tool.current_volume + delta_volume))

    def _pick_up_tip(self) -> None:
        self._stop_all_motion()
        tool = self.robot.get_tool(self.active_mount)
        if hasattr(tool, "pick_up_tip"):
            tool.pick_up_tip()
        else:
            logger.warning(f"{self.active_mount.upper()} tool has no pick_up_tip().")

    def _drop_tip(self) -> None:
        self._stop_all_motion()
        tool = self.robot.get_tool(self.active_mount)
        if hasattr(tool, "drop_tip"):
            tool.drop_tip()
        else:
            logger.warning(f"{self.active_mount.upper()} tool has no drop_tip().")

    def _process_events(self) -> None:
        for event in pygame.event.get():
            try:
                # --- BUTTON PRESSES ---
                if event.type == pygame.JOYBUTTONDOWN:
                    # Emergency Stop (Start Button - usually button 7)
                    if event.button == 7:
                        self._stop_all_motion()
                        self.is_running = False
                        logger.info("Emergency Stop Triggered. Exiting...")

                    # Quick Stop (A Button - usually button 0)
                    elif event.button == 0:
                        self._stop_all_motion()
                        logger.info("Quick Stop Triggered.")

                    # Log Position (X Button - usually button 2)
                    elif event.button == 2:
                        logger.info(f"Current Position: {self.robot.motion.current_position}")

                    # Mount Switching (Y Button - usually button 3)
                    elif event.button == 3:
                        self._stop_all_motion()
                        self.active_mount = "right" if self.active_mount == "left" else "left"
                        logger.info(f"Switched to {self.active_mount.upper()} mount.")

                    # Pickup Tip (LB - usually button 4)
                    elif event.button == 4:
                        self._pick_up_tip()

                    # Drop Tip (RB - usually button 5)
                    elif event.button == 5:
                        self._drop_tip()

                    # Home (Back/Select Button - usually button 6)
                    elif event.button == 6:
                        self.robot.home()

                    # Button 1 (B) intentionally unbound.

                # --- D-PAD / HATS (Settings Configuration) ---
                elif event.type == pygame.JOYHATMOTION:
                    x, y = event.value

                    # Speed Control (Up/Down)
                    if y == 1:
                        self.current_speed = min(
                            self.max_speed, self.current_speed + self.speed_increment
                        )
                        logger.info(f"Speed adjusted to {self.current_speed} steps/s")
                    elif y == -1:
                        self.current_speed = max(1, self.current_speed - self.speed_increment)
                        logger.info(f"Speed adjusted to {self.current_speed} steps/s")

                    # Step Size Control (Right/Left)
                    if x == 1:
                        self.speed_increment += 1_000
                        logger.info(f"Step size increased to {self.speed_increment}")
                    elif x == -1:
                        self.speed_increment = max(1_000, self.speed_increment - 1_000)
                        logger.info(f"Step size decreased to {self.speed_increment}")

                # --- ANALOG STICKS AND TRIGGERS (Continuous Motion) ---
                elif event.type == pygame.JOYAXISMOTION:
                    logger.debug(f"Axis {event.axis} = {event.value:.3f}")

                    if event.axis == AXIS_LEFT_STICK_X:
                        self._handle_axis_motion(
                            "X", event.value, positive_dir=-1.0, negative_dir=1.0
                        )
                    elif event.axis == AXIS_LEFT_STICK_Y:
                        self._handle_axis_motion(
                            "Y", event.value, positive_dir=1.0, negative_dir=-1.0
                        )
                    elif event.axis == AXIS_RIGHT_STICK_Y:
                        axis_name = self._get_active_mount_axis()
                        self._handle_axis_motion(
                            axis_name, event.value, positive_dir=1.0, negative_dir=-1.0
                        )
                    elif event.axis == AXIS_LEFT_TRIGGER:
                        self._handle_trigger_motion(is_left=True, raw_value=event.value)
                    elif event.axis == AXIS_RIGHT_TRIGGER:
                        self._handle_trigger_motion(is_left=False, raw_value=event.value)

            except Exception as e:
                logger.error(f"Teleop error: {e}")

    def start(self) -> None:
        if not self.is_running:
            return

        logger.info("Gamepad Teleop Started. Press 'Start' button to exit.")

        # Pygame requires an event loop to continuously poll hardware
        try:
            while self.is_running:
                self._process_events()
                time.sleep(0.02)  # 50Hz polling rate to prevent CPU maxing
        except KeyboardInterrupt:
            self._stop_all_motion()
            logger.info("Teleop interrupted by user.")
        finally:
            pygame.quit()
