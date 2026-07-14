import time

import pygame

from src.core.robot import Robot
from src.utils.logger import logger


class GamepadTeleop:
    def __init__(self, robot: Robot):
        self.robot = robot
        self.active_mount = "left"  # State: 'left' or 'right'

        # Velocity settings
        self.current_speed = 20_000
        self.max_speed = 100_000
        self.speed_increment = 1_000

        self.is_running = True
        self.deadzone = 0.2  # Ignore slight stick drift
        self.axis_states = {"X": 0, "Y": 0, "Z": 0, "A": 0}  # Tracks active direction
        self._active_pipette_jog = None  # (tool, axis, start_position) while Aspirate/Dispense is held

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
        logger.info(" [X/Y Gantry]    Left Analog Stick")
        logger.info(" [Active Z]      Right Analog Stick (Up/Down)")
        logger.info(" [Mount Switch]  LB / L1 (Left), RB / R1 (Right)")
        logger.info(" [Fluidic]       X / Square (Aspirate, hold), B / Circle (Dispense, hold)")
        logger.info("-" * 60)
        logger.info(" [Speed Control] D-Pad Up (Increase), D-Pad Down (Decrease)")
        logger.info(" [Step Size]     D-Pad Right (Larger), D-Pad Left (Smaller)")
        logger.info(" [Actions]       A / Cross (Log Pos), Y / Triangle (Home)")
        logger.info(" [Stops]         Back / Select (Quick Stop), Start (Emergency)")
        logger.info(
            f" Current Mount: {self.active_mount.upper()} | Speed: {self.current_speed} | Step: {self.speed_increment}"
        )
        logger.info("=" * 60 + "\n")

    def _get_active_mount_axis(self) -> str:
        return self.robot.get_mount_axis(self.active_mount)

    def _handle_axis_motion(
        self, axis: str, value: float, positive_dir: float, negative_dir: float
    ) -> None:
        """Helper to translate analog stick values to continuous jog commands."""
        # Check if the stick is returned to the center (within deadzone)
        if abs(value) < self.deadzone:
            if self.axis_states[axis] != 0:
                self.robot.motion.stop_continuous_jog()
                self.axis_states[axis] = 0
        else:
            # Determine direction based on stick push
            direction = positive_dir if value > 0 else negative_dir
            if self.axis_states[axis] != direction:
                self.robot.motion.start_continuous_jog(axis, direction, self.current_speed)
                self.axis_states[axis] = direction

    def _sync_pipette_jog_volume(self) -> None:
        """Reconciles Pipette.current_volume after a continuous Aspirate/Dispense hold stops."""
        if self._active_pipette_jog is None:
            return

        tool, axis, start_position = self._active_pipette_jog
        self._active_pipette_jog = None

        end_position = self.robot.motion.current_position.get(axis)
        if start_position is None or end_position is None or not tool.steps_per_ul:
            return

        delta_volume = (end_position - start_position) / tool.steps_per_ul
        tool.current_volume = max(0.0, min(tool.max_volume, tool.current_volume + delta_volume))

    def _process_events(self) -> None:
        for event in pygame.event.get():
            try:
                # --- BUTTON PRESSES ---
                if event.type == pygame.JOYBUTTONDOWN:
                    # Emergency Stop (Start Button - usually button 7)
                    if event.button == 7:
                        self.robot.motion.stop_continuous_jog()
                        self._sync_pipette_jog_volume()
                        self.is_running = False
                        logger.info("Emergency Stop Triggered. Exiting...")

                    # Quick Stop (Back/Select Button - usually button 6)
                    elif event.button == 6:
                        self.robot.motion.stop_continuous_jog()
                        self._sync_pipette_jog_volume()
                        self.axis_states = {"X": 0, "Y": 0, "Z": 0, "A": 0}
                        logger.info("Quick Stop Triggered.")

                    # Log Position (A Button - usually button 0)
                    elif event.button == 0:
                        logger.info(f"Current Position: {self.robot.motion.current_position}")

                    # Home (Y Button - usually button 3)
                    elif event.button == 3:
                        self.robot.home()

                    # Mount Switching (LB = 4, RB = 5)
                    elif event.button == 4:
                        self.active_mount = "left"
                        logger.info(f"Switched to {self.active_mount.upper()} mount.")
                    elif event.button == 5:
                        self.active_mount = "right"
                        logger.info(f"Switched to {self.active_mount.upper()} mount.")

                    # Fluidics (X = 2 for Aspirate, B = 1 for Dispense; continuous while held)
                    elif event.button in (1, 2):
                        tool = self.robot.get_tool(self.active_mount)
                        if hasattr(tool, "aspirate"):
                            axis = tool.axis
                            direction = 1.0 if event.button == 2 else -1.0
                            self._active_pipette_jog = (
                                tool,
                                axis,
                                self.robot.motion.current_position[axis],
                            )
                            self.robot.motion.start_continuous_jog(axis, direction, self.current_speed)

                # --- BUTTON RELEASES (Interrupt continuous actions) ---
                elif event.type == pygame.JOYBUTTONUP:
                    # Fluidics release (X = 2 for Aspirate, B = 1 for Dispense)
                    if event.button in (1, 2):
                        self.robot.motion.stop_continuous_jog()
                        self._sync_pipette_jog_volume()

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

                # --- ANALOG STICKS (Continuous Motion) ---
                elif event.type == pygame.JOYAXISMOTION:
                    # Left Stick X-Axis (Usually axis 0)
                    # Note: Original map was A (+1 X, Left) and D (-1 X, Right)
                    if event.axis == 0:
                        self._handle_axis_motion(
                            "X", event.value, positive_dir=-1.0, negative_dir=1.0
                        )

                    # Left Stick Y-Axis (Usually axis 1)
                    # Note: Original map was W (-1 Y, Up) and S (+1 Y, Down)
                    elif event.axis == 1:
                        self._handle_axis_motion(
                            "Y", event.value, positive_dir=1.0, negative_dir=-1.0
                        )

                    # Right Stick Y-Axis (Usually axis 3 or 4 depending on OS/Driver)
                    # Note: Original map was Q (+1 Z, Up) and E (-1 Z, Down)
                    elif event.axis in (3, 4):
                        axis_name = self._get_active_mount_axis()
                        self._handle_axis_motion(
                            axis_name, event.value, positive_dir=-1.0, negative_dir=1.0
                        )

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
            self.robot.motion.stop_continuous_jog()
            self._sync_pipette_jog_volume()
            logger.info("Teleop interrupted by user.")
        finally:
            pygame.quit()
