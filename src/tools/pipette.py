from __future__ import annotations

from dataclasses import dataclass

from ..geometry.coordinates import DeckPoint
from .base import Tool
from .tips import TipGeometry, TipPickup


@dataclass
class PlungerModel:
    """Maps volume (uL) to plunger microsteps. Calibrate microsteps_per_ul
    and the fully-dispensed position for your specific pipette."""

    microsteps_per_ul: float
    bottom_microsteps: int = 0  # plunger position for 0 uL

    def volume_to_microsteps(self, ul: float) -> int:
        return int(self.bottom_microsteps - round(ul * self.microsteps_per_ul))


def _sorted_monotonic(points: tuple, label: str) -> tuple:
    """Sort `points` (PlungerCalibrationPoint) by volume_ul ascending and
    check microsteps fall alongside it..."""
    if len(points) < 2:
        raise ValueError(f"{label} calibration needs at least 2 points, got {len(points)}")
    ordered = tuple(sorted(points, key=lambda p: p.volume_ul))
    for a, b in zip(ordered, ordered[1:]):
        if b.microsteps >= a.microsteps:
            raise ValueError(
                f"{label} calibration is not monotonic: {a.volume_ul:g}uL -> {a.microsteps} "
                f"microsteps, but {b.volume_ul:g}uL -> {b.microsteps} (expected fewer microsteps "
                "for more volume)"
            )
    return ordered


def _interp(points: list, x: float) -> float:
    """Piecewise-linear interpolation through `points` ((x, y) pairs,
    ascending by x) -- exact at each point, extrapolating past either end
    using the nearest segment's own slope rather than a global fit that a
    couple of noisy points could swing wildly."""
    if x <= points[0][0]:
        (x0, y0), (x1, y1) = points[0], points[1]
    elif x >= points[-1][0]:
        (x0, y0), (x1, y1) = points[-2], points[-1]
    else:
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x0 <= x <= x1:
                break
    return y0 + (x - x0) / (x1 - x0) * (y1 - y0)


@dataclass(frozen=True)
class PlungerCalibrationPoint:
    """One measured calibration point: commanding the plunger to
    ``microsteps`` (the same space as ``PlungerModel.bottom_microsteps``)
    produced ``volume_ul`` of liquid, measured externally -- e.g. weighed
    on a scale after a full dispense."""

    microsteps: int
    volume_ul: float


@dataclass(frozen=True)
class PlungerCalibration:
    """Empirical steps<->volume mapping for one (pipette, tip) combination,
    replacing ``PlungerModel``'s single linear factor with piecewise-linear
    interpolation between measured points -- a real plunger's volume-per-
    step is rarely perfectly linear or direction-symmetric (seal friction,
    o-ring compliance, backlash).

    Aspirate and dispense are calibrated SEPARATELY: seal friction/backlash
    commonly make the two strokes disagree for the same nominal volume, so
    a single shared curve would bake in a direction-dependent error.
    ``Pipette._move_plunger_to`` picks whichever applies via `aspirating`.
    """

    aspirate_points: tuple  # tuple[PlungerCalibrationPoint, ...]
    dispense_points: tuple  # tuple[PlungerCalibrationPoint, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "aspirate_points", _sorted_monotonic(tuple(self.aspirate_points), "aspirate")
        )
        object.__setattr__(
            self, "dispense_points", _sorted_monotonic(tuple(self.dispense_points), "dispense")
        )

    def microsteps_for_volume(self, ul: float, *, aspirating: bool) -> int:
        points = self.aspirate_points if aspirating else self.dispense_points
        return round(_interp([(p.volume_ul, p.microsteps) for p in points], ul))

    def volume_for_microsteps(self, microsteps: int, *, aspirating: bool) -> float:
        points = self.aspirate_points if aspirating else self.dispense_points
        # _interp needs its points ascending by x (microsteps here) --
        # aspirate_points/dispense_points are stored ascending by
        # volume_ul instead (see _sorted_monotonic), which is DESCENDING
        # microsteps (more volume = fewer microsteps). Sorting explicitly
        # here rather than relying on that ordering being reversed.
        pairs = sorted((p.microsteps, p.volume_ul) for p in points)
        return _interp(pairs, microsteps)

    @classmethod
    def from_pairs(cls, aspirate, dispense) -> "PlungerCalibration":
        """Build from raw ``(microsteps, volume_ul)`` tuples -- the shape a
        measurement procedure produces directly, without needing the
        caller to construct ``PlungerCalibrationPoint`` objects by hand."""
        return cls(
            aspirate_points=tuple(PlungerCalibrationPoint(m, v) for m, v in aspirate),
            dispense_points=tuple(PlungerCalibrationPoint(m, v) for m, v in dispense),
        )


class Pipette(Tool):
    """A single- or multi-channel pipette. Aspirate/dispense drive the
    plunger axis of whichever mount the pipette is attached to (B on the
    left, C on right) -- one shared plunger stroke moves every channel
    together, so ``channels`` is descriptive (how many tips/wells this
    pipette handles per stroke) rather than something that changes the
    plunger math itself; per-channel-independent aspirate/dispense isn't
    modeled here.

    Once a tip is picked up, ``current_tip`` is set and the robot offsets all
    subsequent Z moves by the tip length so the tip *end* lands on target.
    """

    def __init__(
        self,
        name: str,
        plunger: PlungerModel,
        max_volume_ul: float,
        tip_calibrations: dict | None = None,
        brand: str = "",
        channels: int = 1,
    ):
        super().__init__()
        self.name = name
        self.brand = brand  # vendor/manufacturer, e.g. "Opentrons" -- "" when unknown/custom
        self.channels = channels  # 1 = single-channel; 8/12/... for a multichannel pipette
        self.plunger = plunger
        self.max_volume_ul = max_volume_ul
        self.current_volume_ul = 0.0
        self.current_tip: TipGeometry | None = None
        #: tip name -> PlungerCalibration, empirically measured for this
        #: specific pipette with that tip attached (see PlungerCalibration).
        #: Any tip with no entry here falls back to the linear `plunger`
        #: model -- e.g. before it's ever been characterized.
        self.tip_calibrations: dict = tip_calibrations or {}

    def uses_plunger(self) -> bool:
        return True

    def tip_offset_mm(self) -> float:
        """Length of the installed tip (0 when none) -- read by the robot to
        make Z moves place the tip end rather than the bare nozzle."""
        return self.current_tip.length_mm if self.current_tip else 0.0

    # -- plunger --------------------------------------------------------
    def _calibration_for_current_tip(self) -> PlungerCalibration | None:
        if self.current_tip is None:
            return None
        return self.tip_calibrations.get(self.current_tip.name)

    def _move_plunger_to(self, ul: float, feed=None, *, aspirating: bool) -> None:
        axis = self._mount.plunger
        calibration = self._calibration_for_current_tip()
        target = (
            calibration.microsteps_for_volume(ul, aspirating=aspirating)
            if calibration is not None
            else self.plunger.volume_to_microsteps(ul)
        )

        def _send():
            self._robot.controller.linear_move({axis: target}, feed=feed)

        _send()
        # A move's 'ok' means the firmware considers it done, not that the
        # plunger has physically arrived (see Robot._await_settled's own
        # docstring) -- this call bypasses every Robot.move_* wrapper (which
        # now verify by default for exactly this reason, with stall
        # retries), going straight to the controller, so it needs its own
        # explicit settle-confirmation rather than silently missing out on it.
        self._robot._await_settled({axis: target}, resend=_send)

    def aspirate(self, ul: float, feed=None) -> None:
        if self.current_volume_ul + ul > self.max_volume_ul:
            raise ValueError("aspirate would exceed pipette capacity")
        self.current_volume_ul += ul
        self._move_plunger_to(self.current_volume_ul, feed, aspirating=True)

    def dispense(self, ul: float | None = None, feed=None) -> None:
        ul = self.current_volume_ul if ul is None else ul
        self.current_volume_ul = max(0.0, self.current_volume_ul - ul)
        self._move_plunger_to(self.current_volume_ul, feed, aspirating=False)

    def blow_out(self, feed=None) -> None:
        self.current_volume_ul = 0.0
        self._move_plunger_to(0.0, feed, aspirating=False)

    # -- tips -----------------------------------------------------------
    def pick_up_tip(self, xy: DeckPoint, tip: TipGeometry, pickup: TipPickup) -> None:
        """Seat a tip by pressing onto it, over its position in the rack,
        then (if configured) squares it up by backing off partway and
        tapping it against the rack well's walls in a '+' pattern.

        No tip is installed during the strokes (offset 0), so Z is commanded
        against the bare nozzle reference. After the final stroke the tip is
        recorded and the mount lifts away with the tip-aware offset applied.
        """
        if self.current_tip is not None:
            raise RuntimeError("a tip is already attached; drop it first")
        robot, side = self._robot, self._mount.side
        top = pickup.press_z_mm

        # Arrive above the tip, then press its top with the bare nozzle.
        robot.safe_move_to(DeckPoint(xy.x, xy.y, top), side)
        for stroke in range(pickup.presses):
            robot.move_vertical_to(top - pickup.engage_mm, side, feed=pickup.feed)
            if stroke < pickup.presses - 1:
                robot.move_vertical_to(top + pickup.retract_mm, side, feed=pickup.feed)

        if pickup.touch_offset_mm:
            touch_retract = (
                pickup.engage_mm / 2
                if pickup.touch_retract_mm is None
                else pickup.touch_retract_mm
            )
            touch_feed = pickup.touch_feed or pickup.feed
            robot.move_vertical_to(top - pickup.engage_mm + touch_retract, side, feed=touch_feed)
            d = pickup.touch_offset_mm
            # A '+': one horizontal stroke through center (left, then right),
            # then one vertical stroke through center (front/back), ending
            # back at center -- quick taps, not a slow scrub.
            for tx, ty in (
                (xy.x - d, xy.y),
                (xy.x + d, xy.y),
                (xy.x, xy.y),
                (xy.x, xy.y - d),
                (xy.x, xy.y + d),
                (xy.x, xy.y),
            ):
                robot.move_horizontal_to(tx, ty, side, feed=touch_feed)

        self.current_tip = tip  # now tip-aware
        robot.raise_z(side)  # lift clear at travel height

    def drop_tip(
        self, xy: DeckPoint | None = None, eject_z_mm: float | None = None, side_offset=None
    ) -> None:
        """Eject the tip. On the plunger axes, tip ejection happens at the
        extreme down position (per the hardware notes), so this drives the
        plunger fully down when at the drop location."""
        if self.current_tip is None:
            raise RuntimeError("no tip to drop")
        robot, side = self._robot, self._mount.side
        if xy is not None and eject_z_mm is not None:
            robot.safe_move_to(DeckPoint(xy.x, xy.y, eject_z_mm), side)
        axis = self._mount.plunger
        limit = robot.axes[axis].config.endstop_limit  # extreme down = eject

        def _send():
            robot.controller.linear_move({axis: limit})

        _send()
        robot._await_settled({axis: limit}, resend=_send)  # see _move_plunger_to's own comment
        self.current_tip = None
        self.current_volume_ul = 0.0
        # current_tip is already cleared, so this always uses the linear
        # fallback regardless of `aspirating` -- False just names what
        # "return to top/empty" actually is (a dispense-direction move).
        self._move_plunger_to(0.0, aspirating=False)  # return plunger to top
        robot.raise_z(side)
