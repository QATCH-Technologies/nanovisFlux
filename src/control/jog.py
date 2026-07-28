from __future__ import annotations
import math
from dataclasses import dataclass, field
from ..core import AxisId, MountSide


@dataclass
class JogSettings:
    """Nudge sizes (microsteps) per axis and a set of selectable step scales.
    The active mount decides whether Z/B (left) or A/C (right) get driven.

    ``step_scales`` and ``jog_speed_scales`` share one selectable index
    (cycled by step_up/step_down): the former sizes a discrete nudge(), the
    latter is the feed fraction a held keyboard action drives continuously
    at -- one "how big/fast" dial for both move styles."""
    step_microsteps: dict = field(default_factory=lambda: {
        AxisId.X: 400, AxisId.Y: 400, AxisId.Z: 800, AxisId.A: 800,
        AxisId.B: 200, AxisId.C: 200})
    step_scales: tuple = (0.25, 1.0, 4.0)          # nudge() distance multipliers
    jog_speed_scales: tuple = (0.15, 0.4, 1.0)      # continuous-jog feed fractions
    feed: int = 6000                                # feed for discrete nudge() moves
    jog_feed: int = 10000                           # feed (microsteps/s) at full jog speed


class JogController:
    """Turns abstract jog intents into moves. Stays in G91 for the session so
    each nudge/jog is relative; restores G90 on close.

    Two move styles are supported:

    - ``nudge()``: one short, bounded relative move -- fire and forget.
    - ``begin_jog()`` / ``end_jog()``: a continuous move for held inputs. It
      commands a relative move far past any real travel range at a feed
      scaled to the requested speed, and -- unlike every other move this
      class sends -- does NOT wait for the firmware's 'ok' (see
      Controller.execute's wait_for_ok). A held jog is open-ended by
      nature, and the firmware may not send that 'ok' until the move
      itself completes, not merely once it's queued; waiting for it would
      block the caller (the GUI thread, for keyboard/on-screen/gamepad
      input) for the move's entire duration, so a release/quick-stop
      request could never even be sent until the axis already ran out of
      travel on its own. ``end_jog`` cuts the move short with a quick stop
      (M410, also not waited on) wherever it's gotten to, then resets the
      transport's input buffer (a stray late 'ok' for the move we skipped
      waiting on is likely still sitting there) before re-querying the
      real position. Holding multiple axes combines them into one move;
      any change to the held set re-issues it.

    Requires homed axes (the firmware refuses motion otherwise); M911 relaxes
    limit *clamping* but not the homed gate, so home before jogging.
    """

    def __init__(self, robot, settings: JogSettings | None = None,
                 side: MountSide = MountSide.LEFT):
        self.robot = robot
        self.settings = settings or JogSettings()
        self.side = side
        self._scale_idx = 1
        self._entered = False
        self._active: dict[AxisId, float] = {}   # axis -> signed speed of the in-flight jog

    @property
    def is_jogging(self) -> bool:
        """True while a continuous jog's move is in flight -- its 'ok' is
        deliberately left unread (see class docstring), so anything that
        polls the controller for a response (e.g. a live position timer)
        needs to skip its turn until this goes false again, or it'll read
        that stray leftover reply instead of its own."""
        return bool(self._active)

    # -- session mode --------------------------------------------------
    def __enter__(self):
        self.robot.controller.set_relative()
        self._entered = True
        return self

    def __exit__(self, *exc):
        self.end_jog()
        if self._entered:
            self.robot.controller.set_absolute()
            self._entered = False

    @property
    def scale(self) -> float:
        return self.settings.step_scales[self._scale_idx]

    @property
    def jog_speed(self) -> float:
        return self.settings.jog_speed_scales[self._scale_idx]

    def cycle_scale(self, direction: int = 1) -> float:
        self._scale_idx = (self._scale_idx + direction) % len(self.settings.step_scales)
        return self.scale

    def select_mount(self, side: MountSide) -> None:
        self.side = side

    def toggle_mount(self) -> None:
        self.side = MountSide.RIGHT if self.side is MountSide.LEFT else MountSide.LEFT

    # -- discrete nudge -------------------------------------------------
    def nudge(self, axis: AxisId, sign: int) -> None:
        """Move one bounded step along ``axis`` (+1 away from home, -1 toward
        home). The firmware applies direction inversion internally, so
        positive is always 'away from the endstop' from the caller's point
        of view."""
        if not self._entered:
            self.robot.controller.set_relative()
        step = int(self.settings.step_microsteps[axis] * self.scale)
        self.robot.controller.linear_move({axis: sign * step}, feed=self.settings.feed)

    # -- continuous jog ---------------------------------------------------
    def begin_jog(self, axis: AxisId, sign: int, speed: float = 1.0) -> None:
        """Start (or retune) a continuous move along ``axis``. ``speed`` is a
        0..1 fraction of ``jog_feed`` -- a gamepad passes stick deflection
        directly, a keyboard passes the toggleable ``jog_speed``. Call
        ``end_jog`` to stop it."""
        signed = (1.0 if sign >= 0 else -1.0) * max(0.0, min(1.0, speed))
        if abs(signed) < 1e-3:
            self.end_jog(axis)
            return
        if math.isclose(self._active.get(axis, 0.0), signed, abs_tol=0.02):
            return  # no meaningful change -- avoid restarting the move every poll
        self._active[axis] = signed
        self._restart_continuous()

    def end_jog(self, axis: AxisId | None = None) -> None:
        """Stop one axis's continuous jog, or (with no argument) all of them,
        with an immediate quick stop."""
        if axis is None:
            self._active.clear()
        else:
            self._active.pop(axis, None)
        self._restart_continuous()

    def _restart_continuous(self) -> None:
        """Quick-stop (M410, not waited on) whatever's in flight, then --
        if anything is still held -- issue a fresh move for exactly that
        set. The quick stop isn't optional even when only *narrowing* the
        held set (e.g. releasing X while Y stays held): since multiple
        held axes share one combined G1 line, a new line that only
        mentions Y doesn't touch X's still-in-flight move at all -- G1
        only affects the axes it names, so a dropped axis just keeps
        coasting toward its old target unless something explicitly halts
        it first. When nothing's left held, this is the real "motion
        should stop now" case: also clear whatever stray reply the
        skipped-ack move (see below) left unread, then re-sync the real
        position now that it's actually settled."""
        self.robot.controller.quick_stop()
        if not self._active:
            self.robot.controller.reset_input_buffer()
            self.robot.controller.report_position()
            return
        if not self._entered:
            self.robot.controller.set_relative()
        targets = {axis: int(math.copysign(self.robot.axes[axis].config.endstop_limit, s))
                   for axis, s in self._active.items()}
        feed = int(self.settings.jog_feed * max(abs(s) for s in self._active.values()))
        # Not waited on: a continuous jog is open-ended, and the firmware
        # may not send this G1's 'ok' until the move itself completes, not
        # merely once it's queued -- see class docstring. Waiting would
        # block the caller (the GUI thread, for any input source) for the
        # move's entire duration, so a release could never even be sent
        # until the axis ran out of travel on its own.
        self.robot.controller.linear_move(targets, feed=feed, wait_for_ok=False)

    # -- convenience for the active mount -----------------------------
    def jog_z(self, sign: int) -> None:
        self.nudge(AxisId.Z if self.side is MountSide.LEFT else AxisId.A, sign)

    def jog_plunger(self, sign: int) -> None:
        self.nudge(AxisId.B if self.side is MountSide.LEFT else AxisId.C, sign)

    def begin_jog_z(self, sign: int, speed: float = 1.0) -> None:
        self.begin_jog(AxisId.Z if self.side is MountSide.LEFT else AxisId.A, sign, speed)

    def end_jog_z(self) -> None:
        self.end_jog(AxisId.Z if self.side is MountSide.LEFT else AxisId.A)

    def begin_jog_plunger(self, sign: int, speed: float = 1.0) -> None:
        self.begin_jog(AxisId.B if self.side is MountSide.LEFT else AxisId.C, sign, speed)

    def end_jog_plunger(self) -> None:
        self.end_jog(AxisId.B if self.side is MountSide.LEFT else AxisId.C)

    # -- z calibration -----------------------------------------------
    def capture_z_zero(self, tip_length_mm: float | None = None, commit: bool = True):
        """Record the current vertical position as this mount's z_zero --
        call after manually jogging the tip end down onto a known-flat
        reference surface (e.g. the deck). Delegates to
        ``DeckCalibration.touch_off_z_zero``, which is tip-agnostic:
        ``tip_length_mm`` defaults to whatever tip/tool is on this mount
        right now, so the derived z_zero is the tip-independent nozzle
        reference regardless of which tip touched down."""
        return self.robot.calibration.touch_off_z_zero(self.robot, self.side, tip_length_mm, commit)


#: Logical action names an input backend can emit. Movement actions are
#: continuous: an input backend should call JogSession.press() on
#: press/deflect and .release() on release/return-to-center. Non-movement
#: actions fire once via .press() (or the equivalent .handle()) and need no
#: matching release() call.
ACTIONS = ("x+", "x-", "y+", "y-", "z+", "z-", "plunger+", "plunger-",
           "step_up", "step_down", "mount_toggle", "zero_z", "home", "quit")


class JogSession:
    """Binds action names to JogController calls and dispatches them. Input
    backends translate raw keys/buttons into action names and call press()
    on press/deflect, release() on release/return-to-center."""

    def __init__(self, controller: JogController):
        self.c = controller
        self.running = True
        self._begin = {
            "x+": lambda speed: self.c.begin_jog(AxisId.X, +1, speed),
            "x-": lambda speed: self.c.begin_jog(AxisId.X, -1, speed),
            "y+": lambda speed: self.c.begin_jog(AxisId.Y, +1, speed),
            "y-": lambda speed: self.c.begin_jog(AxisId.Y, -1, speed),
            "z+": lambda speed: self.c.begin_jog_z(+1, speed),
            "z-": lambda speed: self.c.begin_jog_z(-1, speed),
            "plunger+": lambda speed: self.c.begin_jog_plunger(+1, speed),
            "plunger-": lambda speed: self.c.begin_jog_plunger(-1, speed),
        }
        self._end = {
            "x+": lambda: self.c.end_jog(AxisId.X),
            "x-": lambda: self.c.end_jog(AxisId.X),
            "y+": lambda: self.c.end_jog(AxisId.Y),
            "y-": lambda: self.c.end_jog(AxisId.Y),
            "z+": lambda: self.c.end_jog_z(),
            "z-": lambda: self.c.end_jog_z(),
            "plunger+": lambda: self.c.end_jog_plunger(),
            "plunger-": lambda: self.c.end_jog_plunger(),
        }
        self._bindings = {
            # discrete one-shot equivalents -- used by handle() (scripted
            # input, tests, single-button taps); press()/release() bypass
            # these in favor of the continuous jog above.
            "x+": lambda: self.c.nudge(AxisId.X, +1),
            "x-": lambda: self.c.nudge(AxisId.X, -1),
            "y+": lambda: self.c.nudge(AxisId.Y, +1),
            "y-": lambda: self.c.nudge(AxisId.Y, -1),
            "z+": lambda: self.c.jog_z(+1),
            "z-": lambda: self.c.jog_z(-1),
            "plunger+": lambda: self.c.jog_plunger(+1),
            "plunger-": lambda: self.c.jog_plunger(-1),
            "step_up": lambda: self.c.cycle_scale(+1),
            "step_down": lambda: self.c.cycle_scale(-1),
            "mount_toggle": lambda: self.c.toggle_mount(),
            "zero_z": lambda: self.c.capture_z_zero(),
            "home": lambda: self.c.robot.home(),
            "quit": self._quit,
        }

    def _quit(self):
        self.c.end_jog()
        self.running = False

    def press(self, action: str, speed: float | None = None) -> None:
        """Begin ``action``. Movement actions move continuously until
        release() stops them; momentary actions (step_up, home, ...) just
        fire once, same as handle()."""
        fn = self._begin.get(action)
        if fn:
            fn(self.c.jog_speed if speed is None else speed)
        else:
            self.handle(action)

    def release(self, action: str) -> None:
        """End a continuous move started by press(). No-op for momentary
        actions -- there's nothing held to release."""
        fn = self._end.get(action)
        if fn:
            fn()

    def handle(self, action: str) -> None:
        """Fire a momentary action once -- for one-shot inputs (buttons,
        scripted tests) rather than a held key/stick."""
        fn = self._bindings.get(action)
        if fn:
            fn()

    def bind(self, action: str, fn) -> None:
        self._bindings[action] = fn
