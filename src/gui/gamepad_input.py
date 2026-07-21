"""Gamepad polling for manual jog.

Adapted from scripts/gamepad_control.py's GamepadTeleop -- same axis
indices and button legend (see that module's docstring for the hardware
caveats) -- but driving discrete, rate-limited nudges (see jog_timers.py)
instead of JogController's begin_jog continuous-move model, and emitting Qt
signals instead of touching a Robot directly. This class is a pure input
source; ManualControlPanel decides what each signal means.
"""
from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from .jog_timers import RateAccumulator

# Both sticks fully (X, Y) before the triggers -- see gamepad_control.py's docstring.
AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
AXIS_RIGHT_STICK_Y = 3
AXIS_LEFT_TRIGGER = 4
AXIS_RIGHT_TRIGGER = 5

DEADZONE = 0.2
TRIGGER_DEADZONE = 0.12
MIN_RATE_HZ = 1.0     # nudge rate at the edge of the deadzone
MAX_RATE_HZ = 9.0     # nudge rate at full deflection
POLL_HZ = 30.0


def _normalized(raw: float, deadzone: float) -> float:
    if abs(raw) < deadzone:
        return 0.0
    return max(0.0, min(1.0, (abs(raw) - deadzone) / (1.0 - deadzone)))


def _trigger_fraction(raw: float) -> float:
    """SDL2 commonly reports triggers as -1.0 (released) .. 1.0 (pressed)."""
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))


class GamepadInput(QObject):
    nudge_requested = pyqtSignal(str, int)   # "x"/"y"/"z"/"plunger", sign
    mount_toggle_requested = pyqtSignal()
    home_requested = pyqtSignal()
    estop_requested = pyqtSignal()
    quick_stop_requested = pyqtSignal()
    step_cycle_requested = pyqtSignal(int)
    read_sensor_requested = pyqtSignal()
    tip_action_requested = pyqtSignal(str)   # "pickup"/"eject"
    status = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pygame = None
        self._pad = None
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / POLL_HZ))
        self._timer.timeout.connect(self._poll)
        self._rates = {"x": RateAccumulator(), "y": RateAccumulator(),
                      "z": RateAccumulator(), "plunger": RateAccumulator()}

    def start(self) -> None:
        try:
            import pygame
        except ImportError:
            self.status.emit("gamepad unavailable: pygame is not installed")
            return
        try:
            pygame.init()
            pygame.joystick.init()
            if pygame.joystick.get_count() == 0:
                self.status.emit("no gamepad detected")
                return
            self._pygame = pygame
            self._pad = pygame.joystick.Joystick(0)
            self._pad.init()
            self.status.emit(f"gamepad connected: {self._pad.get_name()}")
            self._timer.start()
        except Exception as exc:
            self.status.emit(f"gamepad unavailable: {exc}")

    def stop(self) -> None:
        self._timer.stop()
        for axis_rate in self._rates.values():
            axis_rate.reset()
        if self._pygame is not None:
            try:
                self._pygame.quit()
            except Exception:
                pass
        self._pygame = None
        self._pad = None

    def _poll(self) -> None:
        if self._pad is None:
            return
        try:
            self._poll_unsafe()
        except Exception as exc:
            self.status.emit(f"gamepad error: {exc}")
            self.stop()

    def _poll_unsafe(self) -> None:
        pygame = self._pygame
        pad = self._pad
        dt = self._timer.interval() / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.JOYBUTTONDOWN:
                self._handle_button(event.button)
            elif event.type == pygame.JOYHATMOTION:
                self._handle_hat(event.value)

        n_axes = pad.get_numaxes()
        lx = pad.get_axis(AXIS_LEFT_STICK_X) if n_axes > AXIS_LEFT_STICK_X else 0.0
        ly = pad.get_axis(AXIS_LEFT_STICK_Y) if n_axes > AXIS_LEFT_STICK_Y else 0.0
        ry = pad.get_axis(AXIS_RIGHT_STICK_Y) if n_axes > AXIS_RIGHT_STICK_Y else 0.0
        lt = pad.get_axis(AXIS_LEFT_TRIGGER) if n_axes > AXIS_LEFT_TRIGGER else -1.0
        rt = pad.get_axis(AXIS_RIGHT_TRIGGER) if n_axes > AXIS_RIGHT_TRIGGER else -1.0

        self._axis_tick("x", lx, dt, positive_dir=-1, negative_dir=+1)
        self._axis_tick("y", ly, dt, positive_dir=+1, negative_dir=-1)
        # down = Z+ (this project's "descending increases microsteps"
        # convention) -- matches gamepad_control.py's deliberate choice.
        self._axis_tick("z", ry, dt, positive_dir=+1, negative_dir=-1)

        lt_frac = _trigger_fraction(lt)
        rt_frac = _trigger_fraction(rt)
        lt_speed = 0.0 if lt_frac < TRIGGER_DEADZONE else (lt_frac - TRIGGER_DEADZONE) / (1.0 - TRIGGER_DEADZONE)
        rt_speed = 0.0 if rt_frac < TRIGGER_DEADZONE else (rt_frac - TRIGGER_DEADZONE) / (1.0 - TRIGGER_DEADZONE)
        if lt_speed > 0 and rt_speed == 0:
            self._rate_tick("plunger", lt_speed, dt, +1)   # aspirate
        elif rt_speed > 0 and lt_speed == 0:
            self._rate_tick("plunger", rt_speed, dt, -1)   # dispense
        else:
            self._rates["plunger"].reset()

    def _axis_tick(self, name: str, raw: float, dt: float, positive_dir: int, negative_dir: int) -> None:
        norm = _normalized(raw, DEADZONE)
        if norm == 0.0:
            self._rates[name].reset()
            return
        sign = positive_dir if raw > 0 else negative_dir
        self._rate_tick(name, norm, dt, sign)

    def _rate_tick(self, name: str, norm: float, dt: float, sign: int) -> None:
        rate = MIN_RATE_HZ + norm * (MAX_RATE_HZ - MIN_RATE_HZ)
        n = self._rates[name].step(dt, rate)
        for _ in range(n):
            self.nudge_requested.emit(name, sign)

    def _handle_button(self, button: int) -> None:
        if button == 7:      # Start/Menu
            self.estop_requested.emit()
        elif button == 0:    # A
            self.quick_stop_requested.emit()
        elif button == 1:    # B
            self.read_sensor_requested.emit()
        elif button == 3:    # Y
            self.mount_toggle_requested.emit()
        elif button == 4:    # LB
            self.tip_action_requested.emit("pickup")
        elif button == 5:    # RB
            self.tip_action_requested.emit("eject")
        elif button == 6:    # Back/View
            self.home_requested.emit()

    def _handle_hat(self, value: tuple) -> None:
        _x, y = value
        if y == 1:
            self.step_cycle_requested.emit(+1)
        elif y == -1:
            self.step_cycle_requested.emit(-1)
