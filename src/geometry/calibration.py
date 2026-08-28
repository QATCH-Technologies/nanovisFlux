"""Calibration models and coordinate transforms for robot deck motion.

This module provides the calibration layer that connects physical deck-space
coordinates, expressed in millimeters, with controller-space motor
coordinates, expressed in microsteps.

XY calibration is represented by a full two-dimensional affine transform
learned from corresponding deck and motor calibration points. Mount-specific
mechanical offsets are applied around that shared gantry reference transform so
that each physical mount resolves to its actual deck position, including when
the calibrated XY transform contains rotation or non-uniform scaling.

Z calibration is represented independently for each vertically actuated mount
using a linear axis scale and a calibrated ``z_zero`` reference. The
calibration can be established either automatically through a controller probe
operation or manually by touching a reference surface and recording the
current axis position.

The module intentionally remains largely independent of the protocol layer.
Protocol-specific imports required for automated probing are performed lazily
inside :meth:`DeckCalibration.probe_z_zero`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import AxisId, MountSide
from ..motion.mounts import MOUNT_OFFSET_MM
from .coordinates import DeckPoint
from .transform import AffineTransform2D
from .units import AxisScale


@dataclass
class ZContact:
    """Represent the result of a Z-axis deck contact calibration.

    A contact records both the raw controller position at which the tip or
    probe contacted the reference surface and the derived nozzle-reference
    zero position. The result is independent of whether contact was detected
    automatically by a probe command or manually by an operator.

    Attributes:
        side: Mount whose vertical axis was calibrated.
        contact_microsteps: Vertical-axis position in microsteps at the moment
            the tip or probe contacted the reference surface.
        z_zero_microsteps: Derived nozzle-reference position corresponding to
            deck ``z = 0``.
        tip_length_mm: Length of the attached tip or probe below the nozzle
            reference, in millimeters.
        xy: Deck-space position at which automated contact was performed.
            ``None`` for a manual touch-off.
    """

    side: MountSide
    contact_microsteps: int  # vertical-axis position at contact
    z_zero_microsteps: int  # implied nozzle-reference z_zero
    tip_length_mm: float
    xy: DeckPoint | None = None  # set for an automated probe; None for a manual touch-off


@dataclass
class DeckCalibration:
    """Convert between calibrated deck coordinates and motor coordinates.

    ``DeckCalibration`` is the bridge between physical deck-space positions,
    expressed in millimeters, and controller motor positions, expressed in
    microsteps.

    XY coordinates are transformed using a full affine calibration learned
    from corresponding deck and motor points. Mount-specific mechanical
    offsets are incorporated around this shared gantry reference transform so
    that coordinates represent the selected physical mount rather than merely
    the gantry reference point.

    Z calibration is modeled independently from XY. Each vertically actuated
    mount has a calibrated ``z_zero`` position corresponding to deck
    ``z = 0``, while :attr:`z_scale` converts physical Z distances to motor
    microsteps. Because the robot's home direction is upward, increasing deck
    depth corresponds to increasing vertical-axis microsteps.

    Attributes:
        xy: Affine transformation between deck-space XY coordinates and the
            gantry's motor-space XY reference coordinates.
        z_scale: Unit conversion used to translate physical Z distances into
            motor microsteps.
        z_zero: Mapping from :class:`MountSide` to the calibrated vertical
            motor position corresponding to deck ``z = 0`` for that mount.
    """

    xy: AffineTransform2D
    z_scale: AxisScale
    z_zero: dict = field(default_factory=dict)  # MountSide -> microsteps at deck z=0

    def vertical_axis(self, side: MountSide) -> AxisId | None:
        """Return the vertical controller axis associated with a mount.

        Args:
            side: Mount whose vertical axis should be identified.

        Returns:
            AxisId | None: ``AxisId.Z`` for the left mount,
            ``AxisId.A`` for the right mount, or ``None`` when the mount has no
            independent vertical axis.
        """
        if side is MountSide.LEFT:
            return AxisId.Z
        if side is MountSide.RIGHT:
            return AxisId.A
        return None

    def _reference_xy(self, point: DeckPoint, side: MountSide) -> tuple:
        """Convert a mount target into the shared gantry reference coordinates.

        The requested ``point`` represents the desired position of the selected
        mount, while the affine transform operates on the gantry's common XY
        reference point. The mount's fixed mechanical offset is therefore
        subtracted in deck space before applying the affine transformation.

        Applying the offset before the affine transform preserves the calibrated
        rotation and scale of the transform and avoids treating the mount offset
        as though it were already expressed in motor coordinates.

        Args:
            point: Desired deck-space position of the selected mount.
            side: Mount that should occupy ``point``.

        Returns:
            tuple: Motor-space ``(x, y)`` coordinates for the shared gantry
            reference point.
        """
        ox, oy = MOUNT_OFFSET_MM.get(side, (0.0, 0.0))
        return self.xy.apply(point.x - ox, point.y - oy)

    def deck_to_motor(
        self,
        point: DeckPoint,
        side: MountSide,
        tip_length_mm: float = 0.0,
    ) -> dict:
        """Convert a deck-space working point into controller motor targets.

        XY coordinates are transformed for the requested physical mount. For a
        vertically actuated mount, the Z target is additionally computed from the
        calibrated mount-specific ``z_zero`` and the configured Z scale.

        ``z_zero`` represents the nozzle reference rather than the end of an
        attached tip. Consequently, ``tip_length_mm`` raises the nozzle reference
        above the requested working point so that the tip end reaches the target.
        This allows the same Z calibration to be used with tools of different
        lengths.

        Args:
            point: Desired working-point position in deck coordinates.
            side: Mount whose working point should reach ``point``.
            tip_length_mm: Length of the attached tip or tool below the nozzle
                reference, in millimeters.

        Returns:
            dict[AxisId, int]: Integer motor targets for the required X/Y axes and,
            when applicable, the selected mount's vertical axis.
        """
        mx, my = self._reference_xy(point, side)
        targets = {AxisId.X: round(mx), AxisId.Y: round(my)}
        vertical = self.vertical_axis(side)
        if vertical is not None:
            zref = self.z_zero.get(side, 0)
            targets[vertical] = int(zref - self.z_scale.to_microsteps(point.z + tip_length_mm))
        return targets

    def z_zero_from_contact(
        self,
        contact_microsteps: int,
        tip_length_mm: float = 0.0,
    ) -> int:
        """Derive the nozzle reference zero from a deck contact position.

        At contact, the end of the tip or probe is at deck ``z = 0``. The nozzle
        reference therefore lies ``tip_length_mm`` above the deck surface. The
        corresponding microstep distance is added to the contact position to
        obtain the tip-independent nozzle reference.

        Args:
            contact_microsteps: Vertical-axis position in microsteps at contact.
            tip_length_mm: Length of the attached tip or probe below the nozzle
                reference, in millimeters.

        Returns:
            int: Nozzle-reference ``z_zero`` position in microsteps.
        """
        return int(contact_microsteps + self.z_scale.to_microsteps(tip_length_mm))

    def motor_to_deck_xy(
        self,
        mx: float,
        my: float,
        side: MountSide | None = None,
    ) -> tuple:
        """Convert raw motor-space XY coordinates back to deck coordinates.

        The inverse affine transform first recovers the shared gantry reference
        position. When ``side`` is provided, that mount's fixed mechanical offset
        is then added so the result represents the physical deck position beneath
        the selected mount.

        Args:
            mx: Motor-space X coordinate.
            my: Motor-space Y coordinate.
            side: Optional mount whose physical deck position should be returned.
                When omitted, the returned coordinates describe the shared gantry
                reference point.

        Returns:
            tuple: Deck-space ``(x, y)`` coordinates corresponding to the supplied
            motor position.
        """
        rx, ry = self.xy.inverse().apply(mx, my)
        if side is None:
            return rx, ry
        ox, oy = MOUNT_OFFSET_MM.get(side, (0.0, 0.0))
        return rx + ox, ry + oy

    def motor_to_deck_z(
        self,
        raw_microsteps: float,
        side: MountSide,
        tip_length_mm: float = 0.0,
    ) -> float | None:
        """Convert a mount's raw vertical motor position to deck height.

        The inverse Z calibration uses the mount-specific ``z_zero`` and
        :attr:`z_scale` to determine the deck height of the working point.
        ``tip_length_mm`` accounts for the distance between the nozzle reference
        and the end of the attached tip or tool.

        Args:
            raw_microsteps: Current vertical-axis position in microsteps.
            side: Mount whose calibrated Z reference should be used.
            tip_length_mm: Length of the attached tip or tool below the nozzle
                reference, in millimeters.

        Returns:
            float | None: Deck-space height in millimeters, or ``None`` when the
            mount has no vertical axis or has not yet received a Z calibration.
        """
        vertical = self.vertical_axis(side)
        if vertical is None or side not in self.z_zero:
            return None
        zref = self.z_zero[side]
        return self.z_scale.to_mm(zref - raw_microsteps) - tip_length_mm

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
        """Automatically calibrate a mount's Z zero by probing a reference surface.

        The mount is first raised to a safe raw microstep position and positioned
        over the supplied deck-space XY location using the existing XY affine
        calibration. It then performs a controller ``G38.2`` probe toward the
        deck until contact is detected.

        The descent is specified entirely in raw microsteps so this procedure does
        not depend on an existing Z calibration. Only the XY calibration is
        required to position the mount over the probe location.

        After contact, the exact vertical-axis position is read from the
        controller and converted into the tip-independent nozzle ``z_zero``.
        Unless ``commit`` is false, the resulting value is stored in
        :attr:`z_zero`. The mount is then retracted to the configured safe
        position.

        Args:
            robot: Robot instance providing the controller, axis configuration,
                and motion state required for probing.
            side: Mount whose vertical axis is being calibrated.
            xy: Deck-space location at which the conductive or reference surface
                should be probed.
            tip_length_mm: Length of the probe or attached tip below the nozzle
                reference, in millimeters.
            feed: Probe feed rate in controller units.
            safe_up_microsteps: Raw vertical-axis position used for the safe
                approach and post-contact retraction.
            max_descent_microsteps: Maximum raw vertical-axis descent target. When
                omitted, the configured endstop limit of the selected vertical
                axis is used.
            commit: Whether to store the calculated ``z_zero`` in this calibration
                object.

        Returns:
            ZContact: Contact position and derived Z-zero calibration result.

        Raises:
            ProbeError: If the probe move completes without detecting contact.
        """
        from ..protocol.commands import ProbeMode
        from ..protocol.errors import ProbeError

        ctrl = robot.controller
        vertical = self.vertical_axis(side)
        max_descent = max_descent_microsteps or robot.axes[vertical].config.endstop_limit
        ctrl.rapid_move({vertical: safe_up_microsteps})
        mx, my = self._reference_xy(xy, side)
        ctrl.rapid_move({AxisId.X: round(mx), AxisId.Y: round(my)})
        result = ctrl.probe(vertical, max_descent, feed=feed, mode=ProbeMode.TOWARD_OR_FAIL)
        if not result.contacted:
            raise ProbeError(f"no surface found probing {side.value} at " f"({xy.x}, {xy.y})")
        contact = ctrl.report_position()[vertical]
        z_zero = self.z_zero_from_contact(contact, tip_length_mm)
        if commit:
            self.z_zero[side] = z_zero
        ctrl.rapid_move({vertical: safe_up_microsteps})
        return ZContact(side, contact, z_zero, tip_length_mm, xy)

    def touch_off_z_zero(
        self,
        robot,
        side: MountSide,
        tip_length_mm: float | None = None,
        commit: bool = True,
    ) -> ZContact:
        """Calibrate a mount's Z zero from its manually established contact position.

        This method is intended for manual touch-off procedures in which an
        operator has already jogged the mount's tip or calibration tool onto a
        reference surface. The current vertical-axis position is read from the
        controller and converted into the nozzle-reference ``z_zero``.

        When ``tip_length_mm`` is omitted, the length reported by the robot for
        the currently attached tool is used. Supplying an explicit length allows
        calibration with an unregistered tool or bare calibration fixture.

        Args:
            robot: Robot instance providing the controller and tool-length
                information.
            side: Mount whose vertical axis is being calibrated.
            tip_length_mm: Optional tip or probe length in millimeters. When
                omitted, the robot's current tip offset for the mount is used.
            commit: Whether to store the calculated ``z_zero`` in this calibration
                object.

        Returns:
            ZContact: Contact position and derived Z-zero calibration result.
        """
        vertical = self.vertical_axis(side)
        length = robot.tip_offset(side) if tip_length_mm is None else tip_length_mm
        contact = robot.controller.report_position()[vertical]
        z_zero = self.z_zero_from_contact(contact, length)
        if commit:
            self.z_zero[side] = z_zero
        return ZContact(side, contact, z_zero, length)

    @classmethod
    def from_points(
        cls,
        deck_pts,
        motor_xy,
        z_scale,
        z_zero=None,
    ) -> DeckCalibration:
        """Construct a deck calibration from corresponding XY calibration points.

        The supplied deck and motor point pairs are used to fit a full affine
        transformation. The resulting transform is combined with the supplied Z
        scale and optional per-mount Z-zero references.

        Args:
            deck_pts: Sequence of deck-space points used for XY calibration.
            motor_xy: Sequence of corresponding motor-space ``(x, y)`` points.
            z_scale: Axis scaling used for Z distance conversion.
            z_zero: Optional mapping of mount sides to calibrated Z-zero
                microstep positions. Defaults to an empty mapping.

        Returns:
            DeckCalibration: Calibration object containing the fitted XY
            transform and supplied Z calibration parameters.
        """
        xy = AffineTransform2D.from_point_pairs([(p.x, p.y) for p in deck_pts], list(motor_xy))
        return cls(xy=xy, z_scale=z_scale, z_zero=z_zero or {})
