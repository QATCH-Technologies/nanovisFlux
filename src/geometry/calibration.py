from __future__ import annotations

from dataclasses import dataclass, field

from ..core import AxisId, MountSide
from ..motion.mounts import MOUNT_OFFSET_MM
from .coordinates import DeckPoint
from .transform import AffineTransform2D
from .units import AxisScale


@dataclass
class ZContact:
    """Result of a Z calibration touch, however it was made."""

    side: MountSide
    contact_microsteps: int  # vertical-axis position at contact
    z_zero_microsteps: int  # implied nozzle-reference z_zero
    tip_length_mm: float
    xy: DeckPoint | None = None  # set for an automated probe; None for a manual touch-off


@dataclass
class DeckCalibration:
    """The bridge between deck space (mm) and motor space (microsteps).

    XY is a full affine transform learned from calibration points. Z is a
    per-mount linear map: a reference microstep value at deck z = 0 plus a
    scale. Home is up, so descending toward the deck increases microsteps.
    """

    xy: AffineTransform2D
    z_scale: AxisScale
    z_zero: dict = field(default_factory=dict)  # MountSide -> microsteps at deck z=0

    def vertical_axis(self, side: MountSide) -> AxisId | None:
        """None for a mount with no vertical axis (e.g. MountSide.REAR)."""
        if side is MountSide.LEFT:
            return AxisId.Z
        if side is MountSide.RIGHT:
            return AxisId.A
        return None

    def _reference_xy(self, point: DeckPoint, side: MountSide) -> tuple:
        """Motor (X, Y) that places ``side``'s mount at deck ``point``.

        ``self.xy`` maps the gantry's shared X/Y *reference* point (not any
        particular mount) between deck mm and motor microsteps. Each mount
        sits at a fixed mechanical offset from that reference (see
        ``motion.mounts.MOUNT_OFFSET_MM``): ``mount_deck_pos =
        reference_deck_pos + offset``, so placing the mount at ``point``
        means driving the reference to ``point - offset`` first. Subtracting
        the offset *before* ``xy.apply`` (rather than converting it via a
        flat per-axis mm/microstep scale) carries it through the affine's
        own rotation/scale, so this stays exact even for a rotated
        calibration -- not just the axis-aligned case.
        """
        ox, oy = MOUNT_OFFSET_MM.get(side, (0.0, 0.0))
        return self.xy.apply(point.x - ox, point.y - oy)

    def deck_to_motor(self, point: DeckPoint, side: MountSide, tip_length_mm: float = 0.0) -> dict:
        """Motor targets that place the *working point* at ``point`` (deck mm).

        ``z_zero`` is the nozzle-reference position (tip-independent), so the
        tip end is ``tip_length_mm`` below the nozzle. To land the tip end at
        ``point.z`` the nozzle must sit ``tip_length_mm`` higher, i.e. fewer
        microsteps (home is up). One calibration serves every tip length.
        """
        mx, my = self._reference_xy(point, side)
        targets = {AxisId.X: round(mx), AxisId.Y: round(my)}
        vertical = self.vertical_axis(side)
        if vertical is not None:
            zref = self.z_zero.get(side, 0)
            targets[vertical] = int(zref - self.z_scale.to_microsteps(point.z + tip_length_mm))
        return targets

    def z_zero_from_contact(self, contact_microsteps: int, tip_length_mm: float = 0.0) -> int:
        """Given the microsteps at which a probe of length ``tip_length_mm``
        touched deck z = 0, return the nozzle-reference ``z_zero``.

        At contact the tip end is on the surface, so the nozzle reference is
        ``tip_length_mm`` above it: ``z_zero = contact + msteps(tip_length)``.
        """
        return int(contact_microsteps + self.z_scale.to_microsteps(tip_length_mm))

    def motor_to_deck_xy(self, mx: float, my: float, side: MountSide | None = None) -> tuple:
        """Inverse of ``_reference_xy``: the deck (x, y) under raw motor
        position ``(mx, my)``. ``side=None`` (the default) reports the
        gantry reference point itself, as before. Passing ``side`` instead
        reports where THAT mount's tip actually is -- add its fixed offset
        back on top of the reference point (mirrors ``_reference_xy``'s
        subtraction)."""
        rx, ry = self.xy.inverse().apply(mx, my)
        if side is None:
            return rx, ry
        ox, oy = MOUNT_OFFSET_MM.get(side, (0.0, 0.0))
        return rx + ox, ry + oy

    def motor_to_deck_z(
        self, raw_microsteps: float, side: MountSide, tip_length_mm: float = 0.0
    ) -> float | None:
        """Inverse of ``deck_to_motor``'s Z half: the deck-mm height (of
        whatever ``tip_length_mm`` currently hangs below the nozzle) that
        ``side``'s vertical axis being at ``raw_microsteps`` corresponds to.
        None for a mount with no vertical axis (mirrors ``vertical_axis``)
        or one with no ``z_zero`` calibrated yet -- there's nothing to
        invert against. Used by ``Robot.raise_z`` to tell whether a mount
        is already above a target clearance height before commanding a
        move that would otherwise unconditionally pull it down to exactly
        that height."""
        vertical = self.vertical_axis(side)
        if vertical is None or side not in self.z_zero:
            return None
        zref = self.z_zero[side]
        return self.z_scale.to_mm(zref - raw_microsteps) - tip_length_mm

    # -- z calibration: finding z_zero is calibrating the deck's Z ------
    #
    # Both methods below need a live ``robot`` (controller + axis config),
    # so the import of protocol types stays lazy -- geometry otherwise has
    # no dependency on the protocol layer, and importing this module should
    # never require one.
    def probe_z_zero(
        self,
        robot,
        side: MountSide,
        xy: DeckPoint,
        tip_length_mm: float = 0.0,
        *,
        feed: int = 100,
        safe_up_microsteps: int = 2000,
        max_descent_microsteps: int | None = None,
        commit: bool = True,
    ) -> ZContact:
        """Find z_zero for ``side`` by touching a conductive surface at
        ``xy`` with an automated G38.2 probe. Works in raw microsteps for the
        descent, so it does NOT need a prior Z calibration (that would be
        circular) -- only the XY affine, to position over the target.

        Whatever is on the nozzle -- a bare calibration probe or a
        disposable tip -- is described by ``tip_length_mm``; the result is
        the tip-independent nozzle reference, written back into ``z_zero``.
        """
        from ..protocol.commands import ProbeMode
        from ..protocol.errors import ProbeError

        ctrl = robot.controller
        vertical = self.vertical_axis(side)
        max_descent = max_descent_microsteps or robot.axes[vertical].config.endstop_limit

        # 1. Lift to a safe height, then position over the target in XY.
        ctrl.rapid_move({vertical: safe_up_microsteps})
        mx, my = self._reference_xy(xy, side)
        ctrl.rapid_move({AxisId.X: round(mx), AxisId.Y: round(my)})

        # 2. Probe down (error if it never touches).
        result = ctrl.probe(vertical, max_descent, feed=feed, mode=ProbeMode.TOWARD_OR_FAIL)
        if not result.contacted:
            raise ProbeError(f"no surface found probing {side.value} at " f"({xy.x}, {xy.y})")

        # 3. Read the exact contact microsteps and derive the nozzle z_zero.
        contact = ctrl.report_position()[vertical]
        z_zero = self.z_zero_from_contact(contact, tip_length_mm)
        if commit:
            self.z_zero[side] = z_zero

        # 4. Retract to safe height.
        ctrl.rapid_move({vertical: safe_up_microsteps})
        return ZContact(side, contact, z_zero, tip_length_mm, xy)

    def touch_off_z_zero(
        self, robot, side: MountSide, tip_length_mm: float | None = None, commit: bool = True
    ) -> ZContact:
        """Derive z_zero for ``side`` from the mount's *current* position --
        call after manually jogging the tip end down onto a reference
        surface. An alternative to ``probe_z_zero`` for tips too soft or
        fragile to drive into a hard stop, or when feel/sight is the only
        sensor on hand.

        Tip-agnostic the same way: it never assumes what's on the nozzle.
        ``tip_length_mm`` defaults to whatever tip/tool is attached to
        ``side`` right now (``robot.tip_offset``); pass an explicit value
        when jogging with a bare calibration pin or an unregistered tip.
        """
        vertical = self.vertical_axis(side)
        length = robot.tip_offset(side) if tip_length_mm is None else tip_length_mm
        contact = robot.controller.report_position()[vertical]
        z_zero = self.z_zero_from_contact(contact, length)
        if commit:
            self.z_zero[side] = z_zero
        return ZContact(side, contact, z_zero, length)

    @classmethod
    def from_points(cls, deck_pts, motor_xy, z_scale, z_zero=None) -> "DeckCalibration":
        xy = AffineTransform2D.from_point_pairs([(p.x, p.y) for p in deck_pts], list(motor_xy))
        return cls(xy=xy, z_scale=z_scale, z_zero=z_zero or {})
