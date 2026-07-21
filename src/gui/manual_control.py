"""Manual jog panel: keyboard or gamepad input driving a JogController.

See jog_timers.py for why every jog action here is a repeated discrete
nudge() rather than JogController's begin_jog/end_jog continuous-move model
(that model assumes a real, asynchronous controller a quick-stop can
interrupt mid-flight; FakeTransport executes instantly, so it can't).
"""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                             QPushButton, QButtonGroup, QFrame)

from ..core import AxisId, MountSide
from .jog_timers import HoldRepeater
from .gamepad_input import GamepadInput

_MOUNT_BUTTONS = (("L", MountSide.LEFT), ("R", MountSide.RIGHT), ("rear", MountSide.REAR))
_MOUNT_ORDER = [MountSide.LEFT, MountSide.RIGHT, MountSide.REAR]

_KEY_MAP = {
    Qt.Key_Left: "x-", Qt.Key_Right: "x+",
    Qt.Key_Up: "y+", Qt.Key_Down: "y-",
    Qt.Key_PageUp: "z+", Qt.Key_PageDown: "z-",
    Qt.Key_BracketRight: "plunger+", Qt.Key_BracketLeft: "plunger-",
}


class ManualControlPanel(QWidget):
    home_requested = pyqtSignal()
    estop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.robot = None
        self.jog = None            # JogController, set by set_context()
        self.tracer = None
        self.gamepad: GamepadInput | None = None
        self._input_mode = "keyboard"
        self._input_locked = False  # True while a routine is running

        self._actions = {
            "x-": self._guarded(lambda: self.jog.nudge(AxisId.X, -1)),
            "x+": self._guarded(lambda: self.jog.nudge(AxisId.X, +1)),
            "y+": self._guarded(lambda: self.jog.nudge(AxisId.Y, +1)),
            "y-": self._guarded(lambda: self.jog.nudge(AxisId.Y, -1)),
            "z+": self._guarded(lambda: self.jog.jog_z(+1)),
            "z-": self._guarded(lambda: self.jog.jog_z(-1)),
            "plunger+": self._guarded(lambda: self.jog.jog_plunger(+1)),
            "plunger-": self._guarded(lambda: self.jog.jog_plunger(-1)),
        }
        self._repeaters = {name: HoldRepeater(fn) for name, fn in self._actions.items()}

        root = QVBoxLayout(self)
        root.setSpacing(10)

        mode_row = QHBoxLayout()
        self.btn_keyboard = QPushButton("⌨  Keyboard")
        self.btn_gamepad = QPushButton("🎮  Gamepad")
        for b in (self.btn_keyboard, self.btn_gamepad):
            b.setCheckable(True)
        self.btn_keyboard.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.btn_keyboard)
        mode_group.addButton(self.btn_gamepad)
        self.btn_keyboard.clicked.connect(lambda: self._set_input_mode("keyboard"))
        self.btn_gamepad.clicked.connect(lambda: self._set_input_mode("gamepad"))
        mode_row.addWidget(self.btn_keyboard)
        mode_row.addWidget(self.btn_gamepad)
        root.addLayout(mode_row)

        mount_row = QHBoxLayout()
        self.mount_buttons = {}
        mount_group = QButtonGroup(self)
        mount_group.setExclusive(True)
        for label, side in _MOUNT_BUTTONS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _checked, s=side: self._select_mount(s))
            mount_group.addButton(b)
            mount_row.addWidget(b)
            self.mount_buttons[side] = b
        self.mount_buttons[MountSide.LEFT].setChecked(True)
        mount_row.addStretch(1)
        self.btn_step = QPushButton("step ×1")
        self.btn_step.clicked.connect(lambda: self._apply_step_cycle(+1))
        mount_row.addWidget(self.btn_step)
        root.addLayout(mount_row)

        cross = QGridLayout()
        cross.setSpacing(6)
        self.btn_yplus = self._jog_button("Y+", "y+")
        self.btn_yminus = self._jog_button("Y-", "y-")
        self.btn_xminus = self._jog_button("X-", "x-")
        self.btn_xplus = self._jog_button("X+", "x+")
        xy_label = QLabel("XY")
        xy_label.setAlignment(Qt.AlignCenter)
        xy_label.setProperty("class", "eyebrow")
        cross.addWidget(self.btn_yplus, 0, 1)
        cross.addWidget(self.btn_xminus, 1, 0)
        cross.addWidget(xy_label, 1, 1)
        cross.addWidget(self.btn_xplus, 1, 2)
        cross.addWidget(self.btn_yminus, 2, 1)

        self.btn_zplus = self._jog_button("Z+", "z+")
        self.btn_zminus = self._jog_button("Z-", "z-")
        z_label = QLabel("Z")
        z_label.setAlignment(Qt.AlignCenter)
        z_label.setProperty("class", "eyebrow")
        cross.addWidget(self.btn_zplus, 0, 3)
        cross.addWidget(z_label, 1, 3)
        cross.addWidget(self.btn_zminus, 2, 3)
        root.addLayout(cross)

        plunger_row = QHBoxLayout()
        self.btn_plunger_plus = self._jog_button("Plunger +", "plunger+")
        self.btn_plunger_minus = self._jog_button("Plunger −", "plunger-")
        plunger_row.addWidget(self.btn_plunger_plus)
        plunger_row.addWidget(self.btn_plunger_minus)
        root.addLayout(plunger_row)

        pos_box = QFrame()
        pos_box.setProperty("class", "card")
        pos_layout = QVBoxLayout(pos_box)
        pos_title = QLabel("LIVE POSITION (microsteps)")
        pos_title.setProperty("class", "eyebrow")
        pos_layout.addWidget(pos_title)
        pos_grid = QGridLayout()
        self.pos_labels = {}
        for i, axis in enumerate((AxisId.X, AxisId.Y, AxisId.Z, AxisId.A, AxisId.B, AxisId.C)):
            r, c = divmod(i, 2)
            name_lbl = QLabel(axis.letter)
            val_lbl = QLabel("--")
            val_lbl.setProperty("class", "mono")
            pos_grid.addWidget(name_lbl, r, c * 2)
            pos_grid.addWidget(val_lbl, r, c * 2 + 1)
            self.pos_labels[axis] = val_lbl
        pos_layout.addLayout(pos_grid)
        root.addWidget(pos_box)

        btn_row = QHBoxLayout()
        self.btn_zero_z = QPushButton("Zero Z")
        self.btn_zero_z.clicked.connect(self._zero_z)
        self.btn_read_sensor = QPushButton("Read rear sensor")
        self.btn_read_sensor.clicked.connect(self._read_sensor)
        btn_row.addWidget(self.btn_zero_z)
        btn_row.addWidget(self.btn_read_sensor)
        root.addLayout(btn_row)

        legend = QLabel("keyboard: arrows = X/Y · PgUp/PgDn = Z · [ ] = plunger · "
                        "M = cycle mount · Esc = quick stop\n"
                        "gamepad: sticks jog · LT/RT fluidics · Y mount · A stop · "
                        "Back/View home · Start/Menu e-stop · LB/RB tip")
        legend.setWordWrap(True)
        legend.setProperty("class", "eyebrow")
        root.addWidget(legend)
        root.addStretch(1)

        self._refresh_enabled()

    # -- helpers ------------------------------------------------------------
    def _guarded(self, fn):
        def call():
            if self.jog is None or self._input_locked:
                return
            fn()
        return call

    def _jog_button(self, text: str, action: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("class", "jog")
        rep = self._repeaters[action]
        btn.pressed.connect(rep.start)
        btn.released.connect(rep.stop)
        return btn

    def _refresh_enabled(self) -> None:
        connected = self.jog is not None
        rear = connected and self.jog.side is MountSide.REAR
        locked = self._input_locked
        xy_enabled = connected and not locked
        zp_enabled = connected and not locked and not rear
        for b in (self.btn_xplus, self.btn_xminus, self.btn_yplus, self.btn_yminus):
            b.setEnabled(xy_enabled)
        for b in (self.btn_zplus, self.btn_zminus, self.btn_plunger_plus,
                 self.btn_plunger_minus, self.btn_zero_z):
            b.setEnabled(zp_enabled)
        self.btn_read_sensor.setEnabled(connected and not locked)
        for b in self.mount_buttons.values():
            b.setEnabled(connected and not locked)
        self.btn_step.setEnabled(connected and not locked)

    # -- mount / step size ----------------------------------------------------
    def _select_mount(self, side: MountSide) -> None:
        if self.jog is not None:
            self.jog.select_mount(side)
        for s, b in self.mount_buttons.items():
            b.setChecked(s is side)
        if self.tracer:
            self.tracer.note(f"active mount -> {side.value}")
        self._refresh_enabled()

    def _cycle_mount(self) -> None:
        if self.jog is None:
            return
        idx = (_MOUNT_ORDER.index(self.jog.side) + 1) % len(_MOUNT_ORDER)
        self._select_mount(_MOUNT_ORDER[idx])

    def _apply_step_cycle(self, direction: int) -> None:
        if self.jog is None:
            return
        scale = self.jog.cycle_scale(direction)
        self.btn_step.setText(f"step ×{scale:g}")

    # -- one-shot actions -----------------------------------------------------
    def _zero_z(self) -> None:
        if self.jog is None:
            return
        try:
            contact = self.jog.capture_z_zero()
            if self.tracer:
                self.tracer.note(f"{contact.side.value} z_zero captured: "
                                 f"{contact.z_zero_microsteps} microsteps "
                                 f"(tip {contact.tip_length_mm:.1f} mm)")
        except Exception as exc:
            if self.tracer:
                self.tracer.note(f"zero Z failed: {exc}")

    def _read_sensor(self) -> None:
        if self.robot is None:
            return
        sensor = self.robot.rear()
        if sensor is None:
            if self.tracer:
                self.tracer.note("no ultrasonic sensor attached to the rear mount")
            return
        try:
            distance = sensor.read_distance_mm()
            msg = ("out of range / no echo" if distance is None
                  else f"rear distance: {distance:.1f} mm")
            if self.tracer:
                self.tracer.note(msg)
        except Exception as exc:
            if self.tracer:
                self.tracer.note(f"sensor read failed: {exc}")

    def _quick_stop(self) -> None:
        if self.robot is not None:
            self.robot.controller.quick_stop()
            if self.tracer:
                self.tracer.note("quick stop")

    def _on_gamepad_nudge(self, axis_name: str, sign: int) -> None:
        if self.jog is None or self._input_locked:
            return
        if axis_name == "x":
            self.jog.nudge(AxisId.X, sign)
        elif axis_name == "y":
            self.jog.nudge(AxisId.Y, sign)
        elif axis_name == "z":
            self.jog.jog_z(sign)
        elif axis_name == "plunger":
            self.jog.jog_plunger(sign)

    def _on_tip_action(self, action: str) -> None:
        if self.robot is None or self.jog is None or self._input_locked:
            return
        from scripts.gamepad_control import pickup_tip_in_place, eject_tip_in_place
        try:
            (pickup_tip_in_place if action == "pickup" else eject_tip_in_place)(self.robot, self.jog.side)
        except Exception as exc:
            if self.tracer:
                self.tracer.note(f"{action} tip failed: {exc}")

    # -- input mode ---------------------------------------------------------
    def _set_input_mode(self, mode: str) -> None:
        self._input_mode = mode
        if mode == "gamepad":
            self._start_gamepad()
        else:
            self._stop_gamepad()

    def _start_gamepad(self) -> None:
        if self.gamepad is not None:
            return
        self.gamepad = GamepadInput(self)
        self.gamepad.nudge_requested.connect(self._on_gamepad_nudge)
        self.gamepad.mount_toggle_requested.connect(self._cycle_mount)
        self.gamepad.home_requested.connect(self.home_requested.emit)
        self.gamepad.estop_requested.connect(self.estop_requested.emit)
        self.gamepad.quick_stop_requested.connect(self._quick_stop)
        self.gamepad.step_cycle_requested.connect(self._apply_step_cycle)
        self.gamepad.read_sensor_requested.connect(self._read_sensor)
        self.gamepad.tip_action_requested.connect(self._on_tip_action)
        self.gamepad.status.connect(lambda msg: self.tracer.note(msg) if self.tracer else None)
        self.gamepad.start()

    def _stop_gamepad(self) -> None:
        if self.gamepad is not None:
            self.gamepad.stop()
            self.gamepad.deleteLater()
            self.gamepad = None

    # -- keyboard entry points, called from MainWindow.keyPressEvent --------
    def handle_key_press(self, key: int, autorepeat: bool) -> bool:
        if autorepeat or self._input_mode != "keyboard" or self.jog is None or self._input_locked:
            return False
        action = _KEY_MAP.get(key)
        if action:
            self._repeaters[action].start()
            return True
        if key == Qt.Key_M:
            self._cycle_mount()
            return True
        if key == Qt.Key_Escape:
            self._quick_stop()
            return True
        return False

    def handle_key_release(self, key: int, autorepeat: bool) -> bool:
        if autorepeat or self._input_mode != "keyboard":
            return False
        action = _KEY_MAP.get(key)
        if action:
            self._repeaters[action].stop()
            return True
        return False

    # -- lifecycle ------------------------------------------------------------
    def stop_all_jog(self) -> None:
        for rep in self._repeaters.values():
            rep.stop()
        if self.gamepad is not None:
            self.gamepad.stop()

    def set_context(self, robot, jog, tracer) -> None:
        self.stop_all_jog()
        self.robot = robot
        self.jog = jog
        self.tracer = tracer
        if jog is not None:
            for side, b in self.mount_buttons.items():
                b.setChecked(side is jog.side)
            self.btn_step.setText(f"step ×{jog.scale:g}")
        self._refresh_enabled()

    def set_routine_active(self, active: bool) -> None:
        self._input_locked = active
        if active:
            self.stop_all_jog()
        self._refresh_enabled()

    def update_positions(self, positions: dict) -> None:
        for axis, label in self.pos_labels.items():
            value = positions.get(axis)
            label.setText("--" if value is None else str(value))
