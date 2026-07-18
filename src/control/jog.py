from __future__ import annotations
from dataclasses import dataclass, field
from ..core import AxisId, MountSide


@dataclass
class JogSettings:
    """Nudge sizes (microsteps) per axis and a set of selectable step scales.
    The active mount decides whether Z/B (left) or A/C (right) get driven."""
    step_microsteps: dict = field(default_factory=lambda: {
        AxisId.X: 400, AxisId.Y: 400, AxisId.Z: 800, AxisId.A: 800,
        AxisId.B: 200, AxisId.C: 200})
    step_scales: tuple = (0.25, 1.0, 4.0)   # coarse/fine multipliers to cycle
    feed: int = 6000


class JogController:
    """Turns abstract jog intents into relative moves. Stays in G91 for the
    session so each nudge is one short relative move; restores G90 on close.

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

    # -- session mode --------------------------------------------------
    def __enter__(self):
        self.robot.controller.set_relative()
        self._entered = True
        return self

    def __exit__(self, *exc):
        if self._entered:
            self.robot.controller.set_absolute()
            self._entered = False

    @property
    def scale(self) -> float:
        return self.settings.step_scales[self._scale_idx]

    def cycle_scale(self, direction: int = 1) -> float:
        self._scale_idx = (self._scale_idx + direction) % len(self.settings.step_scales)
        return self.scale

    def select_mount(self, side: MountSide) -> None:
        self.side = side

    def toggle_mount(self) -> None:
        self.side = MountSide.RIGHT if self.side is MountSide.LEFT else MountSide.LEFT

    # -- the actual nudge ---------------------------------------------
    def nudge(self, axis: AxisId, sign: int) -> None:
        """Move one step along ``axis`` (+1 away from home, -1 toward home).
        The firmware applies direction inversion internally, so positive is
        always 'away from the endstop' from the caller's point of view."""
        if not self._entered:
            self.robot.controller.set_relative()
        step = int(self.settings.step_microsteps[axis] * self.scale)
        self.robot.controller.linear_move({axis: sign * step}, feed=self.settings.feed)

    # -- convenience for the active mount -----------------------------
    def jog_z(self, sign: int) -> None:
        self.nudge(AxisId.Z if self.side is MountSide.LEFT else AxisId.A, sign)

    def jog_plunger(self, sign: int) -> None:
        self.nudge(AxisId.B if self.side is MountSide.LEFT else AxisId.C, sign)


#: Logical action names an input backend can emit. Kept as strings so any
#: keyboard/gamepad map can bind to them without importing motion code.
ACTIONS = ("x+", "x-", "y+", "y-", "z+", "z-", "plunger+", "plunger-",
           "step_up", "step_down", "mount_toggle", "home", "quit")


class JogSession:
    """Binds action names to JogController calls and dispatches them. Input
    backends translate raw keys/buttons into action names and call handle()."""

    def __init__(self, controller: JogController):
        self.c = controller
        self.running = True
        self._bindings = {
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
            "home": lambda: self.c.robot.home(),
            "quit": self._quit,
        }

    def _quit(self):
        self.running = False

    def handle(self, action: str) -> None:
        fn = self._bindings.get(action)
        if fn:
            fn()

    def bind(self, action: str, fn) -> None:
        self._bindings[action] = fn
