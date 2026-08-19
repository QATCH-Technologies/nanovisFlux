from __future__ import annotations

import time

from .core import AxisId, MountSide
from .geometry.calibration import DeckCalibration
from .geometry.coordinates import DeckPoint
from .motion.axis import Axis, default_axis_configs
from .motion.mounts import Mount
from .protocol.driver import Controller
from .transport.base import Transport

#: Headroom kept above the tallest labware/obstacle top a safe_move_to
#: crossing passes over (see Robot._path_clearance_mm) -- clearing exactly
#: to that top would graze it, not clear it.
_PATH_CLEARANCE_MARGIN_MM = 5.0


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
        doesn't depend on trusting the handshake alone.

        An axis reporting a negative position (the firmware's own "not
        homed yet" convention -- see raise_z's identical `pos >= 0` check)
        is treated as settled rather than waited on: it will never report a
        comparable value no matter how long this polls, so there's nothing
        trustworthy to verify against for that axis (same reasoning as
        raise_z's own "nothing trustworthy to compare against" fallback,
        which is what calls a verify=True move here in that situation to
        begin with)."""
        deadline = time.monotonic() + timeout
        while True:
            pos = self.controller.report_position()
            if all(
                pos.get(axis) is not None and (pos[axis] < 0 or abs(pos[axis] - target) <= tolerance)
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
        verify: bool = True,
    ) -> None:
        """Cross to the target X/Y at the current Z, then move to the target
        Z -- no clearance-height detour (see safe_move_to for that arc).
        X/Y always goes first, as two separate blocking commands rather than
        one bundled multi-axis move: firmware happens to prioritize X/Y
        stepping over Z today, but a mounted tip dragging across labware if
        that ever isn't true (different firmware revision, etc.) is exactly
        the failure this guards against without relying on it.

        verify: also poll-confirm each leg actually reached its target (see
        _await_settled) before moving on -- on by default: a G-code move's
        'ok' means the firmware considers it done, not that it's physically
        arrived (see _await_settled's own docstring), so back-to-back
        commands with no verification between them can get cut short or
        reordered in effect -- confirmed against real hardware (a routine
        skipped straight to its last few targets, nearly clipping the
        trash bin, with every intermediate move's 'ok' having already come
        back). Pass verify=False to opt back out for a specific call that
        doesn't need it (e.g. a tight interactive-jog loop, where the
        latency cost outweighs the benefit)."""
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
        verify: bool = True,
    ) -> None:
        """Command only the mount's vertical axis to a deck-Z height. See
        move_to's own docstring for what `verify` (on by default) buys."""
        cal = self._require_cal()
        axis = cal.vertical_axis(side)
        mz = cal.deck_to_motor(DeckPoint(0, 0, deck_z_mm), side, self.tip_offset(side))[axis]
        (self.controller.linear_move if feed else self.controller.rapid_move)(
            {axis: mz}, **({"feed": feed} if feed else {})
        )
        if verify:
            self._await_settled({axis: mz})

    def raise_z(
        self, side: MountSide, clearance_mm: float | None = None, *, verify: bool = True
    ) -> None:
        """Ensure this mount's Z/A is at or above clearance height --
        raising if it's currently below, but issuing no move at all if
        it's already there or higher.

        Deliberately NOT "move to exactly clearance unconditionally":
        safe_move_to's whole X/Y-safe arc relies on this step being a pure
        raise, completed before any X/Y crossing, so a mounted tip never
        drags through something on the way up. A mount that happens to
        already be above clearance (fresh off homing, or simply left
        higher by whatever ran before this) would otherwise get pulled
        DOWN to exactly clearance right where it currently sits -- BEFORE
        crossing X/Y -- which is exactly the unplanned descent this arc
        exists to prevent, not cause. If the current height can't be
        determined (axis not yet homed, or no calibration/z_zero to
        invert against), falls back to the original unconditional move --
        the safest option when there's nothing trustworthy to compare
        against.

        verify: see move_to's own docstring -- on by default."""
        target = clearance_mm if clearance_mm is not None else self.travel_z_mm
        cal = self._require_cal()
        axis = cal.vertical_axis(side)
        if axis is not None:
            pos = self.controller.report_position().get(axis)
            if pos is not None and pos >= 0:
                current = cal.motor_to_deck_z(pos, side, self.tip_offset(side))
                if current is not None and current >= target:
                    return  # already at/above clearance -- nothing to do
        self.move_vertical_to(target, side, verify=verify)

    def _current_deck_xy(self, side: MountSide) -> tuple | None:
        """This mount's current (x, y) in deck mm, or None if it can't be
        determined (axes not yet homed -- report_position reports -1 for
        those, mirroring raise_z's own check -- or no calibration). Used
        by _path_clearance_mm; falling back to the plain clearance_mm/
        travel_z_mm default when unknown is always at least as safe as
        before this existed, never less."""
        if self.calibration is None:
            return None
        pos = self.controller.report_position()
        mx, my = pos.get(AxisId.X), pos.get(AxisId.Y)
        if mx is None or my is None or mx < 0 or my < 0:
            return None
        return self.calibration.motor_to_deck_xy(mx, my, side)

    def _slots_crossed(self, start_xy: tuple, end_xy: tuple) -> list:
        """Every deck slot whose footprint overlaps the axis-aligned
        bounding box spanning start_xy to end_xy -- a conservative stand-in
        for "what does a working-height crossing between these two points
        pass over" (the actual XY move need not be perfectly straight, and
        this also always includes the start/end slots themselves, which
        need clearing too, not just whatever's strictly between them)."""
        if self.deck is None:
            return []
        lo_x, hi_x = sorted((start_xy[0], end_xy[0]))
        lo_y, hi_y = sorted((start_xy[1], end_xy[1]))
        crossed = []
        for slot in self.deck.slots.values():
            if not slot.size or not slot.size[0] or not slot.size[1]:
                continue  # a dimensionless slot has no footprint to overlap
            sx, sy = slot.origin.x, slot.origin.y
            sw, sh = slot.size
            if sx <= hi_x and sx + sw >= lo_x and sy <= hi_y and sy + sh >= lo_y:
                crossed.append(slot)
        return crossed

    def _slot_top_height_mm(self, slot) -> float:
        """The tallest surface known to occupy `slot`, deck-mm from the
        deck plane: whatever labware is placed there (its wells' own top
        height -- the same datum Well.offset.z already uses) and any
        SlotObstacle/bin walls built into the slot itself (see
        deck.Slot/SlotObstacle -- previously "purely descriptive, nothing
        in motion planning consults this", which is exactly the gap
        _path_clearance_mm closes)."""
        tallest = max((o.height_mm for o in slot.obstacles), default=0.0)
        tallest = max(tallest, slot.wall_height_mm)
        for lw in self.labware.values():
            if lw.slot is slot and lw.wells:
                tallest = max(tallest, max(w.offset.z for w in lw.wells.values()))
        return tallest

    def _path_clearance_mm(self, side: MountSide, target_xy: tuple, requested_mm: float) -> float:
        """`requested_mm` (the caller's own clearance_mm/travel_z_mm
        default), raised if needed to clear the tallest labware/obstacle
        top in any slot between this mount's current position and
        `target_xy` (see _slots_crossed/_slot_top_height_mm) -- e.g. a tall
        object loaded in a slot between source and destination, which one
        fixed travel_z_mm can't account for if it's taller than whatever
        travel_z_mm happened to be set for. Never returns less than
        `requested_mm` -- only ever raises it, and falls back to it
        unchanged whenever the current position can't be determined."""
        start_xy = self._current_deck_xy(side)
        if start_xy is None:
            return requested_mm
        tallest = max(
            (self._slot_top_height_mm(slot) for slot in self._slots_crossed(start_xy, target_xy)),
            default=0.0,
        )
        return max(requested_mm, tallest + _PATH_CLEARANCE_MARGIN_MM) if tallest else requested_mm

    def safe_move_to(
        self,
        point: DeckPoint,
        side: MountSide,
        clearance_mm: float | None = None,
        feed: int | None = None,
        *,
        verify: bool = True,
    ) -> None:
        """Move in the order X/Y-safe arc: (1) raise this mount's Z/A to
        clearance height, (2) cross to the target's X/Y, (3) descend Z/A to
        the target -- so a mounted tip never drags across labware. The
        clearance height itself is `clearance_mm`/travel_z_mm, boosted if
        needed to clear whatever's tallest between here and there (see
        _path_clearance_mm) -- covers both crossing between slots (a tall
        object loaded in a slot the direct route passes over) and moving
        within one labware's own wells (a source/destination pair whose
        shared plate has taller neighboring wells or a lid in between).

        verify: see move_to's own docstring -- on by default."""
        cal = self._require_cal()
        base_clr = clearance_mm if clearance_mm is not None else self.travel_z_mm
        clr = self._path_clearance_mm(side, (point.x, point.y), base_clr)
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
