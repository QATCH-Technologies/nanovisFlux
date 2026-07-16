import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

from src.common.calibration import Calibration
from src.common.motion import MotionController
from src.coms.connection import Connection
from src.core.coordinate import VirtualCoordinate
from src.core.coordinate_system import DeckCalibration, MountOffsets, PhysicalEnvelope
from src.core.deck import DEFAULT_DECK_LAYOUT_PATH, Deck, DeckLocation
from src.core.gantry import Gantry
from src.core.mount import MountPosition
from src.tools import Tool, create_tool
from src.utils.logger import logger

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "ot2_config.json"


class Robot:
    # Legacy "left"/"right" mount config keys map onto the primary gantry
    # mount positions -- the only ones current configs populate. A caller can
    # still pass a MountPosition (e.g. MountPosition.LEFT_SECONDARY) directly
    # to reach positions with no legacy alias.
    _MOUNT_ALIASES = {"left": MountPosition.LEFT_PRIMARY, "right": MountPosition.RIGHT_PRIMARY}

    def __init__(
        self,
        port: str | None = None,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        deck_layout_path: str | Path = DEFAULT_DECK_LAYOUT_PATH,
        connection_override=None,
    ):
        self.config = {}
        self._load_config(config_path)
        conn_config = self.config.get("connection", {})
        self.port = port or conn_config.get("default_port")
        baudrate = conn_config.get("baudrate", 115200)
        timeout = conn_config.get("timeout", 1.0)
        protocol = conn_config.get("protocol", "auto")

        if connection_override is not None:
            self._connection = connection_override
        else:
            self._connection = Connection(
                target=self.port, port_or_baud=baudrate, timeout=timeout, protocol=protocol
            )

        self.motion = MotionController(self._connection)

        self.gantry = Gantry()
        for side, position in self._MOUNT_ALIASES.items():
            tool = self._init_tool(side)
            if tool is not None:
                self.gantry.mount(position, tool)

        self.left_tool = self.gantry.get(MountPosition.LEFT_PRIMARY)
        self.right_tool = self.gantry.get(MountPosition.RIGHT_PRIMARY)

        self.calibration = self._load_calibration()
        self.deck = self._load_deck(deck_layout_path)
        self.physical_envelope = self._load_physical_envelope()
        self.mount_offsets = self._load_mount_offsets()
        self.deck_calibration = self._load_deck_calibration()

        self.safe_z = self.config.get("gantry", {}).get("safe_z_height", 100)
        self.home()

    def _init_tool(self, side: str) -> Optional[Tool]:
        tool_data: dict = self.config.get("mounts", {}).get(side)

        if not tool_data:
            logger.info(f"No configuration found for {side} mount. Leaving empty.")
            return None

        tool_type = tool_data.get("type", "")

        try:
            return create_tool(tool_type, tool_data, self.motion)
        except ValueError:
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

    def _load_calibration(self) -> Optional[Calibration]:
        calibration_data = self.config.get("calibration")
        if not calibration_data:
            logger.info("No calibration configuration found. mm-based motion is unavailable.")
            return None
        return Calibration.from_config(calibration_data)

    def _load_deck(self, deck_layout_path: Union[str, Path]) -> Optional[Deck]:
        try:
            return Deck.load(deck_layout_path)
        except FileNotFoundError:
            logger.info(f"No deck layout found at {deck_layout_path}. Deck moves are unavailable.")
            return None

    def _load_physical_envelope(self) -> Optional[PhysicalEnvelope]:
        corners = self.config.get("physical_envelope")
        if not corners:
            logger.info("No physical envelope configured. Travel-limit checking is unavailable.")
            return None
        return PhysicalEnvelope.from_corners(corners)

    def _load_mount_offsets(self) -> Optional[MountOffsets]:
        offsets = self.config.get("mount_offsets")
        if not offsets:
            logger.info(
                "No mount offsets configured. Deck moves will target the gantry frame directly."
            )
            return None
        return MountOffsets.from_config(offsets)

    def _load_deck_calibration(self) -> Optional[DeckCalibration]:
        data = self.config.get("deck_calibration")
        if not data:
            logger.info("No deck calibration configured. Deck X/Y moves are unavailable.")
            return None
        return DeckCalibration.from_config(data)

    def connect(self) -> None:
        logger.info(f"Initializing Robot on {self.port}...")
        self._connection.connect()
        logger.info("Robot connected successfully!")

    def disconnect(self) -> None:
        logger.info("Shutting down...")
        self._connection.disconnect()

    def home(self, axes: Optional[List[str]] = None) -> None:
        self.motion.home(axes)

    def emergency_stop(self) -> None:
        self.motion.emergency_stop()

    def reset(self) -> None:
        self.motion.reset_controller()

    def get_tool(self, side: Union[Literal["left", "right"], MountPosition]) -> Tool:
        tool = self.gantry.get(self._resolve_mount_position(side))

        if tool is None:
            raise RuntimeError(f"The {side} tool is not configured or initialized.")

        return tool

    def _resolve_mount_position(self, side: Union[str, MountPosition]) -> MountPosition:
        if isinstance(side, MountPosition):
            return side
        if side in self._MOUNT_ALIASES:
            return self._MOUNT_ALIASES[side]
        return MountPosition(side)

    def get_mount_axis(self, side: Literal["left", "right"]) -> str:
        mount_axis = self.config.get("mounts", {}).get(side, {}).get("mount_axis")

        if not mount_axis:
            raise RuntimeError(f"No mount_axis configured for the {side} mount.")

        return mount_axis.upper()

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

    def move_to_location(
        self,
        location: DeckLocation,
        mount: Optional[Literal["left", "right"]] = None,
        speed: Optional[float] = None,
    ) -> None:
        if self.deck is None:
            raise RuntimeError("No deck layout loaded. Cannot move to a deck location.")
        if self.deck_calibration is None:
            raise RuntimeError("No deck calibration loaded. Cannot convert deck X/Y to steps.")
        if self.calibration is None:
            raise RuntimeError("No calibration loaded. Cannot convert Z mm to steps.")

        positions_mm = self.deck.resolve_mm(location)
        virtual = VirtualCoordinate(x=positions_mm["X"], y=positions_mm["Y"], z=positions_mm["Z"])
        physical = virtual.to_steps(self.deck_calibration, self.calibration)
        positions_steps = physical.as_steps()

        if mount is not None:
            positions_steps = self._to_mount_frame(mount, positions_steps)

        if self.physical_envelope is not None:
            violations = self.physical_envelope.violations(positions_steps)
            if violations:
                raise RuntimeError(
                    f"Target {positions_steps} for slot '{location.slot_id}' exceeds the "
                    f"calibrated physical envelope: {violations}"
                )

        travel_speed = speed or self.config.get("gantry", {}).get("default_travel_speed")
        self.motion.move_absolute(positions_steps, speed=travel_speed)

    def _to_mount_frame(
        self, mount: Literal["left", "right"], gantry_steps: Dict[str, float]
    ) -> Dict[str, float]:
        """Reframes a nominal gantry-space step target for a specific mount:
        swaps the generic 'Z' key for that mount's own vertical axis (Z or A)
        and applies its fixed mounting offset."""
        steps = dict(gantry_steps)
        if "Z" in steps:
            steps[self.get_mount_axis(mount)] = steps.pop("Z")
        if self.mount_offsets is not None:
            steps = self.mount_offsets.apply(mount, steps)
        return steps
