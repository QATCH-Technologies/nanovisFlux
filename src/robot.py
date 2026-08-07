from __future__ import annotations
from .core import AxisId, MountSide
from .transport.base import Transport
from .protocol.driver import Controller
from .geometry.coordinates import DeckPoint
from .geometry.calibration import DeckCalibration
from .motion.axis import Axis, default_axis_configs
from .motion.mounts import Mount


class Robot:
    """Top-level facade tying transport, controller, calibration, deck, axes,
    mounts and loaded labware together. The object most user code touches.

    All deck-space motion is tip-aware: if the tool on a mount reports a
    ``tip_offset_mm()``, Z targets place the tip end, not the bare nozzle.
    """

    def __init__(self, transport: Transport, *, calibration: DeckCalibration | None = None,
                 deck=None, travel_z_mm: float = 60.0, timeout: float = 30.0):
        self.controller = Controller(transport, timeout=timeout)
        self.calibration = calibration
        self.deck = deck
        self.travel_z_mm = travel_z_mm          # safe clearance height (deck mm)
        self.axes = {a: Axis(cfg) for a, cfg in default_axis_configs().items()}
        self.mounts = {
            MountSide.LEFT: Mount(MountSide.LEFT),
            MountSide.RIGHT: Mount(MountSide.RIGHT),
            MountSide.REAR: Mount(MountSide.REAR),
        }
        self.labware: dict = {}                  # name -> Labware, placed on a slot
        self.tips: dict = {}                     # name -> TipGeometry (known tip types)

    # -- lifecycle ----------------------------------------------------
    def connect(self) -> "Robot":
        self.controller.open()
        return self

    def disconnect(self) -> None:
        self.controller.close()

    def __enter__(self) -> "Robot":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.disconnect()

    # -- tools & labware ---------------------------------------------
    def attach(self, side: MountSide, tool) -> None:
        mount = self.mounts[side]
        mount.attach(tool)
        tool.on_attach(mount, self)

    def left(self):
        return self.mounts[MountSide.LEFT].tool

    def right(self):
        return self.mounts[MountSide.RIGHT].tool

    def rear(self):
        return self.mounts[MountSide.REAR].tool

    def load_labware(self, labware, slot_name: str):
        if self.deck is None:
            raise RuntimeError("no deck configured")
        labware.place(self.deck[slot_name])
        self.labware[labware.name] = labware
        return labware

    def load(self, definition, slot_name: str, *, stacked: bool = False):
        """Place a labware *definition* (WellPlateDefinition,
        ReservoirDefinition, TipRackDefinition, ...) on a named slot -- the
        well/tip offsets are computed from the definition, never hand-picked.
        Tip rack definitions also register their TipGeometry in ``self.tips``.
        """
        if self.deck is None:
            raise RuntimeError("no deck configured")
        labware = definition.place(self.deck[slot_name], stacked=stacked)
        self.labware[labware.name] = labware
        tip_geometry = getattr(definition, "tip_geometry", None)
        if callable(tip_geometry):
            self.tips[labware.name] = tip_geometry()
        return labware

    def tip_offset(self, side: MountSide) -> float:
        tool = self.mounts[side].tool
        getter = getattr(tool, "tip_offset_mm", None)
        return getter() if callable(getter) else 0.0

    # -- motion (deck-space, tip-aware) ------------------------------
    def _require_cal(self) -> DeckCalibration:
        if self.calibration is None:
            raise RuntimeError("deck is not calibrated; set robot.calibration first")
        return self.calibration

    def home(self, *axes: AxisId) -> None:
        self.controller.set_absolute()
        self.controller.home(*axes)
        for a in (axes or tuple(AxisId)):
            if a in self.axes:
                self.axes[a].homed = True

    def move_to(self, point: DeckPoint, side: MountSide = MountSide.LEFT,
                feed: int | None = None) -> None:
        """Single coordinated move (no clearance logic). Prefer safe_move_to
        when crossing the deck with a tip on."""
        targets = self._require_cal().deck_to_motor(point, side, self.tip_offset(side))
        (self.controller.linear_move if feed else self.controller.rapid_move)(
            targets, **({"feed": feed} if feed else {}))

    def move_vertical_to(self, deck_z_mm: float, side: MountSide,
                         feed: int | None = None) -> None:
        """Command only the mount's vertical axis to a deck-Z height."""
        cal = self._require_cal()
        axis = cal.vertical_axis(side)
        mz = cal.deck_to_motor(DeckPoint(0, 0, deck_z_mm), side, self.tip_offset(side))[axis]
        (self.controller.linear_move if feed else self.controller.rapid_move)(
            {axis: mz}, **({"feed": feed} if feed else {}))

    def raise_z(self, side: MountSide, clearance_mm: float | None = None) -> None:
        self.move_vertical_to(clearance_mm if clearance_mm is not None else self.travel_z_mm, side)

    def safe_move_to(self, point: DeckPoint, side: MountSide,
                     clearance_mm: float | None = None, feed: int | None = None) -> None:
        """Move in the order X/Y-safe arc: (1) raise this mount's Z/A to
        clearance height, (2) cross to the target's X/Y, (3) descend Z/A to
        the target -- so a mounted tip never drags across labware."""
        cal = self._require_cal()
        clr = clearance_mm if clearance_mm is not None else self.travel_z_mm
        self.raise_z(side, clr)                                 # 1. up
        xy = cal.deck_to_motor(DeckPoint(point.x, point.y, clr), side, self.tip_offset(side))
        self.controller.rapid_move({AxisId.X: xy[AxisId.X], AxisId.Y: xy[AxisId.Y]})  # 2. across
        self.move_vertical_to(point.z, side, feed=feed)          # 3. down

    def emergency_stop(self) -> None:
        self.controller.emergency_stop()
        for ax in self.axes.values():
            ax.homed = False
