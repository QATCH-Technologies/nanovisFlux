"""
Pipette, plunger, and tip-calibration models and motion primitives.

This module defines the data models and tool implementation used to control
single- and multi-channel pipettes. It provides both a simple linear plunger
model and an empirical, direction-specific calibration model that maps
between liquid volume and plunger microsteps.

Plunger calibration is maintained separately for aspiration and dispensing to
account for mechanical effects such as seal friction, compliance, and
backlash. When a calibration is available for the currently installed tip,
the pipette uses the empirical mapping; otherwise, it falls back to the
pipette's linear :class:`PlungerModel`.

The :class:`Pipette` class also manages installed tip geometry, volume state,
tip pickup, tip ejection, and tip-aware deck-space positioning. Once a tip is
installed, its physical length is exposed as a Z-axis offset so robot motion
targets the tip end rather than the bare nozzle reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from ..geometry.coordinates import DeckPoint
from .base import Tool
from .tips import TipGeometry, TipPickup


@dataclass
class PlungerModel:
    """Define a linear relationship between liquid volume and plunger travel.

    `PlungerModel` provides a simple approximation of pipette plunger
    behavior in which volume changes linearly with plunger microsteps. It is
    used as the default model when no empirical calibration is available for
    the currently installed tip.

    Args:
        microsteps_per_ul: Number of plunger microsteps corresponding to one
            microliter of liquid.
        bottom_microsteps: Plunger position corresponding to zero volume.
            Defaults to `0`.

    Attributes:
        microsteps_per_ul: Linear conversion factor between volume and
            plunger travel.
        bottom_microsteps: Plunger position representing zero liquid volume.
    """

    microsteps_per_ul: float
    bottom_microsteps: int = 0

    def volume_to_microsteps(self, ul: float) -> int:
        """Convert a liquid volume to a plunger position.

        Args:
            ul: Target liquid volume in microliters.

        Returns:
            The corresponding plunger position in microsteps.
        """
        return int(self.bottom_microsteps - round(ul * self.microsteps_per_ul))


def _sorted_monotonic(points: tuple, label: str) -> tuple:
    """Validate and order plunger calibration points by volume.

    Calibration points are sorted in ascending order of volume and validated
    to ensure that plunger microsteps decrease as volume increases. This
    monotonic relationship is required for interpolation in both directions.

    Args:
        points: Sequence of :class:`PlungerCalibrationPoint` objects.
        label: Human-readable name identifying the calibration direction,
            typically `"aspirate"` or `"dispense"`.

    Returns:
        A tuple containing the calibration points sorted by ascending
        `volume_ul`.

    Raises:
        ValueError: If fewer than two calibration points are provided or if
            the calibration points are not monotonically decreasing in
            microsteps as volume increases.
    """
    if len(points) < 2:
        raise ValueError(f"{label} calibration needs at least 2 points, got {len(points)}")
    ordered = tuple(sorted(points, key=lambda p: p.volume_ul))
    for a, b in pairwise(ordered):
        if b.microsteps >= a.microsteps:
            raise ValueError(
                f"{label} calibration is not monotonic: {a.volume_ul:g}uL -> {a.microsteps} "
                f"microsteps, but {b.volume_ul:g}uL -> {b.microsteps} (expected fewer microsteps "
                "for more volume)"
            )
    return ordered


def _interp(points: list[tuple[float, float]], x: float) -> float:
    """Perform piecewise-linear interpolation or local extrapolation.

    Interpolation is performed between the two calibration points surrounding
    `x`. Values outside the calibrated range are extrapolated using the
    nearest endpoint segment rather than a global fit, limiting the influence
    of measurement noise elsewhere in the calibration curve.

    Args:
        points: Ordered `(x, y)` pairs with ascending X values.
        x: X coordinate at which to interpolate or extrapolate.

    Returns:
        The interpolated or locally extrapolated Y value.
    """
    if x <= points[0][0]:
        (x0, y0), (x1, y1) = points[0], points[1]
    elif x >= points[-1][0]:
        (x0, y0), (x1, y1) = points[-2], points[-1]
    else:
        for (x0, y0), (x1, y1) in pairwise(points):
            if x0 <= x <= x1:
                break
        else:
            raise ValueError("x is outside the calibration points")
    return y0 + (x - x0) / (x1 - x0) * (y1 - y0)


@dataclass(frozen=True)
class PlungerCalibrationPoint:
    """Represent one measured plunger calibration point.

    A calibration point records the relationship between a commanded plunger
    position and the externally measured liquid volume produced by that
    position.

    Args:
        microsteps: Plunger position in microsteps, using the same coordinate
            system as :attr:`PlungerModel.bottom_microsteps`.
        volume_ul: Externally measured liquid volume in microliters.
    """

    microsteps: int
    volume_ul: float


@dataclass(frozen=True)
class PlungerCalibration:
    """Define empirical, direction-specific plunger calibration curves.

    `PlungerCalibration` replaces the single linear conversion factor of
    :class:`PlungerModel` with piecewise-linear mappings derived from measured
    calibration points.

    Aspiration and dispensing are calibrated independently because mechanical
    effects such as seal friction, O-ring compliance, and backlash can cause
    the same nominal volume to correspond to different plunger positions
    depending on motion direction.

    Calibration points are normalized and validated during initialization.
    Volume-to-position conversion interpolates in volume space, while
    position-to-volume conversion explicitly reorders the points into
    ascending microstep order before interpolation.

    Args:
        aspirate_points: Calibration points measured during aspiration.
        dispense_points: Calibration points measured during dispensing.

    Attributes:
        aspirate_points: Validated aspiration calibration points ordered by
            ascending volume.
        dispense_points: Validated dispensing calibration points ordered by
            ascending volume.
    """

    aspirate_points: tuple
    dispense_points: tuple

    def __post_init__(self) -> None:
        """Validate and normalize both calibration point sets.

        Calibration points are converted to tuples, sorted by ascending volume,
        and checked for the required monotonic relationship between volume and
        plunger position.
        """
        object.__setattr__(
            self, "aspirate_points", _sorted_monotonic(tuple(self.aspirate_points), "aspirate")
        )
        object.__setattr__(
            self, "dispense_points", _sorted_monotonic(tuple(self.dispense_points), "dispense")
        )

    def microsteps_for_volume(self, ul: float, *, aspirating: bool) -> int:
        """Convert a liquid volume to a calibrated plunger position.

        Args:
            ul: Target liquid volume in microliters.
            aspirating: If `True`, use the aspiration calibration; otherwise,
                use the dispensing calibration.

        Returns:
            The calibrated plunger position in microsteps.
        """
        points = self.aspirate_points if aspirating else self.dispense_points
        return round(_interp([(p.volume_ul, p.microsteps) for p in points], ul))

    def volume_for_microsteps(self, microsteps: int, *, aspirating: bool) -> float:
        """Convert a plunger position to a calibrated liquid volume.

        Args:
            microsteps: Plunger position in microsteps.
            aspirating: If `True`, use the aspiration calibration; otherwise,
                use the dispensing calibration.

        Returns:
            The interpolated or extrapolated liquid volume in microliters.
        """
        points = self.aspirate_points if aspirating else self.dispense_points
        pairs = sorted((p.microsteps, p.volume_ul) for p in points)
        return _interp(pairs, microsteps)

    @classmethod
    def from_pairs(cls, aspirate, dispense) -> PlungerCalibration:
        """Construct a calibration from raw measured point pairs.

        This convenience constructor converts raw `(microsteps, volume_ul)`
        tuples into :class:`PlungerCalibrationPoint` instances before creating
        the calibration object.

        Args:
            aspirate: Iterable of `(microsteps, volume_ul)` pairs measured during
                aspiration.
            dispense: Iterable of `(microsteps, volume_ul)` pairs measured during
                dispensing.

        Returns:
            A validated :class:`PlungerCalibration` containing the supplied
            aspiration and dispensing measurements.
        """
        return cls(
            aspirate_points=tuple(PlungerCalibrationPoint(m, v) for m, v in aspirate),
            dispense_points=tuple(PlungerCalibrationPoint(m, v) for m, v in dispense),
        )


class Pipette(Tool):
    """Control a single- or multi-channel pipette mounted on the robot.

    A `Pipette` drives the plunger axis associated with its mount. For a
    left-mounted pipette this is the B axis; for a right-mounted pipette it
    is the C axis. Multi-channel pipettes share one plunger stroke across all
    channels, so `channels` describes the number of wells or tips handled
    per stroke rather than changing the plunger conversion.

    The pipette tracks its current liquid volume and installed tip. Tip
    geometry is incorporated into robot-level Z positioning so that motion
    targets refer to the tip end rather than the bare nozzle.

    When an empirical :class:`PlungerCalibration` exists for the installed
    tip, aspirate and dispense operations use their respective calibrated
    curves. Otherwise, the configured :class:`PlungerModel` provides the
    linear fallback conversion.

    Args:
        name: Name used to identify the pipette instance.
        plunger: Linear fallback model for converting volume to plunger
            microsteps.
        max_volume_ul: Maximum liquid volume the pipette can hold, in
            microliters.
        tip_calibrations: Optional mapping from tip names to empirical
            :class:`PlungerCalibration` instances.
        brand: Pipette manufacturer or vendor name.
        channels: Number of channels handled by one plunger stroke.

    Attributes:
        name: Pipette instance name.
        brand: Pipette manufacturer or vendor.
        channels: Number of pipette channels.
        plunger: Linear fallback plunger model.
        max_volume_ul: Maximum supported liquid volume.
        current_volume_ul: Currently tracked liquid volume.
        current_tip: Installed :class:`TipGeometry`, or `None`.
        tip_calibrations: Empirical calibration curves keyed by tip name.
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
        """Initialize a pipette and its plunger, capacity, channel, and tip calibration state.

        Args:
            name: Unique name identifying the pipette instance.
            plunger: Plunger model used to convert liquid volumes to controller
                microsteps when no tip-specific calibration is available.
            max_volume_ul: Maximum liquid volume the pipette can aspirate, in
                microliters.
            tip_calibrations: Optional mapping from tip geometry names to empirical
                :class:`PlungerCalibration` instances. When a calibration is not
                available for the currently installed tip, the pipette falls back to
                the linear `plunger` model.
            brand: Vendor or manufacturer name. An empty string indicates that the
                manufacturer is unknown or that the pipette is custom.
            channels: Number of independently handled channels represented by the
                pipette. The value is descriptive of the physical pipette; all
                channels share the same plunger stroke and are therefore not modeled
                as independently actuated.
        """
        super().__init__()
        self.name = name
        self.brand = brand
        self.channels = channels
        self.plunger = plunger
        self.max_volume_ul = max_volume_ul
        self.current_volume_ul = 0.0
        self.current_tip: TipGeometry | None = None
        self.tip_calibrations: dict = tip_calibrations or {}

    def uses_plunger(self) -> bool:
        """Indicate that the pipette requires its mount's plunger axis.

        Returns:
            Always `True` for a pipette.
        """
        return True

    def tip_offset_mm(self) -> float:
        """Return the installed tip's physical length.

        The value is used by the robot's coordinate transformations so deck-space
        Z targets position the end of the installed tip rather than the bare
        pipette nozzle.

        Returns:
            Installed tip length in millimeters, or `0.0` when no tip is
            attached.
        """
        return self.current_tip.length_mm if self.current_tip else 0.0

    def _calibration_for_current_tip(self) -> PlungerCalibration | None:
        """Return the empirical calibration for the installed tip.

        Returns:
            The :class:`PlungerCalibration` associated with the currently
            installed tip, or `None` when no tip is installed or no calibration
            has been registered for that tip.
        """
        if self.current_tip is None:
            return None
        return self.tip_calibrations.get(self.current_tip.name)

    def _move_plunger_to(self, ul: float, feed=None, *, aspirating: bool) -> None:
        """Move the plunger to the position corresponding to a target volume.

        Uses the empirical calibration associated with the current tip when one
        is available; otherwise, falls back to the pipette's linear
        :class:`PlungerModel`.

        The commanded move is explicitly position-verified after transmission.
        This is necessary because the method communicates directly with the
        controller rather than through the robot's higher-level motion wrappers.

        Args:
            ul: Target liquid volume in microliters.
            feed: Optional plunger feed rate in controller units.
            aspirating: Whether the target position is being reached as part of
                an aspiration operation. Selects the corresponding empirical
                calibration curve.

        Raises:
            RuntimeError: If the pipette is unmounted or the mounted pipette has
                no plunger axis.
        """
        mount = self._mount
        robot = self._robot
        if mount is None or robot is None:
            raise RuntimeError("pipette must be mounted before moving the plunger")
        axis = mount.plunger
        if axis is None:
            raise RuntimeError("mounted pipette has no plunger axis")
        calibration = self._calibration_for_current_tip()
        target = (
            calibration.microsteps_for_volume(ul, aspirating=aspirating)
            if calibration is not None
            else self.plunger.volume_to_microsteps(ul)
        )

        def _send():
            robot.controller.linear_move({axis: target}, feed=feed)

        _send()
        robot._await_settled({axis: target}, resend=_send)

    def aspirate(self, ul: float, feed=None) -> None:
        """Aspirate the requested volume of liquid.

        Updates the tracked pipette volume and moves the plunger using the
        aspiration calibration for the installed tip when available.

        Args:
            ul: Volume to aspirate in microliters.
            feed: Optional plunger feed rate in controller units.

        Raises:
            ValueError: If the requested aspiration would exceed the pipette's
                configured maximum capacity.
        """
        if self.current_volume_ul + ul > self.max_volume_ul:
            raise ValueError("aspirate would exceed pipette capacity")
        self.current_volume_ul += ul
        self._move_plunger_to(self.current_volume_ul, feed, aspirating=True)

    def dispense(self, ul: float | None = None, feed=None) -> None:
        """Dispense liquid from the pipette.

        If `ul` is omitted, the entire currently tracked volume is dispensed.
        The tracked volume is reduced before the plunger is moved using the
        dispensing calibration for the installed tip when available.

        Args:
            ul: Volume to dispense in microliters. If `None`, dispense the
                entire tracked volume.
            feed: Optional plunger feed rate in controller units.
        """
        ul = self.current_volume_ul if ul is None else ul
        self.current_volume_ul = max(0.0, self.current_volume_ul - ul)
        self._move_plunger_to(self.current_volume_ul, feed, aspirating=False)

    def blow_out(self, feed=None) -> None:
        """Fully empty the pipette using a dispense-direction plunger move.

        Resets the tracked liquid volume to zero and drives the plunger to the
        zero-volume position using the dispensing calibration when available.

        Args:
            feed: Optional plunger feed rate in controller units.
        """
        self.current_volume_ul = 0.0
        self._move_plunger_to(0.0, feed, aspirating=False)

    def pick_up_tip(self, xy: DeckPoint, tip: TipGeometry, pickup: TipPickup) -> None:
        """Pick up and mechanically seat a pipette tip from a rack.

        Moves to the supplied rack position, presses the bare nozzle into the tip
        according to the configured :class:`TipPickup` sequence, and optionally
        performs a four-direction well-wall touch pattern to square the tip.

        The seating strokes occur before `current_tip` is updated, so all Z
        positions during the pickup sequence are interpreted relative to the bare
        nozzle. After the final seating stroke, the tip becomes active and its
        length is applied to subsequent robot positioning. The mount is then
        raised to the configured travel clearance.

        Args:
            xy: Deck-space XY position of the tip in the rack.
            tip: Physical geometry definition of the tip being installed.
            pickup: Mechanical parameters controlling the pickup and optional
                alignment sequence.

        Raises:
            RuntimeError: If a tip is already installed or if the pipette is unmounted.
        """
        if self.current_tip is not None:
            raise RuntimeError("a tip is already attached; drop it first")
        robot, mount = self._robot, self._mount
        if robot is None or mount is None:
            raise RuntimeError("pipette must be attached before picking up a tip")
        side = mount.side
        top = pickup.press_z_mm
        robot.safe_move_to(DeckPoint(xy.x, xy.y, top), side)
        for stroke in range(pickup.presses):
            robot.move_vertical_to(top - pickup.engage_mm, side, feed=pickup.feed)
            if stroke < pickup.presses - 1:
                robot.move_vertical_to(top + pickup.retract_mm, side, feed=pickup.feed)

        if pickup.touch_offset_mm:
            touch_retract = (
                pickup.engage_mm / 2 if pickup.touch_retract_mm is None else pickup.touch_retract_mm
            )
            touch_feed = pickup.touch_feed or pickup.feed
            robot.move_vertical_to(top - pickup.engage_mm + touch_retract, side, feed=touch_feed)
            d = pickup.touch_offset_mm
            for tx, ty in (
                (xy.x - d, xy.y),
                (xy.x + d, xy.y),
                (xy.x, xy.y),
                (xy.x, xy.y - d),
                (xy.x, xy.y + d),
                (xy.x, xy.y),
            ):
                robot.move_horizontal_to(tx, ty, side, feed=touch_feed)

        self.current_tip = tip
        robot.raise_z(side)

    def drop_tip(
        self, xy: DeckPoint | None = None, eject_z_mm: float | None = None, side_offset=None
    ) -> None:
        """Eject the currently installed tip.

        Optionally moves to the specified deck-space drop position before driving
        the mount's plunger to its configured lower endstop, which performs the
        hardware tip-ejection action. After ejection, the installed tip and
        tracked liquid volume are cleared and the plunger is returned to its
        zero-volume position.

        The mount is raised to travel clearance after the tip has been ejected.

        Args:
            xy: Optional deck-space XY location at which to eject the tip.
            eject_z_mm: Optional deck-space Z height for the ejection position.
                A movement to `xy` is performed only when both `xy` and
                `eject_z_mm` are supplied.
            side_offset: Optional side-specific offset reserved for tip-drop
                positioning. Its interpretation is implementation-dependent.

        Raises:
            RuntimeError: If no tip is currently installed or if the pipette is unmounted
                or if the pipette has no plunger axis.
        """
        if self.current_tip is None:
            raise RuntimeError("no tip to drop")
        robot, mount = self._robot, self._mount
        if robot is None or mount is None:
            raise RuntimeError("pipette must be attached before dropping a tip")
        side = mount.side
        if xy is not None and eject_z_mm is not None:
            robot.safe_move_to(DeckPoint(xy.x, xy.y, eject_z_mm), side)
        axis = mount.plunger
        if axis is None:
            raise RuntimeError("pipette mount has no plunger axis")
        limit = robot.axes[axis].config.endstop_limit

        def _send():
            robot.controller.linear_move({axis: limit})

        _send()
        robot._await_settled({axis: limit}, resend=_send)
        self.current_tip = None
        self.current_volume_ul = 0.0
        self._move_plunger_to(0.0, aspirating=False)
        robot.raise_z(side)
