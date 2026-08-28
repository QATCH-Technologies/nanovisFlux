"""
High-level robot control facade for deck-space motion and instrument hardware.

This module provides the :class:`Robot` facade that coordinates the major
components required to operate the instrument, including the transport layer,
motion controller, deck calibration, motion axes, physical mounts, deck
geometry, labware, and tip geometry.

The :class:`Robot` class exposes user-facing operations for connecting to and
disconnecting from the controller, attaching tools, loading labware, homing
axes, and commanding deck-space motion. Motion commands are converted from
deck coordinates to calibrated motor coordinates and are tip-aware when a
mounted tool provides a `tip_offset_mm()` method.

Two classes of motion are provided:

* Direct motion via :meth:`Robot.move_to`, which moves horizontally at the
  current vertical position before moving to the requested height.
* Clearance-aware motion via :meth:`Robot.safe_move_to`, which raises the
  active mount before crossing the deck, moves horizontally, and then lowers
  to the destination.

Clearance-aware motion accounts for known labware and deck obstacles along
the horizontal path. Motion completion can optionally be verified using
controller-reported positions, including detection and retry of stalled
motion.

Attributes:
    _PATH_CLEARANCE_MARGIN_MM: Additional vertical clearance maintained above
        the tallest known labware or obstacle encountered during a safe
        horizontal crossing.
"""

from __future__ import annotations

import time

from .core import AxisId, MountSide
from .geometry.calibration import DeckCalibration
from .geometry.coordinates import DeckPoint
from .motion.axis import Axis, default_axis_configs
from .motion.mounts import Mount
from .protocol.driver import Controller
from .transport.base import Transport

# Headroom kept above the tallest labware/obstacle top a safe_move_to
_PATH_CLEARANCE_MARGIN_MM = 5.0


class Robot:
    """Provide the high-level interface for operating the instrument.

    `Robot` is the primary facade intended for application-level code. It
    combines the controller, transport, calibration, deck, motion axes,
    physical mounts, labware, and tip geometry into a single object through
    which instrument operations can be performed.

    Deck-space motion is converted to motor coordinates using
    :class:`DeckCalibration`. When a mounted tool provides a
    `tip_offset_mm()` method, the offset is incorporated into the coordinate
    conversion so that requested Z positions describe the tool tip rather
    than the bare nozzle.

    Attributes:
        controller: Motion controller responsible for communicating with the
            firmware.
        calibration: Deck calibration used for coordinate transformations.
        deck: Configured deck containing slots and deck geometry.
        travel_z_mm: Default safe travel height in deck-space millimeters.
        axes: Mapping from :class:`AxisId` values to configured motion axes.
        mounts: Mapping from :class:`MountSide` values to physical mounts.
        labware: Mapping of registration keys to loaded labware instances.
        tips: Mapping of labware names to known tip geometry definitions.
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
        """Initialize a robot and its motion-control components.

        Args:
            transport: Transport implementation used by the controller for
                communication with the instrument.
            calibration: Optional calibration describing the transformation
                between deck-space and motor-space coordinates.
            deck: Optional deck definition containing slots and deck geometry.
            travel_z_mm: Default deck-space height used for clearance-aware travel.
            timeout: Controller communication timeout in seconds.
        """
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
        self.labware: dict = {}
        self.tips: dict = {}

    def connect(self) -> Robot:
        """Open the controller connection and return this robot.

        Returns:
            The connected :class:`Robot` instance.
        """
        self.controller.open()
        return self

    def disconnect(self) -> None:
        """Close the controller connection."""
        self.controller.close()

    def __enter__(self) -> Robot:  # noqa
        """Connect the robot when entering a context manager.

        Returns:
            The connected :class:`Robot` instance.
        """
        return self.connect()

    def __exit__(self, *exc) -> None:
        """Disconnect the robot when leaving a context manager.

        Args:
            *exc: Exception information supplied by the context-manager protocol.
        """
        self.disconnect()

    def attach(self, side: MountSide, tool) -> None:
        """Attach a tool to a specified mount.

        The mount is updated before the tool's `on_attach` callback is invoked.

        Args:
            side: Mount position to which the tool should be attached.
            tool: Tool instance to attach to the mount.
        """
        mount = self.mounts[side]
        mount.attach(tool)
        tool.on_attach(mount, self)

    def left(self):
        """Return the tool attached to the left mount.

        Returns:
            The tool attached to :attr:`MountSide.LEFT`, or `None` if no tool
            is attached.
        """
        return self.mounts[MountSide.LEFT].tool

    def right(self):
        """Return the tool attached to the right mount.

        Returns:
            The tool attached to :attr:`MountSide.RIGHT`, or `None` if no tool
            is attached.
        """
        return self.mounts[MountSide.RIGHT].tool

    def rear(self):
        """Return the tool attached to the rear mount.

        Returns:
            The tool attached to :attr:`MountSide.REAR`, or `None` if no tool
            is attached.
        """
        return self.mounts[MountSide.REAR].tool

    def load_labware(self, labware, slot_name: str, *, key: str | None = None):
        """Place and register an instantiated labware object.

        An explicit `key` allows multiple placements of the same reusable
        labware definition to coexist without overwriting one another in the
        labware registry.

        Args:
            labware: Labware instance to place on the deck.
            slot_name: Name of the deck slot on which the labware is placed.
            key: Optional registry key. Defaults to `labware.name`.

        Returns:
            The placed labware instance.

        Raises:
            RuntimeError: If no deck is configured.
            KeyError: If `slot_name` is not a valid deck slot.
        """
        if self.deck is None:
            raise RuntimeError("no deck configured")
        labware.place(self.deck[slot_name])
        self.labware[key or labware.name] = labware
        return labware

    def load(self, definition, slot_name: str, *, stacked: bool = False):
        """Instantiate, place, and register labware from a definition.

        Labware geometry is derived from the supplied definition rather than
        manually specifying well or tip offsets. Definitions that provide a
        callable `tip_geometry` are also registered in the robot's tip geometry
        registry.

        Args:
            definition: Labware definition used to construct the labware.
            slot_name: Name of the deck slot on which the labware is placed.
            stacked: Whether the labware should use stacked placement geometry.

        Returns:
            The instantiated and placed labware object.

        Raises:
            RuntimeError: If no deck is configured.
            KeyError: If `slot_name` is not a valid deck slot.
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
        """Return the vertical tip offset for a mounted tool.

        Args:
            side: Mount whose attached tool should be queried.

        Returns:
            Tip offset in millimeters, or `0.0` when the attached tool does not
            provide a `tip_offset_mm()` method.
        """
        tool = self.mounts[side].tool
        getter = getattr(tool, "tip_offset_mm", None)
        return float(getter()) if callable(getter) else 0.0  # type: ignore

    def _require_cal(self) -> DeckCalibration:
        """Return the configured deck calibration.

        Returns:
            The active :class:`DeckCalibration`.

        Raises:
            RuntimeError: If no deck calibration is configured.
        """
        if self.calibration is None:
            raise RuntimeError("deck is not calibrated; set robot.calibration first")
        return self.calibration

    def home(self, *axes: AxisId) -> None:
        """Home the specified motion axes.

        Absolute positioning mode is enabled before the homing command is sent.
        Requested axes are marked as homed after the command is issued.

        Args:
            *axes: Axes to home. If omitted, all known axes are marked as homed.
        """
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
        stall_timeout: float = 1.0,
        resend=None,
        max_resends: int = 2,
    ) -> None:
        """Wait until controller-reported positions reach commanded targets.

        Motion completion is verified independently of the controller's command
        completion response by repeatedly querying its reported position.

        Negative reported positions are treated as settled because they indicate
        that the controller cannot provide a trustworthy comparable position.
        Stalled motion can optionally be retried by invoking `resend` before
        ultimately raising an error.

        Args:
            targets: Mapping of axis identifiers to target motor positions.
            tolerance: Maximum permitted position error in microsteps.
            timeout: Maximum total wait time in seconds.
            poll_interval: Delay between position queries in seconds.
            stall_timeout: Time that positions may remain unchanged before the
                move is considered stalled.
            resend: Optional zero-argument callable used to reissue the move after
                a stall.
            max_resends: Maximum number of stalled-move retries.

        Raises:
            TimeoutError: If the targets are not reached within `timeout` or
                motion remains stalled after all retries.
        """
        deadline = time.monotonic() + timeout
        last_pos: dict | None = None
        stalled_since: float | None = None
        resends_left = max_resends
        while True:
            pos = self.controller.report_position()
            if all(
                pos.get(axis) is not None
                and (pos[axis] < 0 or abs(pos[axis] - target) <= tolerance)
                for axis, target in targets.items()
            ):
                return
            now = time.monotonic()
            current = {axis: pos.get(axis) for axis in targets}
            if current == last_pos:
                stalled_since = stalled_since or now
                if now - stalled_since >= stall_timeout:
                    if resend is not None and resends_left > 0:
                        resends_left -= 1
                        resend()
                        stalled_since = None
                        last_pos = None
                        continue
                    tried = max_resends - resends_left
                    retry_note = (
                        f" after {tried} retr{'y' if tried == 1 else 'ies'}" if tried else ""
                    )
                    raise TimeoutError(
                        f"axes stopped moving without reaching target{retry_note}:"
                        f" wanted {targets}, stalled at {current}"
                    )
            else:
                stalled_since = None
            last_pos = current
            if now >= deadline:
                raise TimeoutError(
                    f"axes did not settle within {timeout}s: wanted {targets}, last read {current}"
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
        """Move a mounted tool to a deck-space point without a clearance arc.

        X/Y motion is performed before the vertical move. The target is converted
        to motor coordinates using deck calibration and the selected tool's tip
        offset.

        This method does not raise the tool to a clearance height before
        horizontal travel. Use :meth:`safe_move_to` when the path must clear
        labware or other deck obstacles.

        Args:
            point: Target deck-space position.
            side: Mount whose tool should be moved.
            feed: Optional feed rate. Rapid motion is used when omitted.
            verify: Whether to verify each motion leg using reported positions.

        Raises:
            RuntimeError: If deck calibration is not configured.
            TimeoutError: If verification is enabled and motion fails to settle.
        """
        cal = self._require_cal()
        xy = cal.deck_to_motor(point, side, self.tip_offset(side))
        xy_targets = {AxisId.X: xy[AxisId.X], AxisId.Y: xy[AxisId.Y]}

        def _send():
            if feed is not None:
                self.controller.linear_move(xy_targets, feed=feed)
            else:
                self.controller.rapid_move(xy_targets)

        _send()
        if verify:
            self._await_settled(xy_targets, resend=_send)
        self.move_vertical_to(point.z, side, feed=feed, verify=verify)

    def move_vertical_to(
        self,
        deck_z_mm: float,
        side: MountSide,
        feed: int | None = None,
        *,
        verify: bool = True,
    ) -> None:
        """Move only a mount's vertical axis to a deck-space height.

        The target is converted to motor coordinates using deck calibration and
        the mounted tool's tip offset. Horizontal position is unchanged.

        Args:
            deck_z_mm: Target vertical position in deck-space millimeters.
            side: Mount whose vertical axis should be moved.
            feed: Optional feed rate. Rapid motion is used when omitted.
            verify: Whether to verify that the axis reaches its target.

        Raises:
            RuntimeError: If deck calibration is not configured.
            TimeoutError: If verification is enabled and the axis fails to settle.
        """
        cal = self._require_cal()
        axis = cal.vertical_axis(side)
        mz = cal.deck_to_motor(DeckPoint(0, 0, deck_z_mm), side, self.tip_offset(side))[axis]

        def _send():
            if axis is None:
                return

            if feed is not None:
                self.controller.linear_move({axis: mz}, feed=feed)
            else:
                self.controller.rapid_move({axis: mz})

        _send()
        if verify:
            self._await_settled({axis: mz}, resend=_send)

    def move_horizontal_to(
        self,
        x_mm: float,
        y_mm: float,
        side: MountSide,
        feed: int | None = None,
        *,
        verify: bool = True,
    ) -> None:
        """Move only the horizontal X/Y axes to a deck-space position.

        The vertical axis associated with the selected mount is left unchanged.
        No clearance-height movement is performed.

        Args:
            x_mm: Target deck X coordinate in millimeters.
            y_mm: Target deck Y coordinate in millimeters.
            side: Mount whose horizontal position is being commanded.
            feed: Optional feed rate. Rapid motion is used when omitted.
            verify: Whether to verify that the horizontal axes reach their targets.

        Raises:
            RuntimeError: If deck calibration is not configured.
            TimeoutError: If verification is enabled and the axes fail to settle.
        """
        cal = self._require_cal()
        xy = cal.deck_to_motor(DeckPoint(x_mm, y_mm, 0.0), side, self.tip_offset(side))
        xy_targets = {AxisId.X: xy[AxisId.X], AxisId.Y: xy[AxisId.Y]}

        def _send():
            if feed is not None:
                self.controller.linear_move(xy_targets, feed=feed)
            else:
                self.controller.rapid_move(xy_targets)

        _send()
        if verify:
            self._await_settled(xy_targets, resend=_send)

    def raise_z(
        self, side: MountSide, clearance_mm: float | None = None, *, verify: bool = True
    ) -> None:
        """Raise a mount to at least the requested clearance height.

        If the current vertical position can be determined and is already at or
        above the requested clearance, no motion is issued. If the current
        position cannot be determined, the requested clearance is commanded
        unconditionally.

        Args:
            side: Mount whose vertical axis should be raised.
            clearance_mm: Minimum clearance height in deck-space millimeters.
                Defaults to :attr:`travel_z_mm`.
            verify: Whether to verify that the resulting motion reaches its target.

        Raises:
            RuntimeError: If deck calibration is not configured.
            TimeoutError: If verification is enabled and the move fails to settle.
        """
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
        """Determine the current deck-space X/Y position of a mount.

        The controller's motor-space position is converted back to deck-space
        coordinates using the active calibration.

        Args:
            side: Mount whose current position should be determined.

        Returns:
            A `(x, y)` tuple in deck-space millimeters, or `None` if the
            current position cannot be determined reliably.
        """
        if self.calibration is None:
            return None
        pos = self.controller.report_position()
        mx, my = pos.get(AxisId.X), pos.get(AxisId.Y)
        if mx is None or my is None or mx < 0 or my < 0:
            return None
        return self.calibration.motor_to_deck_xy(mx, my, side)

    def _slots_crossed(self, start_xy: tuple, end_xy: tuple) -> list:
        """Find deck slots intersecting the path bounding box.

        The calculation conservatively includes every dimensioned slot whose
        footprint overlaps the axis-aligned bounding box between the start and
        destination positions.

        Args:
            start_xy: Starting deck-space `(x, y)` position.
            end_xy: Destination deck-space `(x, y)` position.

        Returns:
            A list of deck slots whose footprints overlap the path bounding box.
            Returns an empty list when no deck is configured.
        """
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
        """Determine the tallest known surface occupying a deck slot.

        Labware, slot obstacles, and slot walls are considered when determining
        the maximum occupied height.

        Args:
            slot: Deck slot whose occupied height should be evaluated.

        Returns:
            The greatest known occupied height above the deck plane in
            deck-space millimeters.
        """
        tallest = max((o.height_mm for o in slot.obstacles), default=0.0)
        tallest = max(tallest, slot.wall_height_mm)
        for lw in self.labware.values():
            if lw.slot is slot and lw.wells:
                tallest = max(tallest, max(w.offset.z for w in lw.wells.values()))
        return tallest

    def _path_clearance_mm(self, side: MountSide, target_xy: tuple, requested_mm: float) -> float:
        """Calculate the clearance required for a horizontal crossing.

        The requested clearance is increased when necessary to clear the tallest
        known labware or obstacle in any slot intersected by the path.

        Args:
            side: Mount whose current position defines the path origin.
            target_xy: Destination deck-space `(x, y)` position.
            requested_mm: Minimum clearance requested by the caller.

        Returns:
            A clearance height in deck-space millimeters. The result is never
            lower than `requested_mm`.
        """
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
        """Move a mounted tool to a deck-space point using a clearance arc.

        Motion is performed in three stages:

        1. Raise the selected mount to the required clearance height.
        2. Move horizontally to the destination X/Y position.
        3. Lower the mount to the requested Z height.

        The clearance is based on `clearance_mm` or :attr:`travel_z_mm` and is
        automatically increased when known labware or deck obstacles along the
        path require additional height.

        Args:
            point: Target deck-space position.
            side: Mount whose tool should be moved.
            clearance_mm: Requested minimum travel height. Defaults to
                :attr:`travel_z_mm`.
            feed: Optional feed rate for the final vertical move.
            verify: Whether to verify each motion leg using reported positions.

        Raises:
            RuntimeError: If deck calibration is not configured.
            TimeoutError: If verification is enabled and a motion leg fails to
                settle.
        """
        cal = self._require_cal()
        base_clr = clearance_mm if clearance_mm is not None else self.travel_z_mm
        clr = self._path_clearance_mm(side, (point.x, point.y), base_clr)
        self.raise_z(side, clr, verify=verify)
        xy = cal.deck_to_motor(DeckPoint(point.x, point.y, clr), side, self.tip_offset(side))
        xy_targets = {AxisId.X: xy[AxisId.X], AxisId.Y: xy[AxisId.Y]}

        def _send():
            self.controller.rapid_move(xy_targets)

        _send()
        if verify:
            self._await_settled(xy_targets, resend=_send)
        self.move_vertical_to(point.z, side, feed=feed, verify=verify)

    def emergency_stop(self) -> None:
        """Immediately stop controller motion and invalidate homing state.

        After an emergency stop, all tracked axes are marked as not homed because
        the controller's assumed coordinates may no longer correspond reliably
        to the physical position of the instrument.
        """
        self.controller.emergency_stop()
        for ax in self.axes.values():
            ax.homed = False
