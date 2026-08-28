from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
AXIS_RIGHT_STICK_Y = 3
AXIS_LEFT_TRIGGER = 4
AXIS_RIGHT_TRIGGER = 5

DEADZONE = 0.2
TRIGGER_DEADZONE = 0.12
POLL_HZ = 30.0
_SPEED_EPSILON = 0.02


def _normalized(raw: float, deadzone: float) -> float:
    if abs(raw) < deadzone:
        return 0.0
    return max(0.0, min(1.0, (abs(raw) - deadzone) / (1.0 - deadzone)))


def _trigger_fraction(raw: float) -> float:
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))


_HIGHLIGHT_BUTTONS = {0: "A", 1: "B", 2: "X", 3: "Y", 4: "LB", 5: "RB", 6: "minus", 7: "plus"}


class GamepadInput(QObject):
    axis_speed_changed = pyqtSignal(str, float)
    mount_toggle_requested = pyqtSignal()
    home_requested = pyqtSignal()
    estop_requested = pyqtSignal()
    quick_stop_requested = pyqtSignal()
    step_cycle_requested = pyqtSignal(int)
    read_sensor_requested = pyqtSignal()
    zero_z_requested = pyqtSignal()
    tip_action_requested = pyqtSignal(str)
    status = pyqtSignal(str)
    connected_changed = pyqtSignal(bool, str)
    button_highlight_changed = pyqtSignal(str, bool)
    trigger_changed = pyqtSignal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pygame = None
        self._pad = None
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / POLL_HZ))
        self._timer.timeout.connect(self._poll)
        self._last_speed = {"x": 0.0, "y": 0.0, "z": 0.0, "plunger": 0.0}
        self._last_trigger = {"LT": 0.0, "RT": 0.0}
        self._pressed_highlights: set[str] = set()

    def start(self) -> None:
        try:
            import pygame
        except ImportError:
            self.status.emit("gamepad unavailable: pygame is not installed")
            self.connected_changed.emit(False, "")
            return
        try:
            pygame.init()
            pygame.joystick.init()
        except Exception as exc:
            self.status.emit(f"gamepad unavailable: {exc}")
            self.connected_changed.emit(False, "")
            return
        self._pygame = pygame
        self._pad = None
        self.status.emit("waiting for a gamepad...")
        self.connected_changed.emit(False, "")
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        for name, speed in self._last_speed.items():
            if speed != 0.0:
                self.axis_speed_changed.emit(name, 0.0)
        self._last_speed = {k: 0.0 for k in self._last_speed}
        for name, level in self._last_trigger.items():
            if level != 0.0:
                self.trigger_changed.emit(name, 0.0)
        self._last_trigger = {k: 0.0 for k in self._last_trigger}
        for name in self._pressed_highlights:
            self.button_highlight_changed.emit(name, False)
        self._pressed_highlights.clear()
        if self._pygame is not None:
            try:
                self._pygame.quit()
            except Exception:
                pass
        self._pygame = None
        self._pad = None
        self.connected_changed.emit(False, "")

    def _poll(self) -> None:
        if self._pygame is None:
            return
        try:
            if self._pad is None:
                self._try_attach()
            else:
                self._poll_unsafe()
        except Exception as exc:
            self.status.emit(f"gamepad error: {exc}")
            self.stop()

    def _try_attach(self) -> None:
        pygame = self._pygame
        pygame.event.pump()
        if pygame.joystick.get_count() == 0:
            return
        self._pad = pygame.joystick.Joystick(0)
        self._pad.init()
        name = self._pad.get_name()
        self.status.emit(f"gamepad connected: {name}")
        self.connected_changed.emit(True, name)

    def _poll_unsafe(self) -> None:
        pygame = self._pygame
        pad = self._pad

        for event in pygame.event.get():
            if event.type == pygame.JOYBUTTONDOWN:
                self._set_highlight(event.button, True)
                self._handle_button(event.button)
            elif event.type == pygame.JOYBUTTONUP:
                self._set_highlight(event.button, False)
            elif event.type == pygame.JOYHATMOTION:
                self._handle_hat(event.value)

        n_axes = pad.get_numaxes()
        lx = pad.get_axis(AXIS_LEFT_STICK_X) if n_axes > AXIS_LEFT_STICK_X else 0.0
        ly = pad.get_axis(AXIS_LEFT_STICK_Y) if n_axes > AXIS_LEFT_STICK_Y else 0.0
        ry = pad.get_axis(AXIS_RIGHT_STICK_Y) if n_axes > AXIS_RIGHT_STICK_Y else 0.0
        lt = pad.get_axis(AXIS_LEFT_TRIGGER) if n_axes > AXIS_LEFT_TRIGGER else -1.0
        rt = pad.get_axis(AXIS_RIGHT_TRIGGER) if n_axes > AXIS_RIGHT_TRIGGER else -1.0

        self._axis_tick("x", lx)
        self._axis_tick("y", ly)
        self._axis_tick("z", ry)

        lt_frac = _trigger_fraction(lt)
        rt_frac = _trigger_fraction(rt)
        lt_speed = (
            0.0
            if lt_frac < TRIGGER_DEADZONE
            else (lt_frac - TRIGGER_DEADZONE) / (1.0 - TRIGGER_DEADZONE)
        )
        rt_speed = (
            0.0
            if rt_frac < TRIGGER_DEADZONE
            else (rt_frac - TRIGGER_DEADZONE) / (1.0 - TRIGGER_DEADZONE)
        )
        self._emit_trigger("LT", lt_speed)
        self._emit_trigger("RT", rt_speed)
        if lt_speed > 0 and rt_speed == 0:
            self._emit_speed("plunger", +lt_speed)
        elif rt_speed > 0 and lt_speed == 0:
            self._emit_speed("plunger", -rt_speed)
        else:
            self._emit_speed("plunger", 0.0)

    def _axis_tick(self, name: str, raw: float) -> None:
        norm = _normalized(raw, DEADZONE)
        if norm == 0.0:
            self._emit_speed(name, 0.0)
            return
        sign = 1.0 if raw > 0 else -1.0
        self._emit_speed(name, sign * norm)

    def _emit_speed(self, name: str, signed: float) -> None:
        last = self._last_speed[name]
        if signed == 0.0:
            if last != 0.0:
                self._last_speed[name] = 0.0
                self.axis_speed_changed.emit(name, 0.0)
        elif abs(signed - last) > _SPEED_EPSILON:
            self._last_speed[name] = signed
            self.axis_speed_changed.emit(name, signed)

    def _emit_trigger(self, name: str, value: float) -> None:
        last = self._last_trigger[name]
        if value == 0.0:
            if last != 0.0:
                self._last_trigger[name] = 0.0
                self.trigger_changed.emit(name, 0.0)
        elif abs(value - last) > _SPEED_EPSILON:
            self._last_trigger[name] = value
            self.trigger_changed.emit(name, value)

    def _set_highlight(self, name_or_button: int | str, pressed: bool) -> None:
        name = (
            _HIGHLIGHT_BUTTONS.get(name_or_button)
            if isinstance(name_or_button, int)
            else name_or_button
        )
        if name is None:
            return
        was_pressed = name in self._pressed_highlights
        if pressed == was_pressed:
            return
        if pressed:
            self._pressed_highlights.add(name)
        else:
            self._pressed_highlights.discard(name)
        self.button_highlight_changed.emit(name, pressed)

    def _handle_button(self, button: int) -> None:
        if button == 7:
            self.estop_requested.emit()
        elif button == 0:
            self.quick_stop_requested.emit()
        elif button == 1:
            self.read_sensor_requested.emit()
        elif button == 2:
            self.zero_z_requested.emit()
        elif button == 3:
            self.mount_toggle_requested.emit()
        elif button == 4:
            self.tip_action_requested.emit("pickup")
        elif button == 5:
            self.tip_action_requested.emit("eject")
        elif button == 6:
            self.home_requested.emit()

    def _handle_hat(self, value: tuple) -> None:
        x, y = value
        self._set_highlight("dpad_up", y == 1)
        self._set_highlight("dpad_down", y == -1)
        self._set_highlight("dpad_left", x == -1)
        self._set_highlight("dpad_right", x == 1)
        if y == 1:
            self.step_cycle_requested.emit(+1)
        elif y == -1:
            self.step_cycle_requested.emit(-1)
        if x == 1:
            self.step_cycle_requested.emit(+1)
        elif x == -1:
            self.step_cycle_requested.emit(-1)
