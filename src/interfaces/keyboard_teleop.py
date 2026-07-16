from pynput import keyboard

from src.common.robot import Robot
from src.utils.logger import logger


class KeyboardTeleop:
    def __init__(self, robot: Robot):
        self.robot = robot
        self.active_mount = "left"  # State: 'left' or 'right'

        # Velocity settings
        self.current_speed = 20_000
        self.max_speed = 100_000
        self.speed_increment = 1_000
        self.active_axes = {}
        self.pressed_keys = set()
        self.is_running = True
        self._active_pipette_jog = None  # (tool, axis, start_position) while R/F is held
        self._print_legend()

    def _print_legend(self) -> None:
        logger.info("=" * 50)
        logger.info(" KEYBOARD TELEOP CONTROLS ")
        logger.info(" [X/Y Gantry]    A (+X), D (-X), W (-Y), S (+Y)")
        logger.info(" [Mount Switch]  1 (Left), 2 (Right)")
        logger.info(" [Active Z]      Q (+Z), E (-Z)")
        logger.info(" [Fluidic]       R (Aspirate, hold), F (Dispense, hold)")
        logger.info(" [Tip]           T (Pickup), G (Drop)")
        logger.info("-" * 50)
        logger.info(" [Speed Control] Left (Decrease Speed), Right (Increase Speed)")
        logger.info(" [Step Size]     [ (Smaller Step), ] (Larger Step)")
        logger.info(" [Actions]       Enter (Log Pos), H (Home)")
        logger.info(" [Stops]         Space (Quick), ESC (Emergency)")
        logger.info(
            f" Current Mount: {self.active_mount.upper()} | Speed: {self.current_speed} | Step: {self.speed_increment}"
        )
        logger.info("=" * 50 + "\n")

    def _get_active_mount_axis(self) -> str:
        return self.robot.get_mount_axis(self.active_mount)

    def on_press(self, key) -> bool:
        if key in self.pressed_keys:
            return True
        self.pressed_keys.add(key)

        try:
            if key == keyboard.Key.esc:
                self.robot.motion.stop_continuous_jog()
                self._sync_pipette_jog_volume()
                self.is_running = False
                return False
            if key == keyboard.Key.space:
                self.robot.motion.stop_continuous_jog()
                self._sync_pipette_jog_volume()
                self.active_axes.clear()
                return True
            if key == keyboard.Key.enter:
                logger.info(f"Current Position: {self.robot.motion.current_position}")
                return True

            # --- Speed ---
            if key == keyboard.Key.up:
                self.current_speed = min(self.max_speed, self.current_speed + self.speed_increment)
                logger.info(f"Speed adjusted to {self.current_speed} steps/s")

            elif key == keyboard.Key.down:
                self.current_speed = max(1, self.current_speed - self.speed_increment)
                logger.info(f"Speed adjusted to {self.current_speed} steps/s")

            # --- Speed and Increment Control ---
            if key == keyboard.Key.right:
                self.speed_increment += 1_000
                logger.info(f"Step size increased to {self.speed_increment}")

            elif key == keyboard.Key.left:
                self.speed_increment = max(1_000, self.speed_increment - 1_000)
                logger.info(f"Step size decreased to {self.speed_increment}")

            # --- Axis Mapping ---
            elif hasattr(key, "char"):
                char = key.char.lower()

                # Mount Switching
                if char == "1":
                    self.active_mount = "left"
                    logger.info(f"Switched to {self.active_mount.upper()} mount.")
                elif char == "2":
                    self.active_mount = "right"
                    logger.info(f"Switched to {self.active_mount.upper()} mount.")
                elif char == "h":
                    self.robot.home()

                # Fluidics (Continuous, interrupted on key release)
                elif char in ("r", "f"):
                    tool = self.robot.get_tool(self.active_mount)
                    if hasattr(tool, "aspirate"):
                        axis = tool.axis
                        direction = 1.0 if char == "r" else -1.0
                        self._active_pipette_jog = (
                            tool,
                            axis,
                            self.robot.motion.current_position[axis],
                        )
                        self.robot.motion.start_continuous_jog(axis, direction, self.current_speed)

                # Tip handling (single press, not held)
                elif char in ("t", "g"):
                    self.robot.motion.stop_continuous_jog()
                    self._sync_pipette_jog_volume()
                    tool = self.robot.get_tool(self.active_mount)
                    if char == "t":
                        if hasattr(tool, "pick_up_tip"):
                            tool.pick_up_tip()
                        else:
                            logger.warning(
                                f"{self.active_mount.upper()} tool has no pick_up_tip()."
                            )
                    else:
                        if hasattr(tool, "drop_tip"):
                            tool.drop_tip()
                        else:
                            logger.warning(f"{self.active_mount.upper()} tool has no drop_tip().")

                elif hasattr(key, "char"):
                    char = key.char.lower()

                    # Gantry/Mount Mapping
                    axis_map = {
                        "a": ("X", 1.0),
                        "d": ("X", -1.0),
                        "w": ("Y", -1.0),
                        "s": ("Y", 1.0),
                    }

                    # Handle Z/A axis
                    if char in ("q", "e"):
                        axis = self._get_active_mount_axis()
                        direction = 1.0 if char == "q" else -1.0
                        self.robot.motion.start_continuous_jog(axis, direction, self.current_speed)

                    # Handle X/Y axis
                    elif char in axis_map:
                        axis, direction = axis_map[char]
                        self.robot.motion.start_continuous_jog(axis, direction, self.current_speed)

        except Exception as e:
            logger.error(f"Teleop error: {e}")
        return True

    def on_release(self, key) -> bool:
        if key in self.pressed_keys:
            self.pressed_keys.remove(key)

        if hasattr(key, "char"):
            char = key.char.lower()
            if char in ("a", "d", "w", "s", "q", "e", "r", "f"):
                self.robot.motion.stop_continuous_jog()
                self._sync_pipette_jog_volume()
        return True

    def _sync_pipette_jog_volume(self) -> None:
        """Reconciles Pipette.current_volume after a continuous R/F jog stops."""
        if self._active_pipette_jog is None:
            return

        tool, axis, start_position = self._active_pipette_jog
        self._active_pipette_jog = None

        end_position = self.robot.motion.current_position.get(axis)
        if start_position is None or end_position is None or not tool.steps_per_ul:
            return

        delta_volume = (end_position - start_position) / tool.steps_per_ul
        tool.current_volume = max(0.0, min(tool.max_volume, tool.current_volume + delta_volume))

    def start(self) -> None:
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()
