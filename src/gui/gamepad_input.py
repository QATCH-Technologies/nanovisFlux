"""Gamepad polling for manual jog.

Adapted from scripts/gamepad_control.py's GamepadTeleop -- same axis
indices and button legend (see that module's docstring for the hardware
caveats) -- but emitting a continuous signed speed per axis (stick/trigger
deflection -> JogController.begin_jog's speed argument) rather than driving
a Robot directly. This class is a pure input source; ManualControlPanel
decides what each signal means.
"""
from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

# Both sticks fully (X, Y) before the triggers -- see gamepad_control.py's docstring.
AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
AXIS_RIGHT_STICK_Y = 3
AXIS_LEFT_TRIGGER = 4
AXIS_RIGHT_TRIGGER = 5

DEADZONE = 0.2
TRIGGER_DEADZONE = 0.12
POLL_HZ = 30.0
_SPEED_EPSILON = 0.02   # matches JogController.begin_jog's own restart tolerance


def _normalized(raw: float, deadzone: float) -> float:
    if abs(raw) < deadzone:
        return 0.0
    return max(0.0, min(1.0, (abs(raw) - deadzone) / (1.0 - deadzone)))


def _trigger_fraction(raw: float) -> float:
    """SDL2 commonly reports triggers as -1.0 (released) .. 1.0 (pressed)."""
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))


class GamepadInput(QObject):
    #: "x"/"y"/"z"/"plunger", signed speed in [-1, 1] -- 0 means centered/
    #: released (stop); ManualControlPanel maps nonzero straight onto
    #: JogController.begin_jog(..., speed=abs(value)) and 0 onto end_jog().
    axis_speed_changed = pyqtSignal(str, float)
    mount_toggle_requested = pyqtSignal()
    home_requested = pyqtSignal()
    estop_requested = pyqtSignal()
    quick_stop_requested = pyqtSignal()
    step_cycle_requested = pyqtSignal(int)
    read_sensor_requested = pyqtSignal()
    zero_z_requested = pyqtSignal()
    tip_action_requested = pyqtSignal(str)   # "pickup"/"eject"
    status = pyqtSignal(str)
    connected_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pygame = None
        self._pad = None
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / POLL_HZ))
        self._timer.timeout.connect(self._poll)
        self._last_speed = {"x": 0.0, "y": 0.0, "z": 0.0, "plunger": 0.0}

    def start(self) -> None:
        try:
            import pygame
        except ImportError:
            self.status.emit("gamepad unavailable: pygame is not installed")
            self.connected_changed.emit(False)
            return
        try:
            pygame.init()
            pygame.joystick.init()
            if pygame.joystick.get_count() == 0:
                self.status.emit("no gamepad detected")
                self.connected_changed.emit(False)
                return
            self._pygame = pygame
            self._pad = pygame.joystick.Joystick(0)
            self._pad.init()
            self.status.emit(f"gamepad connected: {self._pad.get_name()}")
            self.connected_changed.emit(True)
            self._timer.start()
        except Exception as exc:
            self.status.emit(f"gamepad unavailable: {exc}")
            self.connected_changed.emit(False)

    def stop(self) -> None:
        self._timer.stop()
        for name, speed in self._last_speed.items():
            if speed != 0.0:
                self.axis_speed_changed.emit(name, 0.0)
        self._last_speed = {k: 0.0 for k in self._last_speed}
        if self._pygame is not None:
            try:
                self._pygame.quit()
            except Exception:
                pass
        self._pygame = None
        self._pad = None
        self.connected_changed.emit(False)

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

        self._axis_tick("x", lx, positive_dir=-1, negative_dir=+1)
        self._axis_tick("y", ly, positive_dir=+1, negative_dir=-1)
        # down = Z+ (this project's "descending increases microsteps"
        # convention) -- matches gamepad_control.py's deliberate choice.
        self._axis_tick("z", ry, positive_dir=+1, negative_dir=-1)

        lt_frac = _trigger_fraction(lt)
        rt_frac = _trigger_fraction(rt)
        lt_speed = 0.0 if lt_frac < TRIGGER_DEADZONE else (lt_frac - TRIGGER_DEADZONE) / (1.0 - TRIGGER_DEADZONE)
        rt_speed = 0.0 if rt_frac < TRIGGER_DEADZONE else (rt_frac - TRIGGER_DEADZONE) / (1.0 - TRIGGER_DEADZONE)
        if lt_speed > 0 and rt_speed == 0:
            self._emit_speed("plunger", +lt_speed)   # aspirate
        elif rt_speed > 0 and lt_speed == 0:
            self._emit_speed("plunger", -rt_speed)   # dispense
        else:
            self._emit_speed("plunger", 0.0)

    def _axis_tick(self, name: str, raw: float, positive_dir: int, negative_dir: int) -> None:
        norm = _normalized(raw, DEADZONE)
        if norm == 0.0:
            self._emit_speed(name, 0.0)
            return
        sign = positive_dir if raw > 0 else negative_dir
        self._emit_speed(name, sign * norm)

    def _emit_speed(self, name: str, signed: float) -> None:
        """Emit only on a meaningful change -- every centered/idle poll
        (30/sec) would otherwise re-emit 0.0 and make ManualControlPanel
        call end_jog needlessly often."""
        last = self._last_speed[name]
        if signed == 0.0:
            if last != 0.0:
                self._last_speed[name] = 0.0
                self.axis_speed_changed.emit(name, 0.0)
        elif abs(signed - last) > _SPEED_EPSILON:
            self._last_speed[name] = signed
            self.axis_speed_changed.emit(name, signed)

    def _handle_button(self, button: int) -> None:
        if button == 7:      # Start/Menu
            self.estop_requested.emit()
        elif button == 0:    # A
            self.quick_stop_requested.emit()
        elif button == 1:    # B
            self.read_sensor_requested.emit()
        elif button == 2:    # X
            self.zero_z_requested.emit()
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
