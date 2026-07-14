import json
from pathlib import Path
from typing import List, Literal, Optional, Union

from src.core.motion import MotionController
from src.core.pipette import Pipette
from src.core.touch_sensor import TouchSensor
from src.hardware.connection import Connection
from src.utils.logger import logger

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "ot2_config.json"
)


class Robot:

    def __init__(
        self,
        port: str | None = None,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        connection_override=None,
    ):
        self.config = {}
        self._load_config(config_path)
        self.port = port or self.config.get("connection", {}).get("default_port")
        baudrate = self.config.get("connection", {}).get("baudrate", 115200)

        if connection_override is not None:
            self._connection = connection_override
        else:
            self._connection = Connection(port=self.port, baudrate=baudrate)

        self.motion = MotionController(self._connection)

        self.left_tool = self._init_tool("left")
        self.right_tool = self._init_tool("right")

        self.safe_z = self.config.get("gantry", {}).get("safe_z_height", 100)
        self.home()

    def _init_tool(self, side: str) -> Union[Pipette, TouchSensor, None]:
        tool_data: dict = self.config.get("mounts", {}).get(side)

        if not tool_data:
            logger.info(f"No configuration found for {side} mount. Leaving empty.")
            return None

        tool_type = tool_data.get("type", "")
        mount_axis = tool_data.get("mount_axis", "")

        if tool_type == "pipette":
            return Pipette(
                axis=tool_data.get("plunger_axis", ""),
                max_volume=tool_data.get("max_volume", 0.0),
                steps_per_ul=tool_data.get("steps_per_ul", 0),
                blowout_distance=tool_data.get("blowout_distance", 0),
                motion=self.motion,
            )

        elif tool_type == "touch_sensor":
            return TouchSensor(mount_axis=mount_axis, motion=self.motion)

        else:
            logger.warning(f"Unknown tool type '{tool_type}' on {side} mount.")
            return None

    def _load_config(self, config_path: Union[str, Path]) -> None:
        try:
            with open(config_path, "r") as file:
                self.config = json.load(file)
            logger.debug(f"Loaded configuration from {config_path}")
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Configuration file missing at {config_path}. Cannot initialize robot."
            )
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON formatting in {config_path}: {e}")

    def connect(self) -> None:
        logger.info(f"Initializing Robot on {self.port}...")
        self._connection.connect()
        logger.info("Robot connected successfully!")

    def disconnect(self) -> None:
        logger.info("Shutting down...")
        self._connection.disconnect()

    def home(self, axes: Optional[List[str]] = None) -> None:
        self.motion.home(axes)

    def get_tool(self, side: Literal["left", "right"]) -> Pipette | TouchSensor:
        tool = self.left_tool if side == "left" else self.right_tool

        if tool is None:
            raise RuntimeError(f"The {side} tool is not configured or initialized.")

        return tool

    def move_to(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        speed: float = 3000.0,
    ) -> None:
        targets = {}
        if x is not None:
            targets["X"] = x
        if y is not None:
            targets["Y"] = y
        if z is not None:
            targets["Z"] = z

        if targets:
            self.motion.move_absolute(targets, speed=speed)

    def jog(self, x: int = 0, y: int = 0, z: int = 0, speed: float = 3000.0) -> None:
        offsets = {}
        if x != 0:
            offsets["X"] = x
        if y != 0:
            offsets["Y"] = y
        if z != 0:
            offsets["Z"] = z

        if offsets:
            self.motion.move_relative(offsets, speed=speed)
