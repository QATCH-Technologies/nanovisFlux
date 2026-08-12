"""Manual jog panel: keyboard or gamepad input driving a JogController.

Every jog action is a continuous move: press and hold (a key, an on-screen
jog button, or a gamepad stick/trigger deflection) calls
JogController.begin_jog, which commands a move toward the axis's endstop
limit -- as far as it can physically go, the practical "max step size" --
at a feed proportional to speed; release calls end_jog, which quick-stops
it wherever it's gotten to. This now works correctly against FakeTransport
too (see transport/fake.py's real-time G1 simulation), not just real
hardware, which is why the panel no longer drives repeated discrete
nudge() calls the way it used to.
"""
from __future__ import annotations

from loguru import logger
from PyQt5.QtCore import Qt, QPointF, QSize, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                             QPushButton, QButtonGroup, QFrame, QStackedWidget,
                             QDoubleSpinBox, QCheckBox, QFormLayout)

from ..core import AxisId, MountSide
from ..geometry.coordinates import DeckPoint
from ..geometry.units import default_axis_scale
from . import icon_utils
from .gamepad_input import GamepadInput
from .tokens import TOKENS

_GOTO_MM_RANGE = (-100.0, 1000.0)   # generous bound around a typical deck's extent

_ICON_SIZE = QSize(16, 16)
_INK = QColor(*TOKENS["flat_text"][:3])
_ON_ACCENT = QColor(*TOKENS["flat_on_accent"][:3])
_SUCCESS = QColor(*TOKENS["flat_success"][:3])
_MUTED = QColor(*TOKENS["flat_text_muted"][:3])
_SURFACE2 = QColor(*TOKENS["flat_surface2"][:3])
_BORDER_STRONG = QColor(*TOKENS["flat_border_strong"][:3])

_MOUNT_BUTTONS = (("L", MountSide.LEFT), ("R", MountSide.RIGHT), ("rear", MountSide.REAR))
_MOUNT_ORDER = [MountSide.LEFT, MountSide.RIGHT, MountSide.REAR]

#: Axes with a known linear-travel calibration (see
#: geometry.units.MEASURED_AXIS_TRAVEL_MM) -- shown with a cm readout
#: alongside raw microsteps. B/C are plunger axes (volumetric, not linear).
_LINEAR_AXES = (AxisId.X, AxisId.Y, AxisId.Z, AxisId.A)

_KEY_MAP = {
    Qt.Key_Left: "x-", Qt.Key_Right: "x+",
    Qt.Key_Up: "y+", Qt.Key_Down: "y-",
    Qt.Key_PageUp: "z+", Qt.Key_PageDown: "z-",
    Qt.Key_BracketRight: "plunger+", Qt.Key_BracketLeft: "plunger-",
}

#: gamepad axis name -> (begin_jog call, end_jog call), both taking the
#: JogController as their first argument -- see GamepadInput.axis_speed_changed
#: and ManualControlPanel._on_gamepad_axis.
_GAMEPAD_JOG = {
    "x": (lambda jog, s: jog.begin_jog(AxisId.X, 1 if s > 0 else -1, abs(s)),
         lambda jog: jog.end_jog(AxisId.X)),
    "y": (lambda jog, s: jog.begin_jog(AxisId.Y, 1 if s > 0 else -1, abs(s)),
         lambda jog: jog.end_jog(AxisId.Y)),
    "z": (lambda jog, s: jog.begin_jog_z(1 if s > 0 else -1, abs(s)),
         lambda jog: jog.end_jog_z()),
    "plunger": (lambda jog, s: jog.begin_jog_plunger(1 if s > 0 else -1, abs(s)),
               lambda jog: jog.end_jog_plunger()),
}


def _set_pill_class(label: QLabel, css_class: str) -> None:
    """Swap a QLabel's "class" dynamic property and force Qt to re-match
    the stylesheet -- setProperty alone doesn't repaint, since Qt caches
    class-selector results per widget until explicitly re-polished."""
    label.setProperty("class", css_class)
    label.style().unpolish(label)
    label.style().polish(label)


class _StickIndicator(QWidget):
    """A small circle mimicking one analog stick: a fixed outer ring plus
    an inner knob that offsets toward the live deflection direction,
    proportional to magnitude -- so the on-screen gamepad page visibly
    "moves" the same way the physical stick does while jogging. `dx`/`dy`
    are each in [-1, 1]; see set_deflection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self._dx = 0.0
        self._dy = 0.0

    def set_deflection(self, dx: float, dy: float) -> None:
        dx = max(-1.0, min(1.0, dx))
        dy = max(-1.0, min(1.0, dy))
        if (dx, dy) == (self._dx, self._dy):
            return
        self._dx, self._dy = dx, dy
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        ring_r = min(self.width(), self.height()) / 2 - 2
        p.setPen(QPen(_BORDER_STRONG, 1.5))
        p.setBrush(_SURFACE2)
        p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)
        knob_r = ring_r * 0.42
        travel = ring_r - knob_r
        p.setPen(Qt.NoPen)
        p.setBrush(_INK)
        p.drawEllipse(QPointF(cx + self._dx * travel, cy + self._dy * travel), knob_r, knob_r)


class ManualControlPanel(QWidget):
    home_requested = pyqtSignal()
    estop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.robot = None
        self.jog = None            # JogController, set by set_context()
        self.gamepad: GamepadInput | None = None
        self._input_mode = "keyboard"
        self._input_locked = False  # True while a routine is running
        self._stick_deflection = {"x": 0.0, "y": 0.0, "z": 0.0}  # -> stick_left/stick_right

        # Continuous jog: press starts a move toward the endstop at the
        # current jog_speed (see JogController.begin_jog); release quick-
        # stops it wherever it got to. jog_speed is read fresh each call so
        # it always reflects whatever the step/speed dial is set to *now*.
        #
        # X/Y/Z signs are deliberately the OPPOSITE of JogController's own
        # "positive = away from the endstop" convention: away-from-home
        # raw motor X/Y actually maps to a SMALLER deck x/y (see
        # DeckCalibration/robot.example.yaml's calibration points -- the
        # gantry homes to the deck's back-right corner), which the 2D/3D
        # deck view then renders moving left/down on screen (deck_view's
        # _project is (x, -y), +screen-y is down). GamepadInput's
        # positive_dir/negative_dir already correct for this (see its own
        # "down = Z+" comment); these need the same correction so the "->"
        # /"^"/PgUp glyphs (and the identically-bound arrow keys) actually
        # move the marker the way they're labelled instead of backwards.
        self._begin = {
            "x-": self._guarded(lambda: self.jog.begin_jog(AxisId.X, +1, self.jog.jog_speed)),
            "x+": self._guarded(lambda: self.jog.begin_jog(AxisId.X, -1, self.jog.jog_speed)),
            "y+": self._guarded(lambda: self.jog.begin_jog(AxisId.Y, -1, self.jog.jog_speed)),
            "y-": self._guarded(lambda: self.jog.begin_jog(AxisId.Y, +1, self.jog.jog_speed)),
            "z+": self._guarded(lambda: self.jog.begin_jog_z(-1, self.jog.jog_speed)),
            "z-": self._guarded(lambda: self.jog.begin_jog_z(+1, self.jog.jog_speed)),
            "plunger+": self._guarded(lambda: self.jog.begin_jog_plunger(+1, self.jog.jog_speed)),
            "plunger-": self._guarded(lambda: self.jog.begin_jog_plunger(-1, self.jog.jog_speed)),
        }
        self._end = {
            "x-": self._guarded_end(lambda: self.jog.end_jog(AxisId.X)),
            "x+": self._guarded_end(lambda: self.jog.end_jog(AxisId.X)),
            "y+": self._guarded_end(lambda: self.jog.end_jog(AxisId.Y)),
            "y-": self._guarded_end(lambda: self.jog.end_jog(AxisId.Y)),
            "z+": self._guarded_end(lambda: self.jog.end_jog_z()),
            "z-": self._guarded_end(lambda: self.jog.end_jog_z()),
            "plunger+": self._guarded_end(lambda: self.jog.end_jog_plunger()),
            "plunger-": self._guarded_end(lambda: self.jog.end_jog_plunger()),
        }

        root = QVBoxLayout(self)
        root.setSpacing(10)

        root.addLayout(self._build_header())
        root.addLayout(self._build_mode_toggle())

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_keyboard_page())
        self.content_stack.addWidget(self._build_gamepad_page())
        root.addWidget(self.content_stack)

        root.addWidget(self._build_position_box())
        root.addWidget(self._build_goto_box())
        root.addLayout(self._build_bottom_buttons())

        legend = QLabel("keyboard: arrows = X/Y · PgUp/PgDn = Z · [ ] = plunger · "
                        "M = cycle mount · Esc = quick stop\n"
                        "gamepad: sticks jog · LT/RT fluidics · Y mount · A stop · X zero Z · "
                        "Back/View home · Start/Menu e-stop · LB/RB tip")
        legend.setWordWrap(True)
        legend.setProperty("class", "eyebrow")
        root.addWidget(legend)
        root.addStretch(1)

        self._refresh_enabled()

    # -- layout builders ------------------------------------------------------
    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        title = QLabel("Manual control")
        title.setProperty("class", "h1")
        header.addWidget(title)

        self.status_pill_icon = QLabel()
        self.status_pill_icon.setFixedSize(14, 14)
        header.addWidget(self.status_pill_icon)
        self.status_pill = QLabel("jog")
        _set_pill_class(self.status_pill, "pill")
        header.addWidget(self.status_pill)
        header.addStretch(1)

        mount_label = QLabel("active mount")
        mount_label.setProperty("class", "eyebrow")
        header.addWidget(mount_label)

        self.mount_buttons = {}
        mount_group = QButtonGroup(self)
        mount_group.setExclusive(True)
        for label, side in _MOUNT_BUTTONS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setFixedWidth(40)
            b.clicked.connect(lambda _checked, s=side: self._select_mount(s))
            mount_group.addButton(b)
            header.addWidget(b)
            self.mount_buttons[side] = b
        self.mount_buttons[MountSide.LEFT].setChecked(True)
        return header

    def _build_mode_toggle(self) -> QHBoxLayout:
        mode_row = QHBoxLayout()
        self.btn_keyboard = QPushButton("Keyboard")
        self.btn_keyboard.setIcon(icon_utils.icon("keyboard", _INK, size=16))
        self.btn_gamepad = QPushButton("Gamepad")
        self.btn_gamepad.setIcon(icon_utils.icon("gamepad", _INK, size=16))
        for b in (self.btn_keyboard, self.btn_gamepad):
            b.setCheckable(True)
            b.setMinimumHeight(36)
            b.setIconSize(_ICON_SIZE)
        self.btn_keyboard.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.btn_keyboard)
        mode_group.addButton(self.btn_gamepad)
        self.btn_keyboard.clicked.connect(lambda: self._set_input_mode("keyboard"))
        self.btn_gamepad.clicked.connect(lambda: self._set_input_mode("gamepad"))
        mode_row.addWidget(self.btn_keyboard, 1)
        mode_row.addWidget(self.btn_gamepad, 1)
        return mode_row

    def _key_cap(self, text: str, action: str, *, wide: bool = False,
                icon_name: str | None = None, rotation: float = 0) -> QPushButton:
        """A jog button styled/labelled as the physical key that triggers
        it (e.g. "PgUp"), rather than the semantic action name -- unless
        `icon_name` is given, in which case it shows that icon instead of
        text (the XY jog cross reuses chevron.svg, rotated per direction,
        rather than a "PgUp"-style keycap label)."""
        btn = self._jog_button(text, action, icon_name=icon_name, rotation=rotation)
        if wide:
            btn.setMinimumWidth(64)
        return btn

    def _captioned(self, item, caption: str, *, align=Qt.AlignCenter) -> QVBoxLayout:
        """A widget or layout with a small eyebrow-style caption beneath it."""
        col = QVBoxLayout()
        col.setSpacing(2)
        if isinstance(item, QWidget):
            col.addWidget(item, alignment=align)
        else:
            col.addLayout(item)
        label = QLabel(caption)
        label.setProperty("class", "eyebrow")
        label.setAlignment(align)
        col.addWidget(label)
        return col

    def _build_keyboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        top_row = QHBoxLayout()
        self.btn_esc = QPushButton("Esc")
        self.btn_esc.setObjectName("estop")
        self.btn_esc.clicked.connect(self._quick_stop)
        top_row.addLayout(self._captioned(self.btn_esc, "quick stop"))
        top_row.addStretch(1)

        step_col = QVBoxLayout()
        step_col.setSpacing(2)
        step_label = QLabel("STEP")
        step_label.setProperty("class", "eyebrow")
        step_label.setAlignment(Qt.AlignRight)
        step_col.addWidget(step_label)
        self.btn_step = QPushButton("×1")
        self.btn_step.clicked.connect(lambda: self._apply_step_cycle(+1))
        step_col.addWidget(self.btn_step)
        top_row.addLayout(step_col)

        self.btn_cycle_mount = QPushButton("M")
        top_row.addLayout(self._captioned(self.btn_cycle_mount, "cycle mount"))
        self.btn_cycle_mount.clicked.connect(self._cycle_mount)
        layout.addLayout(top_row)

        clusters = QHBoxLayout()
        clusters.setSpacing(18)

        xy_group = QVBoxLayout()
        xy_caption = QLabel("GANTRY · X / Y")
        xy_caption.setProperty("class", "eyebrow")
        xy_caption.setAlignment(Qt.AlignCenter)
        xy_group.addWidget(xy_caption)
        cross = QGridLayout()
        cross.setSpacing(6)
        self.btn_yplus = self._key_cap("↑", "y+", icon_name="chevron", rotation=0)
        self.btn_yminus = self._key_cap("↓", "y-", icon_name="chevron", rotation=180)
        self.btn_xminus = self._key_cap("←", "x-", icon_name="chevron", rotation=270)
        self.btn_xplus = self._key_cap("→", "x+", icon_name="chevron", rotation=90)
        cross.addWidget(self.btn_yplus, 0, 1)
        cross.addWidget(self.btn_xminus, 1, 0)
        cross.addWidget(self.btn_xplus, 1, 2)
        cross.addWidget(self.btn_yminus, 2, 1)
        xy_group.addLayout(cross)
        clusters.addLayout(xy_group)

        z_group = QVBoxLayout()
        z_caption = QLabel("Z LIFT")
        z_caption.setProperty("class", "eyebrow")
        z_caption.setAlignment(Qt.AlignCenter)
        z_group.addWidget(z_caption)
        self.btn_zplus = self._key_cap("PgUp", "z+", wide=True)
        self.btn_zminus = self._key_cap("PgDn", "z-", wide=True)
        z_group.addLayout(self._captioned(self.btn_zplus, "z+"))
        z_group.addLayout(self._captioned(self.btn_zminus, "z-"))
        clusters.addLayout(z_group)

        plunger_group = QVBoxLayout()
        plunger_caption = QLabel("PLUNGER")
        plunger_caption.setProperty("class", "eyebrow")
        plunger_caption.setAlignment(Qt.AlignCenter)
        plunger_group.addWidget(plunger_caption)
        self.btn_plunger_plus = self._key_cap("]", "plunger+", wide=True)
        self.btn_plunger_minus = self._key_cap("[", "plunger-", wide=True)
        plunger_group.addLayout(self._captioned(self.btn_plunger_plus, "aspirate +"))
        plunger_group.addLayout(self._captioned(self.btn_plunger_minus, "dispense −"))
        clusters.addLayout(plunger_group)

        layout.addLayout(clusters)

        hint = QLabel("keys highlight blue while held")
        hint.setProperty("class", "eyebrow")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _gamepad_button(self, text: str, color: str, on_click) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(34, 34)
        btn.setStyleSheet(
            f"QPushButton {{ border-radius: 17px; background: {color}; color: white; "
            "font-weight: 700; border: none; }"
            f"QPushButton:hover {{ background: {color}; }}"
        )
        btn.clicked.connect(on_click)
        return btn

    def _gamepad_pill(self, text: str, on_click, *,
                      icon_name: str | None = None, rotation: float = 0) -> QPushButton:
        btn = QPushButton("" if icon_name else text)
        if icon_name:
            btn.setIcon(icon_utils.icon(icon_name, _INK, size=16, rotation=rotation))
            btn.setIconSize(_ICON_SIZE)
        btn.clicked.connect(on_click)
        return btn

    def _decorative_pad_button(self, icon_name: str) -> QLabel:
        """A small non-interactive icon badge -- fills out the center
        button cluster to match the physical pad's button count (see the
        photo this layout is modeled on) for buttons this app doesn't
        (yet) bind to an action."""
        lbl = QLabel()
        lbl.setPixmap(icon_utils.icon(icon_name, _MUTED, size=14).pixmap(QSize(14, 14)))
        lbl.setFixedSize(22, 22)
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _build_gamepad_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        trigger_row = QHBoxLayout()
        self.btn_lt = self._gamepad_pill("LT   dispense −",
                                        self._guarded(lambda: self.jog.jog_plunger(-1)))
        self.btn_lb = self._gamepad_pill("LB   tip up", lambda: self._on_tip_action("pickup"))
        trigger_row.addWidget(self.btn_lt)
        trigger_row.addWidget(self.btn_lb)
        trigger_row.addStretch(1)
        self.btn_rb = self._gamepad_pill("tip drop   RB", lambda: self._on_tip_action("eject"))
        self.btn_rt = self._gamepad_pill("aspirate +   RT",
                                        self._guarded(lambda: self.jog.jog_plunger(+1)))
        trigger_row.addWidget(self.btn_rb)
        trigger_row.addWidget(self.btn_rt)
        layout.addLayout(trigger_row)

        body = QFrame()
        body.setProperty("class", "panel")
        body_layout = QHBoxLayout(body)

        # -- D-pad, offset to the left of the sticks/buttons cluster (see
        # the reference photo this whole page layout is modeled on) -- all
        # four directions cycle step size, same as the physical pad's own
        # up/down/left/right (see GamepadInput._handle_hat).
        dpad_col = QVBoxLayout()
        dpad = QGridLayout()
        dpad.setSpacing(2)
        self.btn_dpad_up = self._gamepad_pill("▲", lambda: self._apply_step_cycle(+1),
                                             icon_name="chevron", rotation=0)
        self.btn_dpad_down = self._gamepad_pill("▼", lambda: self._apply_step_cycle(-1),
                                               icon_name="chevron", rotation=180)
        self.btn_dpad_left = self._gamepad_pill("◀", lambda: self._apply_step_cycle(-1),
                                               icon_name="chevron", rotation=270)
        self.btn_dpad_right = self._gamepad_pill("▶", lambda: self._apply_step_cycle(+1),
                                                icon_name="chevron", rotation=90)
        for b in (self.btn_dpad_up, self.btn_dpad_down, self.btn_dpad_left, self.btn_dpad_right):
            b.setFixedSize(22, 18)
        dpad.addWidget(self.btn_dpad_up, 0, 1)
        dpad.addWidget(self.btn_dpad_left, 1, 0)
        dpad.addWidget(self.btn_dpad_right, 1, 2)
        dpad.addWidget(self.btn_dpad_down, 2, 1)
        dpad_col.addLayout(self._captioned(dpad, "D-pad · step size"))
        body_layout.addLayout(dpad_col)

        # -- both analog sticks, each showing live deflection while jogging
        # (see _StickIndicator / _on_gamepad_axis) -- the right stick only
        # ever moves vertically since this app only reads its Y axis (Z
        # jog); see GamepadInput's own "intentionally unhandled" note on
        # the right stick's X axis.
        sticks_row = QHBoxLayout()
        self.stick_left = _StickIndicator()
        sticks_row.addLayout(self._captioned(self.stick_left, "jog X / Y"))
        self.stick_right = _StickIndicator()
        sticks_row.addLayout(self._captioned(self.stick_right, "jog Z"))
        body_layout.addLayout(sticks_row)

        # -- center button cluster, mimicking the physical pad's column of
        # small buttons between the sticks and the face buttons. Only two
        # are wired to an action today (Home, E-STOP -- unchanged from
        # before, just re-iconed); the rest are decorative placeholders
        # matching the pad's actual button count.
        mid_col = QVBoxLayout()
        self.btn_back = self._gamepad_pill("", self.home_requested.emit, icon_name="minus_circle")
        mid_col.addLayout(self._captioned(self.btn_back, "home / view"))
        mid_col.addWidget(self._decorative_pad_button("add_circle"))
        mid_col.addWidget(self._decorative_pad_button("controller_connect"))
        self.btn_start = QPushButton()
        self.btn_start.setIcon(icon_utils.icon("square_circle", _ON_ACCENT, size=16))
        self.btn_start.setIconSize(_ICON_SIZE)
        self.btn_start.setObjectName("estop")
        self.btn_start.clicked.connect(self.estop_requested.emit)
        mid_col.addLayout(self._captioned(self.btn_start, "E-STOP"))
        mid_col.addWidget(self._decorative_pad_button("star_circle"))
        body_layout.addLayout(mid_col)

        right_col = QGridLayout()
        right_col.setSpacing(4)
        self.btn_y = self._gamepad_button("Y", "#B18A3E", self._cycle_mount)
        self.btn_x = self._gamepad_button("X", "#3E6E8E", self._zero_z)
        self.btn_b = self._gamepad_button("B", "#C13B2E", self._read_sensor)
        self.btn_a = self._gamepad_button("A", "#3E8E5B", self._quick_stop)
        right_col.addWidget(self.btn_y, 0, 1)
        right_col.addWidget(self.btn_x, 1, 0)
        right_col.addWidget(self.btn_b, 1, 2)
        right_col.addWidget(self.btn_a, 2, 1)
        body_layout.addLayout(right_col)
        layout.addWidget(body)

        legend_grid = QGridLayout()
        for i, text in enumerate(("Y cycle mount", "A stop motion", "X zero Z", "B read sensor")):
            lbl = QLabel(text)
            lbl.setProperty("class", "eyebrow")
            legend_grid.addWidget(lbl, i // 2, i % 2)
        layout.addLayout(legend_grid)
        layout.addStretch(1)
        return page

    def _build_position_box(self) -> QFrame:
        pos_box = QFrame()
        pos_box.setProperty("class", "card")
        pos_layout = QVBoxLayout(pos_box)
        pos_title = QLabel("LIVE POSITION (microsteps · cm)")
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
        return pos_box

    def _build_goto_box(self) -> QFrame:
        """Immediate "go to deck mm" for the active mount (see the header's
        mount selector) -- a blocking robot.safe_move_to/move_to call fired
        straight from the button handler, same as the Home button
        (MainWindow._on_home_requested): a single manual move is treated as
        an acceptable one-off block on the GUI thread, unlike a full
        multi-step Routine (see routine_runner.py's own docstring for why
        *that* gets a worker QThread instead)."""
        goto_box = QFrame()
        goto_box.setProperty("class", "card")
        goto_layout = QVBoxLayout(goto_box)
        goto_title = QLabel("GO TO (deck mm)")
        goto_title.setProperty("class", "eyebrow")
        goto_layout.addWidget(goto_title)

        form = QFormLayout()
        self.goto_spins: dict = {}
        for label in ("X", "Y", "Z"):
            spin = QDoubleSpinBox()
            spin.setRange(*_GOTO_MM_RANGE)
            spin.setDecimals(2)
            spin.setSuffix(" mm")
            form.addRow(label, spin)
            self.goto_spins[label] = spin
        goto_layout.addLayout(form)

        bottom_row = QHBoxLayout()
        self.goto_safe_check = QCheckBox("safe move (raise / cross / descend)")
        self.goto_safe_check.setChecked(True)
        bottom_row.addWidget(self.goto_safe_check, 1)
        self.btn_goto = QPushButton("Go")
        self.btn_goto.clicked.connect(self._go_to_point)
        bottom_row.addWidget(self.btn_goto)
        goto_layout.addLayout(bottom_row)
        return goto_box

    def _build_bottom_buttons(self) -> QVBoxLayout:
        rows = QVBoxLayout()
        row1 = QHBoxLayout()
        self.btn_zero_z = QPushButton("Zero Z")
        self.btn_zero_z.clicked.connect(self._zero_z)
        self.btn_read_sensor = QPushButton("Read rear sensor")
        self.btn_read_sensor.clicked.connect(self._read_sensor)
        row1.addWidget(self.btn_zero_z)
        row1.addWidget(self.btn_read_sensor)
        rows.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_home = QPushButton("Home")
        self.btn_home.setIcon(icon_utils.icon("home", _INK, size=16))
        self.btn_home.setIconSize(_ICON_SIZE)
        self.btn_home.clicked.connect(self.home_requested.emit)
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setObjectName("estop")
        self.btn_stop.setIcon(icon_utils.icon("power", _ON_ACCENT, size=16))
        self.btn_stop.setIconSize(_ICON_SIZE)
        self.btn_stop.clicked.connect(self.estop_requested.emit)
        row2.addWidget(self.btn_home)
        row2.addWidget(self.btn_stop)
        rows.addLayout(row2)
        return rows

    # -- helpers ------------------------------------------------------------
    def _guarded(self, fn):
        def call():
            if self.jog is None or self._input_locked:
                return
            fn()
        return call

    def _guarded_end(self, fn):
        """Like _guarded, but without the lock check -- releasing a held
        jog input must always be able to stop the move, even if a routine
        started running while it was held (set_routine_active already
        calls stop_all_jog in that case, but a stray release event should
        never be a no-op that leaves motion running)."""
        def call():
            if self.jog is None:
                return
            fn()
        return call

    def _jog_button(self, text: str, action: str, *,
                    icon_name: str | None = None, rotation: float = 0) -> QPushButton:
        btn = QPushButton("" if icon_name else text)
        if icon_name:
            btn.setIcon(icon_utils.icon(icon_name, _INK, size=16, rotation=rotation))
            btn.setIconSize(_ICON_SIZE)
        btn.setProperty("class", "jog")
        btn.pressed.connect(self._begin[action])
        btn.released.connect(self._end[action])
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
                 self.btn_plunger_minus, self.btn_zero_z, self.btn_lt, self.btn_rt):
            b.setEnabled(zp_enabled)
        self.btn_read_sensor.setEnabled(connected and not locked)
        self.btn_x.setEnabled(zp_enabled)
        self.btn_b.setEnabled(connected and not locked)
        for b in self.mount_buttons.values():
            b.setEnabled(connected and not locked)
        self.btn_step.setEnabled(connected and not locked)
        for b in (self.btn_dpad_up, self.btn_dpad_down, self.btn_dpad_left, self.btn_dpad_right):
            b.setEnabled(connected and not locked)
        self.btn_cycle_mount.setEnabled(connected and not locked)
        self.btn_y.setEnabled(connected and not locked)
        self.btn_home.setEnabled(connected and not locked)
        self.btn_goto.setEnabled(connected and not locked)
        for spin in self.goto_spins.values():
            spin.setEnabled(connected and not locked)
        self.goto_safe_check.setEnabled(connected and not locked)
        self.btn_stop.setEnabled(connected)
        self.btn_esc.setEnabled(connected)
        self.btn_a.setEnabled(connected)

    # -- mount / step size ----------------------------------------------------
    def _select_mount(self, side: MountSide) -> None:
        if self.jog is not None:
            self.jog.select_mount(side)
        for s, b in self.mount_buttons.items():
            b.setChecked(s is side)
        logger.info(f"active mount -> {side.value}")
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
        self.btn_step.setText(f"×{scale:g}")

    # -- one-shot actions -----------------------------------------------------
    def _zero_z(self) -> None:
        if self.jog is None:
            return
        try:
            contact = self.jog.capture_z_zero()
            logger.info(f"{contact.side.value} z_zero captured: "
                        f"{contact.z_zero_microsteps} microsteps "
                        f"(tip {contact.tip_length_mm:.1f} mm)")
        except Exception as exc:
            logger.error(f"zero Z failed: {exc}")

    def _go_to_point(self) -> None:
        if self.robot is None or self.jog is None or self._input_locked:
            return
        point = DeckPoint(self.goto_spins["X"].value(), self.goto_spins["Y"].value(),
                          self.goto_spins["Z"].value())
        side = self.jog.side
        safe = self.goto_safe_check.isChecked()
        try:
            # Robot.move_to/safe_move_to send absolute deck-mm targets but
            # don't set the positioning mode themselves -- they trust the
            # caller to already be in G90 (see RoutineRunner.run's own
            # set_absolute/set_relative bracketing around a routine's
            # moves). The ambient mode is G91 for the whole connection
            # (JogController.__enter__, so held-key jogging stays
            # relative), so without switching here first, the firmware
            # would treat this target as a RELATIVE move by that many
            # microsteps -- usually slamming into an endstop instead of
            # landing on the requested point. Always restore relative
            # mode afterward so jogging keeps working.
            self.robot.controller.set_absolute()
            try:
                (self.robot.safe_move_to if safe else self.robot.move_to)(point, side)
            finally:
                self.robot.controller.set_relative()
            logger.info(f"moved {side.value} to ({point.x:g}, {point.y:g}, "
                        f"{point.z:g}) mm{' (safe)' if safe else ''}")
        except Exception as exc:
            logger.error(f"go-to failed: {exc}")

    def _read_sensor(self) -> None:
        if self.robot is None:
            return
        sensor = self.robot.rear()
        if sensor is None:
            logger.warning("no ultrasonic sensor attached to the rear mount")
            return
        try:
            distance = sensor.read_distance_mm()
            if distance is None:
                logger.warning("out of range / no echo")
            else:
                logger.info(f"rear distance: {distance:.1f} mm")
        except Exception as exc:
            logger.error(f"sensor read failed: {exc}")

    def _quick_stop(self) -> None:
        if self.robot is not None:
            self.robot.controller.quick_stop()
            logger.warning("quick stop")

    def _on_gamepad_axis(self, axis_name: str, signed: float) -> None:
        """A stick/trigger's deflection changed. 0 means centered/released
        -- stop; otherwise (re)start a continuous jog at this speed,
        matching real accel/decel-by-deflection behaviour (see
        JogController.begin_jog's own restart-tolerance for why re-calling
        this every poll tick while deflected is cheap, not redundant)."""
        if axis_name in self._stick_deflection:
            self._stick_deflection[axis_name] = signed
            if axis_name in ("x", "y"):
                self.stick_left.set_deflection(
                    self._stick_deflection["x"], self._stick_deflection["y"])
            else:  # "z" -- right stick only ever reads vertical deflection
                self.stick_right.set_deflection(0.0, self._stick_deflection["z"])
        if self.jog is None:
            return
        begin, end = _GAMEPAD_JOG[axis_name]
        if signed == 0.0 or self._input_locked:
            end(self.jog)
        else:
            begin(self.jog, signed)

    def _on_tip_action(self, action: str) -> None:
        if self.robot is None or self.jog is None or self._input_locked:
            return
        from scripts.gamepad_control import pickup_tip_in_place, eject_tip_in_place
        try:
            (pickup_tip_in_place if action == "pickup" else eject_tip_in_place)(self.robot, self.jog.side)
        except Exception as exc:
            logger.error(f"{action} tip failed: {exc}")

    # -- input mode ---------------------------------------------------------
    def _set_input_mode(self, mode: str) -> None:
        self._input_mode = mode
        if mode == "gamepad":
            self.content_stack.setCurrentIndex(1)
            self._start_gamepad()
        else:
            self.content_stack.setCurrentIndex(0)
            self._stop_gamepad()
            _set_pill_class(self.status_pill, "pill")
            self.status_pill.setText("jog")
            self.status_pill_icon.clear()

    def _on_gamepad_connected(self, connected: bool) -> None:
        if connected:
            _set_pill_class(self.status_pill, "pill-live")
            self.status_pill.setText("pad connected")
            self.status_pill_icon.setPixmap(
                icon_utils.icon("controller_connect", _SUCCESS, size=14).pixmap(_ICON_SIZE))
        else:
            _set_pill_class(self.status_pill, "pill-warn")
            self.status_pill.setText("no gamepad")
            self.status_pill_icon.setPixmap(icon_utils.icon("gamepad", _MUTED, size=14).pixmap(_ICON_SIZE))

    def _start_gamepad(self) -> None:
        if self.gamepad is not None:
            return
        self.gamepad = GamepadInput(self)
        self.gamepad.axis_speed_changed.connect(self._on_gamepad_axis)
        self.gamepad.mount_toggle_requested.connect(self._cycle_mount)
        self.gamepad.home_requested.connect(self.home_requested.emit)
        self.gamepad.estop_requested.connect(self.estop_requested.emit)
        self.gamepad.quick_stop_requested.connect(self._quick_stop)
        self.gamepad.step_cycle_requested.connect(self._apply_step_cycle)
        self.gamepad.read_sensor_requested.connect(self._read_sensor)
        self.gamepad.zero_z_requested.connect(self._zero_z)
        self.gamepad.tip_action_requested.connect(self._on_tip_action)
        self.gamepad.connected_changed.connect(self._on_gamepad_connected)
        self.gamepad.status.connect(lambda msg: logger.info(msg))
        self.gamepad.start()

    def _stop_gamepad(self) -> None:
        if self.gamepad is not None:
            self.gamepad.stop()
            self.gamepad.deleteLater()
            self.gamepad = None
        self._stick_deflection = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.stick_left.set_deflection(0.0, 0.0)
        self.stick_right.set_deflection(0.0, 0.0)

    # -- keyboard entry points, called from MainWindow.keyPressEvent --------
    def handle_key_press(self, key: int, autorepeat: bool) -> bool:
        if autorepeat or self._input_mode != "keyboard" or self.jog is None or self._input_locked:
            return False
        action = _KEY_MAP.get(key)
        if action:
            self._begin[action]()
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
            self._end[action]()
            return True
        return False

    # -- lifecycle ------------------------------------------------------------
    def stop_all_jog(self) -> None:
        if self.jog is not None:
            self.jog.end_jog()   # every axis at once -- see JogController.end_jog
        if self.gamepad is not None:
            self.gamepad.stop()

    def set_context(self, robot, jog) -> None:
        self.stop_all_jog()
        self.robot = robot
        self.jog = jog
        if jog is not None:
            for side, b in self.mount_buttons.items():
                b.setChecked(side is jog.side)
            self.btn_step.setText(f"×{jog.scale:g}")
        self._refresh_enabled()

    def set_routine_active(self, active: bool) -> None:
        self._input_locked = active
        if active:
            self.stop_all_jog()
        self._refresh_enabled()

    def update_positions(self, positions: dict) -> None:
        for axis, label in self.pos_labels.items():
            value = positions.get(axis)
            if value is None:
                label.setText("--")
            elif axis in _LINEAR_AXES:
                cm = default_axis_scale(axis).to_cm(value)
                label.setText(f"{value}  ({cm:.2f} cm)")
            else:
                label.setText(str(value))
