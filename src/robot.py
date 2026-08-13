from __future__ import annotations

import time

from .core import AxisId, MountSide
from .geometry.calibration import DeckCalibration
from .geometry.coordinates import DeckPoint
from .motion.axis import Axis, default_axis_configs
from .motion.mounts import Mount
from .protocol.driver import Controller
from .transport.base import Transport


class Robot:
    """Top-level facade tying transport, controller, calibration, deck, axes,
    mounts and loaded labware together. The object most user code touches.

    All deck-space motion is tip-aware: if the tool on a mount reports a
    ``tip_offset_mm()``, Z targets place the tip end, not the bare nozzle.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        calibration: DeckCalibration | None = None,
        deck=None,
        travel_z_mm: float = 60.0,
        timeout: float = 30.0,
    ):
        self.controller = Controller(transport, timeout=timeout)
        self.calibration = calibration
        self.deck = deck
        self.travel_z_mm = travel_z_mm  # safe clearance height (deck mm)
        self.axes = {a: Axis(cfg) for a, cfg in default_axis_configs().items()}
        self.mounts = {
            MountSide.LEFT: Mount(MountSide.LEFT),
            MountSide.RIGHT: Mount(MountSide.RIGHT),
            MountSide.REAR: Mount(MountSide.REAR),
        }
        self.labware: dict = {}  # name -> Labware, placed on a slot
        self.tips: dict = {}  # name -> TipGeometry (known tip types)

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

    def load_labware(self, labware, slot_name: str, *, key: str | None = None):
        """Place ``labware`` on ``slot_name`` and register it in
        ``self.labware`` under ``key`` (default: the labware's own
        ``.name``). Pass an explicit ``key`` when two placements share one
        reusable labware definition (same ``.name``, different slots) --
        e.g. the same well-plate spec used as both a source and a
        destination -- so the second placement doesn't overwrite the
        first's dict entry; ``.name`` still reflects the shared physical
        identity either way, only the addressing key differs."""
        if self.deck is None:
            raise RuntimeError("no deck configured")
        labware.place(self.deck[slot_name])
        self.labware[key or labware.name] = labware
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
        for a in axes or tuple(AxisId):
            if a in self.axes:
                self.axes[a].homed = True

    def _await_settled(
        self,
        targets: dict,
        *,
        tolerance: int = 5,
        timeout: float = 30.0,
        poll_interval: float = 0.05,
    ) -> None:
        """Polls the controller's OWN reported position (M114) until every
        axis in `targets` is within `tolerance` microsteps of its commanded
        value, or raises TimeoutError. A move's 'ok' means the firmware
        considers it done, but that hasn't reliably meant "physically
        arrived" on every real firmware/hardware combination this has been
        run against (see scripts/calibrate_pipette.py's verify=True,
        added after commands issued back-to-back with no delay were
        observed getting cut short in practice, confirmed by the same
        sequence working correctly when stepped through with a debugger --
        i.e. when real wall-clock time was inadvertently inserted between
        them). This is an independent, position-based confirmation that
        doesn't depend on trusting the handshake alone."""
        deadline = time.monotonic() + timeout
        while True:
            pos = self.controller.report_position()
            if all(
                pos.get(axis) is not None and abs(pos[axis] - target) <= tolerance
                for axis, target in targets.items()
            ):
                return
            if time.monotonic() >= deadline:
                last = {a: pos.get(a) for a in targets}
                raise TimeoutError(
                    f"axes did not settle within {timeout}s: wanted {targets}, last read {last}"
                )
            time.sleep(poll_interval)

    def move_to(
        self,
        point: DeckPoint,
        side: MountSide = MountSide.LEFT,
        feed: int | None = None,
        *,
        verify: bool = False,
    ) -> None:
        """Cross to the target X/Y at the current Z, then move to the target
        Z -- no clearance-height detour (see safe_move_to for that arc).
        X/Y always goes first, as two separate blocking commands rather than
        one bundled multi-axis move: firmware happens to prioritize X/Y
        stepping over Z today, but a mounted tip dragging across labware if
        that ever isn't true (different firmware revision, etc.) is exactly
        the failure this guards against without relying on it.

        verify: also poll-confirm each leg actually reached its target (see
        _await_settled) before moving on -- opt-in, so existing callers
        (interactive jogging, routines) keep today's behavior unchanged."""
        cal = self._require_cal()
        xy = cal.deck_to_motor(point, side, self.tip_offset(side))
        xy_targets = {AxisId.X: xy[AxisId.X], AxisId.Y: xy[AxisId.Y]}
        (self.controller.linear_move if feed else self.controller.rapid_move)(
            xy_targets, **({"feed": feed} if feed else {})
        )
        if verify:
            self._await_settled(xy_targets)
        self.move_vertical_to(point.z, side, feed=feed, verify=verify)

    def move_vertical_to(
        self,
        deck_z_mm: float,
        side: MountSide,
        feed: int | None = None,
        *,
        verify: bool = False,
    ) -> None:
        """Command only the mount's vertical axis to a deck-Z height."""
        cal = self._require_cal()
        axis = cal.vertical_axis(side)
        mz = cal.deck_to_motor(DeckPoint(0, 0, deck_z_mm), side, self.tip_offset(side))[axis]
        (self.controller.linear_move if feed else self.controller.rapid_move)(
            {axis: mz}, **({"feed": feed} if feed else {})
        )
        if verify:
            self._await_settled({axis: mz})

    def raise_z(
        self, side: MountSide, clearance_mm: float | None = None, *, verify: bool = False
    ) -> None:
        self.move_vertical_to(
            clearance_mm if clearance_mm is not None else self.travel_z_mm, side, verify=verify
        )

    def safe_move_to(
        self,
        point: DeckPoint,
        side: MountSide,
        clearance_mm: float | None = None,
        feed: int | None = None,
        *,
        verify: bool = False,
    ) -> None:
        """Move in the order X/Y-safe arc: (1) raise this mount's Z/A to
        clearance height, (2) cross to the target's X/Y, (3) descend Z/A to
        the target -- so a mounted tip never drags across labware.

        verify: see move_to's own docstring -- opt-in, poll-confirms each
        leg before moving on to the next."""
        cal = self._require_cal()
        clr = clearance_mm if clearance_mm is not None else self.travel_z_mm
        self.raise_z(side, clr, verify=verify)  # 1. up
        xy = cal.deck_to_motor(DeckPoint(point.x, point.y, clr), side, self.tip_offset(side))
        xy_targets = {AxisId.X: xy[AxisId.X], AxisId.Y: xy[AxisId.Y]}
        self.controller.rapid_move(xy_targets)  # 2. across
        if verify:
            self._await_settled(xy_targets)
        self.move_vertical_to(point.z, side, feed=feed, verify=verify)  # 3. down

    def emergency_stop(self) -> None:
        self.controller.emergency_stop()
        for ax in self.axes.values():
            ax.homed = False
