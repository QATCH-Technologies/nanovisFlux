"""Interactive jogging control for robot axes and mounted tools.

This module provides the configuration, motion-control, and action-dispatch
layers used by interactive robot jogging.

The :class:`JogController` translates high-level relative jog requests into
firmware motion commands while applying per-axis speed limits and resonance
avoidance. It supports both bounded single-step nudges and open-ended
continuous jogging for held inputs.

The :class:`JogSession` maps device-independent action names to controller
operations. Input backends such as keyboard, gamepad, or scripted input can
therefore share the same jogging behavior without depending on a particular
input device.

The active :class:`~core.MountSide` determines which vertical and plunger
axes are controlled by the logical Z and plunger actions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..core import AxisId, MountSide
from ..motion.resonance import avoid_resonant_feed


@dataclass
class JogSettings:
    """Configuration for discrete and continuous jogging behavior.

    Jogging uses a shared scale index to select both the distance of discrete
    nudges and the speed fraction used for continuous motion. The active mount
    determines whether the logical Z and plunger controls address the left
    mount's Z/B axes or the right mount's A/C axes.

    Continuous jog speed is calculated relative to each axis's configured
    ``travel_speed`` rather than using one global microsteps-per-second
    value. This accounts for the substantially different microstep densities
    of the horizontal and vertical axes. The resulting per-axis speed is then
    multiplied by ``jog_speed_fraction`` and, where applicable, the selected
    continuous-jog scale and input-device speed.

    Attributes:
        step_microsteps: Base relative movement distance in firmware
            microsteps for each axis. The active ``step_scales`` value is
            applied to these distances for discrete nudges.
        step_scales: Multipliers available for discrete nudge distances.
            The active value is selected by the shared scale index.
        jog_speed_scales: Feed fractions available for continuous jogging.
            These share the same selection index as ``step_scales``.
        jog_speed_fraction: Global multiplier applied to each axis's
            configured ``travel_speed`` to establish its jog-speed ceiling.
            A value of ``1.0`` permits jogging up to the configured travel
            speed before input-specific speed scaling is applied.
    """

    step_microsteps: dict = field(
        default_factory=lambda: {
            AxisId.X: 400,
            AxisId.Y: 400,
            AxisId.Z: 800,
            AxisId.A: 800,
            AxisId.B: 200,
            AxisId.C: 200,
        }
    )
    step_scales: tuple = (0.25, 1.0, 4.0)
    jog_speed_scales: tuple = (0.15, 0.4, 1.0)
    jog_speed_fraction: float = 1.0


class JogController:
    """Translate logical jog requests into robot motion commands.

    The controller operates in relative-coordinate mode while a jog session
    is active and restores absolute-coordinate mode when the session closes.
    It supports two types of motion:

    * ``nudge()`` performs a bounded relative move and waits for the normal
      firmware acknowledgement.
    * ``begin_jog()`` / ``end_jog()`` implement continuous motion for held
      inputs. Continuous moves are deliberately sent without waiting for the
      firmware's ``ok`` response because an open-ended move may not produce
      that response until the commanded move completes. Waiting would prevent
      the input source from sending a release or quick-stop command.

    Continuous motion is stopped using the firmware quick-stop command before
    any changed set of held axes is re-issued. This is necessary because a
    G-code move only affects the axes explicitly named by that command; an
    axis removed from a combined jog would otherwise continue executing its
    previous move.

    Feed rates are derived from each axis's configured ``travel_speed`` and
    adjusted to avoid configured resonance bands. When multiple axes are
    moving together, the slowest participating axis establishes the common
    feed ceiling because one firmware G1 command applies the same feed to all
    named axes.

    Args:
        robot: Robot instance whose controller, axis configuration, and
            calibration are used to execute jog operations.
        settings: Optional jogging configuration. Defaults to
            :class:`JogSettings`.
        side: Initial active mount side. Defaults to
            :attr:`MountSide.LEFT`.

    Notes:
        Axes must be homed before jogging. Firmware limit-clamping relaxation
        does not bypass the firmware's requirement that axes be homed before
        motion is permitted.
    """

    def __init__(
        self, robot, settings: JogSettings | None = None, side: MountSide = MountSide.LEFT
    ):
        """Initialize a jog controller.

        Args:
            robot: Robot instance to control.
            settings: Optional jogging configuration.
            side: Mount side initially selected for logical Z and plunger
                operations.
        """
        self.robot = robot
        self.settings = settings or JogSettings()
        self.side = side
        self._scale_idx = 1
        self._entered = False
        self._active: dict[AxisId, float] = {}

    @property
    def is_jogging(self) -> bool:
        """Return whether a continuous jog is currently active.

        Returns:
            True if at least one axis has an in-flight continuous jog command;
            otherwise False.

        Notes:
            Continuous jog commands intentionally do not wait for their firmware
            acknowledgement. Callers that poll controller responses, such as
            live-position display code, should avoid consuming responses while
            this property is True.
        """
        return bool(self._active)

    def __enter__(self):
        """Enter relative-coordinate jog mode.

        The robot controller is switched to relative coordinates so that all
        subsequent nudge and continuous-jog commands are interpreted as
        incremental movements.

        Returns:
            This controller instance.
        """
        self.robot.controller.set_relative()
        self._entered = True
        return self

    def __exit__(self, *exc):
        """Stop active jogging and restore absolute-coordinate mode.

        Any active continuous jog is stopped before the controller is returned to
        absolute-coordinate mode.

        Args:
            *exc: Exception information supplied by the context-manager protocol.

        Returns:
            None. Exceptions are not suppressed.
        """
        self.end_jog()
        if self._entered:
            self.robot.controller.set_absolute()
            self._entered = False

    @property
    def scale(self) -> float:
        """Return the currently selected discrete-nudge scale.

        Returns:
            Multiplicative factor applied to the configured per-axis
            ``step_microsteps`` values.
        """
        return self.settings.step_scales[self._scale_idx]

    @property
    def jog_speed(self) -> float:
        """Return the currently selected continuous-jog speed fraction.

        Returns:
            Speed fraction selected from ``JogSettings.jog_speed_scales``.
        """
        return self.settings.jog_speed_scales[self._scale_idx]

    def cycle_scale(self, direction: int = 1) -> float:
        """Cycle the shared nudge and continuous-jog scale.

        Args:
            direction: Direction in which to move through the scale list.
                Positive values advance toward larger indices; negative values
                move toward smaller indices.

        Returns:
            The newly selected discrete-nudge scale.
        """
        self._scale_idx = (self._scale_idx + direction) % len(self.settings.step_scales)
        return self.scale

    def select_mount(self, side: MountSide) -> None:
        """Select the active mount for mount-dependent jog operations.

        Args:
            side: Mount side to make active. Logical Z and plunger operations
                subsequently address that mount's vertical and plunger axes.
        """
        self.side = side

    def toggle_mount(self) -> None:
        """Switch the active mount between the left and right sides."""
        self.side = MountSide.RIGHT if self.side is MountSide.LEFT else MountSide.LEFT

    def _axis_feed(self, axis: AxisId) -> float:
        """Calculate the jog feed ceiling for an axis.

        The ceiling is derived from the axis's configured ``travel_speed`` and
        multiplied by ``JogSettings.jog_speed_fraction``.

        Args:
            axis: Axis whose configured travel speed should be used.

        Returns:
            Maximum jog feed for the axis, in firmware microsteps per second.
        """
        return self.robot.axes[axis].config.travel_speed * self.settings.jog_speed_fraction

    def _resonance_safe_feed(self, feed: float, axes, *, ceiling: float | None = None) -> float:
        """Adjust a feed rate to avoid resonance bands for selected axes.

        The resonance bands of all participating axes are combined because a
        single firmware G1 command applies one feed value to every axis named by
        that command.

        Args:
            feed: Requested feed rate in firmware microsteps per second.
            axes: Iterable of axes participating in the motion.
            ceiling: Optional maximum feed rate that the adjusted value must not
                exceed.

        Returns:
            A feed rate adjusted away from configured resonance bands while
            respecting the requested ceiling.
        """
        bands = tuple(b for axis in axes for b in self.robot.axes[axis].config.resonance_bands_hz)
        if not bands:
            return feed
        return avoid_resonant_feed(feed, bands, ceiling=ceiling, floor=1.0)

    def nudge(self, axis: AxisId, sign: int) -> None:
        """Perform one bounded relative movement.

        Args:
            axis: Axis to move.
            sign: Direction of movement. ``+1`` represents movement away from
                home and ``-1`` represents movement toward home from the caller's
                perspective. Firmware-level direction inversion is handled by the
                axis configuration.

        Raises:
            KeyError: If no step size is configured for ``axis``.
            RuntimeError: If the underlying controller rejects the motion.
        """
        if not self._entered:
            self.robot.controller.set_relative()
        step = int(self.settings.step_microsteps[axis] * self.scale)
        ceiling = self._axis_feed(axis)
        feed = self._resonance_safe_feed(ceiling, (axis,), ceiling=ceiling)
        self.robot.controller.linear_move({axis: sign * step}, feed=int(feed))

    def begin_jog(self, axis: AxisId, sign: int, speed: float = 1.0) -> None:
        """Start or retune continuous motion along an axis.

        A continuous move is commanded sufficiently far that the jog remains
        active until explicitly stopped. The requested speed is interpreted as a
        fraction of the axis's configured jog ceiling.

        Args:
            axis: Axis to move continuously.
            sign: Direction of movement. Positive values move away from home;
                negative values move toward home.
            speed: Requested speed fraction in the range ``0.0`` to ``1.0``.
                Values outside the range are clamped.

        Notes:
            Calling this method with a speed effectively equal to the currently
            active speed does not restart the move. This prevents high-frequency
            input polling from repeatedly reissuing identical motion commands.
        """
        signed = (1.0 if sign >= 0 else -1.0) * max(0.0, min(1.0, speed))
        if abs(signed) < 1e-3:
            self.end_jog(axis)
            return
        if math.isclose(self._active.get(axis, 0.0), signed, abs_tol=0.02):
            return  # no meaningful change
        self._active[axis] = signed
        self._restart_continuous()

    def end_jog(self, axis: AxisId | None = None) -> None:
        """Stop continuous jogging.

        Args:
            axis: Specific axis to stop. If omitted, all active continuous jogs
                are stopped.

        Notes:
            The firmware quick-stop mechanism is used so that motion stops
            immediately rather than waiting for an open-ended movement command to
            complete.
        """
        if axis is None:
            self._active.clear()
        else:
            self._active.pop(axis, None)
        self._restart_continuous()

    def _restart_continuous(self) -> None:
        """Stop the current continuous move and issue the current jog state.

        The existing firmware move is first cancelled with a quick stop. If axes
        remain active, a new combined relative move is issued for exactly those
        axes using a common feed rate that does not exceed the slowest
        participating axis's configured ceiling.

        If no axes remain active, the controller input buffer is cleared and the
        current physical position is queried to resynchronize software state
        after the intentionally unread acknowledgement from the previous
        continuous move.
        """
        self.robot.controller.quick_stop()
        if not self._active:
            self.robot.controller.reset_input_buffer()
            self.robot.controller.report_position()
            return
        if not self._entered:
            self.robot.controller.set_relative()
        targets = {
            axis: int(math.copysign(self.robot.axes[axis].config.endstop_limit, s))
            for axis, s in self._active.items()
        }
        ceiling = min(self._axis_feed(axis) for axis in self._active)
        speed_fraction = max(abs(s) for s in self._active.values())
        feed = self._resonance_safe_feed(
            ceiling * speed_fraction, tuple(self._active), ceiling=ceiling
        )
        feed = int(feed)
        self.robot.controller.linear_move(targets, feed=feed, wait_for_ok=False)

    def jog_z(self, sign: int) -> None:
        """Perform one bounded Z-axis nudge on the active mount.

        Args:
            sign: Direction of movement relative to the active mount.
        """
        self.nudge(AxisId.Z if self.side is MountSide.LEFT else AxisId.A, sign)

    def jog_plunger(self, sign: int) -> None:
        """Perform one bounded plunger-axis nudge on the active mount.

        Args:
            sign: Direction of plunger movement.
        """
        self.nudge(AxisId.B if self.side is MountSide.LEFT else AxisId.C, sign)

    def begin_jog_z(self, sign: int, speed: float = 1.0) -> None:
        """Start continuous Z-axis jogging on the active mount.

        Args:
            sign: Direction of movement.
            speed: Speed fraction between zero and one.
        """
        self.begin_jog(AxisId.Z if self.side is MountSide.LEFT else AxisId.A, sign, speed)

    def end_jog_z(self) -> None:
        """Stop continuous Z-axis jogging on the active mount."""
        self.end_jog(AxisId.Z if self.side is MountSide.LEFT else AxisId.A)

    def begin_jog_plunger(self, sign: int, speed: float = 1.0) -> None:
        """Start continuous plunger jogging on the active mount.

        Args:
            sign: Direction of plunger movement.
            speed: Speed fraction between zero and one.
        """
        self.begin_jog(AxisId.B if self.side is MountSide.LEFT else AxisId.C, sign, speed)

    def end_jog_plunger(self) -> None:
        """Stop continuous plunger jogging on the active mount."""
        self.end_jog(AxisId.B if self.side is MountSide.LEFT else AxisId.C)

    def capture_z_zero(self, tip_length_mm: float | None = None, commit: bool = True):
        """Capture the current position as the active mount's Z reference.

        This method is intended to be called after manually jogging a tool or tip
        onto a known-flat reference surface. The calibration layer converts the
        touched position into a tip-independent nozzle reference.

        Args:
            tip_length_mm: Optional length of the currently installed tip or tool.
                If omitted, the calibration layer determines the appropriate
                current tool length.
            commit: Whether the newly calculated Z-zero should be persisted to
                the active calibration.

        Returns:
            The result returned by
            :meth:`DeckCalibration.touch_off_z_zero`.
        """
        return self.robot.calibration.touch_off_z_zero(self.robot, self.side, tip_length_mm, commit)
