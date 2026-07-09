from pynput import keyboard

from src.core.robot import Robot
from src.utils.logger import logger


class KeyboardTeleop:
    def __init__(self, robot: Robot):
        self.robot = robot
        self.active_mount = "left"  # State: 'left' or 'right'

        # Velocity settings
        self.current_speed = 20_000
        self.max_speed = 100_000
        self.speed_increment = 1_000
        self.volume_step = 1_000
        self.active_axes = {}
        self.pressed_keys = set()
        self.is_running = True
        self._print_legend()

    def _print_legend(self) -> None:
        logger.info("=" * 50)
        logger.info(" KEYBOARD TELEOP CONTROLS ")
        logger.info(" [X/Y Gantry]    A (+X), D (-X), W (-Y), S (+Y)")
        logger.info(" [Mount Switch]  1 (Left), 2 (Right)")
        logger.info(" [Active Z]      Q (+Z), E (-Z)")
        logger.info(" [Fluidic]       R (Aspirate), F (Dispense)")
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
        if self.active_mount == "left":
            return "Z"
        elif self.active_mount == "right":
            return "Z"
        return "Z"

    def on_press(self, key) -> bool:
        if key in self.pressed_keys:
            return True
        self.pressed_keys.add(key)

        try:
            if key == keyboard.Key.esc:
                self.robot.motion.stop_continuous_jog()
                self.is_running = False
                return False
            if key == keyboard.Key.space:
                self.robot.motion.stop_continuous_jog()
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

                # Fluidics (One-shot actions)
                elif char in ("r", "f"):
                    tool = self.robot.get_tool(self.active_mount)
                    if hasattr(tool, "aspirate"):
                        if char == "r":
                            tool.aspirate(self.volume_step)
                        else:
                            tool.dispense(self.volume_step)

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
            if char in ("a", "d", "w", "s", "q", "e"):
                self.robot.motion.stop_continuous_jog()
        return True

    def start(self) -> None:
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()
