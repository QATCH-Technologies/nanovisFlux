from __future__ import annotations

from loguru import logger
from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import AxisId, MountSide
from ..geometry.coordinates import DeckPoint
from ..geometry.units import default_axis_scale
from . import icon_utils
from .gamepad_input import GamepadInput
from .style import ACCENT_RED
from .tokens import TOKENS

_GOTO_MM_RANGE = (-100.0, 1000.0)
_ICON_SIZE = QSize(16, 16)
_INK = QColor(*TOKENS["flat_text"][:3])
_ON_ACCENT = QColor(*TOKENS["flat_on_accent"][:3])
_SUCCESS = QColor(*TOKENS["flat_success"][:3])
_MUTED = QColor(*TOKENS["flat_text_muted"][:3])
_SURFACE2 = QColor(*TOKENS["flat_surface2"][:3])
_BORDER_STRONG = QColor(*TOKENS["flat_border_strong"][:3])
_PAD_BODY = QColor("#33383E")
_PAD_DARK = QColor("#22262B")
_PAD_SHOULDER_TOP = QColor("#2B2F34")
_PAD_GRIP = QColor("#2B2F34")
_PAD_ACCENT = QColor("#35C13A")
_PAD_KNOB = QColor("#4A4F56")
_PAD_ICON_MUTED = QColor("#8B9096")

_MOUNT_BUTTONS = (("L", MountSide.LEFT), ("R", MountSide.RIGHT), ("rear", MountSide.REAR))
_MOUNT_ORDER = [MountSide.LEFT, MountSide.RIGHT, MountSide.REAR]
_LINEAR_AXES = (AxisId.X, AxisId.Y, AxisId.Z, AxisId.A)

_KEY_MAP = {
    Qt.Key_Left: "x-",
    Qt.Key_Right: "x+",
    Qt.Key_Up: "y+",
    Qt.Key_Down: "y-",
    Qt.Key_PageUp: "z+",
    Qt.Key_PageDown: "z-",
    Qt.Key_BracketRight: "plunger+",
    Qt.Key_BracketLeft: "plunger-",
}

_GAMEPAD_JOG = {
    "x": (
        lambda jog, s: jog.begin_jog(AxisId.X, -1 if s > 0 else 1, abs(s)),
        lambda jog: jog.end_jog(AxisId.X),
    ),
    "y": (
        lambda jog, s: jog.begin_jog(AxisId.Y, 1 if s > 0 else -1, abs(s)),
        lambda jog: jog.end_jog(AxisId.Y),
    ),
    "z": (lambda jog, s: jog.begin_jog_z(1 if s > 0 else -1, abs(s)), lambda jog: jog.end_jog_z()),
    "plunger": (
        lambda jog, s: jog.begin_jog_plunger(1 if s > 0 else -1, abs(s)),
        lambda jog: jog.end_jog_plunger(),
    ),
}


def _set_pill_class(label: QLabel, css_class: str) -> None:
    label.setProperty("class", css_class)
    label.style().unpolish(label)
    label.style().polish(label)


class _StickIndicator(QWidget):

    def __init__(
        self,
        parent=None,
        *,
        diameter: int = 56,
        ring: QColor = _BORDER_STRONG,
        bg: QColor = _SURFACE2,
        knob: QColor = _INK,
    ):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self._ring, self._bg, self._knob = ring, bg, knob
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
        p.setPen(QPen(self._ring, 1.5))
        p.setBrush(self._bg)
        p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)
        knob_r = ring_r * 0.42
        travel = ring_r - knob_r
        p.setPen(Qt.NoPen)
        p.setBrush(self._knob)
        p.drawEllipse(QPointF(cx + self._dx * travel, cy + self._dy * travel), knob_r, knob_r)


def _corner_path(
    x: float, y: float, w: float, h: float, tl: float, tr: float, br: float, bl: float
):
    path = QPainterPath()
    path.moveTo(x + tl, y)
    path.lineTo(x + w - tr, y)
    path.quadTo(x + w, y, x + w, y + tr)
    path.lineTo(x + w, y + h - br)
    path.quadTo(x + w, y + h, x + w - br, y + h)
    path.lineTo(x + bl, y + h)
    path.quadTo(x, y + h, x, y + h - bl)
    path.lineTo(x, y + tl)
    path.quadTo(x, y, x + tl, y)
    path.closeSubpath()
    return path


def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    """Blend c1 (t=0) toward c2 (t=1) -- used for the analog trigger
    shoulders, whose fill tracks depression continuously rather than
    snapping on/off like a digital button's highlight."""
    t = max(0.0, min(1.0, t))
    return QColor(
        round(c1.red() + (c2.red() - c1.red()) * t),
        round(c1.green() + (c2.green() - c1.green()) * t),
        round(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


_PAD_CANVAS = (470.0, 300.0)
_PAD_MIN_WIDTH = 260
_PAD_MAX_WIDTH = 480
_PAD_BODY_RECT = (35, 26, 400, 200)
_PAD_SHOULDER_L_TOP = (103, 0, 74, 15)
_PAD_SHOULDER_L_BOTTOM = (96, 20, 88, 16)
_PAD_SHOULDER_R_TOP = (293, 0, 74, 15)
_PAD_SHOULDER_R_BOTTOM = (286, 20, 88, 16)
_PAD_GRIP_L = (100, 206, 13, (56, 40, 64, 74))
_PAD_GRIP_R = (370, 206, -13, (40, 56, 74, 64))
_PAD_GRIP_SIZE = (148, 172)
_PAD_DPAD_V = (132, 144, 18, 56)
_PAD_DPAD_H = (113, 163, 56, 18)
_PAD_FACE_BUTTONS = {
    "Y": (318, 58, 24),
    "X": (291, 85, 24),
    "B": (345, 85, 24),
    "A": (318, 112, 24),
}
_PAD_STICK_L = (101, 64, 64)
_PAD_STICK_R = (305, 138, 64)
_PAD_HUB_CONNECT = (218, 80, 34)
_PAD_HUB_MINUS = (187, 87, 20)
_PAD_HUB_PLUS = (263, 87, 20)
_PAD_HUB_SQUARE = (199, 120, 20)
_PAD_HUB_START = (251, 120, 20)


class _ControllerStage(QWidget):
    _HIGHLIGHT_NAMES = frozenset(
        {
            "A",
            "B",
            "X",
            "Y",
            "LB",
            "RB",
            "minus",
            "plus",
            "dpad_up",
            "dpad_down",
            "dpad_left",
            "dpad_right",
        }
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(_PAD_MIN_WIDTH)
        self.setMaximumWidth(_PAD_MAX_WIDTH)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._connect_icon = icon_utils.icon("controller_connect", _PAD_ACCENT, size=18).pixmap(
            QSize(18, 18)
        )
        self._start_icon = icon_utils.icon("star_circle", _PAD_ICON_MUTED, size=12).pixmap(
            QSize(12, 12)
        )
        self._start_icon_lit = icon_utils.icon("star_circle", _PAD_DARK, size=12).pixmap(
            QSize(12, 12)
        )
        self._pressed: set[str] = set()
        self._trigger_level = {"LT": 0.0, "RT": 0.0}

        self.stick_left = _StickIndicator(
            self, diameter=1, ring=_PAD_ACCENT, bg=_PAD_DARK, knob=_PAD_KNOB
        )
        self.stick_right = _StickIndicator(
            self, diameter=1, ring=_PAD_ACCENT, bg=_PAD_DARK, knob=_PAD_KNOB
        )
        self._layout_children()

    def set_button_pressed(self, name: str, pressed: bool) -> None:
        if name not in self._HIGHLIGHT_NAMES or (name in self._pressed) == pressed:
            return
        if pressed:
            self._pressed.add(name)
        else:
            self._pressed.discard(name)
        self.update()

    def set_trigger_level(self, name: str, value: float) -> None:
        value = max(0.0, min(1.0, value))
        if name not in self._trigger_level or self._trigger_level[name] == value:
            return
        self._trigger_level[name] = value
        self.update()

    def clear_live_state(self) -> None:
        changed = bool(self._pressed) or any(self._trigger_level.values())
        self._pressed.clear()
        self._trigger_level = {k: 0.0 for k in self._trigger_level}
        if changed:
            self.update()

    def heightForWidth(self, width: int) -> int:
        return round(width * _PAD_CANVAS[1] / _PAD_CANVAS[0])

    def sizeHint(self) -> QSize:
        w = round(_PAD_CANVAS[0] * 0.8)
        return QSize(w, self.heightForWidth(w))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_children()

    def _layout_children(self) -> None:
        scale = (self.width() or round(_PAD_CANVAS[0] * 0.8)) / _PAD_CANVAS[0]
        for stick, (x, y, d) in ((self.stick_left, _PAD_STICK_L), (self.stick_right, _PAD_STICK_R)):
            size = max(10, round(d * scale))
            stick.setFixedSize(size, size)
            stick.move(round(x * scale), round(y * scale))

    def _hub_glyph(
        self, p: QPainter, x: float, y: float, d: float, kind: str, lit: bool = False
    ) -> None:
        cx, cy = x + d / 2, y + d / 2
        pen = QPen(_PAD_DARK if lit else _PAD_ICON_MUTED, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if kind == "minus":
            p.drawLine(QPointF(cx - 4.5, cy), QPointF(cx + 4.5, cy))
        elif kind == "plus":
            p.drawLine(QPointF(cx - 4.5, cy), QPointF(cx + 4.5, cy))
            p.drawLine(QPointF(cx, cy - 4.5), QPointF(cx, cy + 4.5))
        elif kind == "square":
            p.drawRoundedRect(QRectF(cx - 4, cy - 4, 8, 8), 1.5, 1.5)
        p.setPen(Qt.NoPen)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        scale = self.width() / _PAD_CANVAS[0]
        p.scale(scale, scale)
        p.setPen(Qt.NoPen)
        p.setBrush(_lerp_color(_PAD_SHOULDER_TOP, _PAD_ACCENT, self._trigger_level["LT"]))
        p.drawPath(_corner_path(*_PAD_SHOULDER_L_TOP, 8, 8, 4, 4))
        p.setBrush(_lerp_color(_PAD_SHOULDER_TOP, _PAD_ACCENT, self._trigger_level["RT"]))
        p.drawPath(_corner_path(*_PAD_SHOULDER_R_TOP, 8, 8, 4, 4))
        p.setBrush(_PAD_ACCENT if "LB" in self._pressed else _PAD_DARK)
        p.drawPath(_corner_path(*_PAD_SHOULDER_L_BOTTOM, 9, 9, 4, 4))
        p.setBrush(_PAD_ACCENT if "RB" in self._pressed else _PAD_DARK)
        p.drawPath(_corner_path(*_PAD_SHOULDER_R_BOTTOM, 9, 9, 4, 4))
        p.setBrush(_PAD_GRIP)
        gw, gh = _PAD_GRIP_SIZE
        for cx, cy, angle, radii in (_PAD_GRIP_L, _PAD_GRIP_R):
            p.save()
            p.translate(cx, cy)
            p.rotate(angle)
            p.drawPath(_corner_path(-gw / 2, -gh / 2, gw, gh, *radii))
            p.restore()
        p.setBrush(_PAD_BODY)
        p.drawPath(_corner_path(*_PAD_BODY_RECT, 108, 108, 88, 88))
        vx, vy, vw, vh = _PAD_DPAD_V
        hx, hy, hw, hh = _PAD_DPAD_H
        for name, rect, radii in (
            ("dpad_up", (vx, vy, vw, hy - vy), (4, 4, 0, 0)),
            ("dpad_down", (vx, hy + hh, vw, vy + vh - hy - hh), (0, 0, 4, 4)),
            ("dpad_left", (hx, hy, vx - hx, hh), (4, 0, 0, 4)),
            ("dpad_right", (vx + vw, hy, hx + hw - vx - vw, hh), (0, 4, 4, 0)),
        ):
            p.setBrush(_PAD_ACCENT if name in self._pressed else _PAD_DARK)
            p.drawPath(_corner_path(*rect, *radii))
        p.setBrush(_PAD_DARK)
        p.drawRect(QRectF(vx, hy, vw, hh))
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(9)
        p.setFont(font)
        for letter, (x, y, d) in _PAD_FACE_BUTTONS.items():
            lit = letter in self._pressed
            p.setPen(Qt.NoPen)
            p.setBrush(_PAD_ACCENT if lit else _PAD_DARK)
            p.drawEllipse(QRectF(x, y, d, d))
            p.setPen(_PAD_DARK if lit else _PAD_ACCENT)
            p.drawText(QRectF(x, y, d, d), Qt.AlignCenter, letter)
        p.setPen(Qt.NoPen)
        p.setBrush(_PAD_DARK)
        cx, cy, cd = _PAD_HUB_CONNECT
        p.drawEllipse(QRectF(cx, cy, cd, cd))
        p.drawPixmap(round(cx + cd / 2 - 9), round(cy + cd / 2 - 9), self._connect_icon)
        for (x, y, d), kind in (
            (_PAD_HUB_MINUS, "minus"),
            (_PAD_HUB_PLUS, "plus"),
            (_PAD_HUB_SQUARE, "square"),
            (_PAD_HUB_START, "start"),
        ):
            lit = kind in self._pressed
            p.setPen(Qt.NoPen)
            p.setBrush(_PAD_ACCENT if lit else _PAD_DARK)
            p.drawEllipse(QRectF(x, y, d, d))
            if kind == "start":
                icon_px = self._start_icon_lit if lit else self._start_icon
                isize = icon_px.width()
                p.drawPixmap(round(x + d / 2 - isize / 2), round(y + d / 2 - isize / 2), icon_px)
            else:
                self._hub_glyph(p, x, y, d, kind, lit)


class _VScrollArea(QScrollArea):
    """A QScrollArea that only ever constrains/scrolls vertically. Plain
    QScrollArea + setWidgetResizable(True) refuses to shrink its content
    widget below that widget's own minimumSizeHint in EITHER dimension --
    fine normally, but ManualControlPanel's content is a QWidget directly
    (not one, see __init__), so once _ControllerStage's height-for-width
    growth can push the panel's total height past the viewport, that same
    refusal also stops the panel from ever getting narrower than its
    widest row (e.g. the header), even though every row here already
    degrades gracefully to a narrower width on its own -- exactly what a
    plain, non-scrolling QWidget would have let it do. Forcing the content
    width to the viewport on every resize restores that, while height
    stays free to exceed the viewport and scroll."""

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = self.widget()
        if w is not None:
            w.setFixedWidth(self.viewport().width())


class ManualControlPanel(QWidget):
    home_requested = pyqtSignal()
    estop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.robot = None
        self.jog = None  # JogController, set by set_context()
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
        # DeckCalibration/configs/calibration.yaml's calibration points --
        # the gantry homes to the deck's back-right corner), which the 2D/3D
        # deck view then renders moving left/down on screen (deck_view's
        # _project is (x, -y), +screen-y is down). _GAMEPAD_JOG above
        # applies the same correction for x (y/z's raw sign already lines
        # up); these need it too so the "->" /"^"/PgUp glyphs (and the
        # identically-bound arrow keys) actually move the marker the way
        # they're labelled instead of backwards.
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

        content = QWidget()
        root = QVBoxLayout(content)
        root.setSpacing(8)

        root.addLayout(self._build_header())
        root.addLayout(self._build_mode_toggle())

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_keyboard_page())
        self.content_stack.addWidget(self._build_gamepad_page())
        root.addWidget(self.content_stack)

        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        info_row.addWidget(self._build_position_box(), 1)
        info_row.addWidget(self._build_goto_box(), 1)
        root.addLayout(info_row)
        root.addLayout(self._build_bottom_buttons())
        root.addStretch(1)

        # The controller-stage illustration (see _ControllerStage) grows
        # with the panel's width, which on a wide-but-short window can ask
        # for more total height than the tab actually has -- without a
        # scroll area that would silently squeeze every widget below it
        # (fixed-size badges, buttons) into too little space, overlapping
        # rather than resizing. A scroll area instead just grows past the
        # viewport and scrolls, which is always safe.
        scroll = _VScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

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
            # A few px narrower than a plain round number so the header row
            # keeps a little slack below the panel's default width even
            # when the vertical scrollbar (see the QScrollArea wrapping
            # this panel's content) is showing and eating into it.
            b.setFixedWidth(34)
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

    def _key_cap(
        self,
        text: str,
        action: str,
        *,
        wide: bool = False,
        icon_name: str | None = None,
        rotation: float = 0,
    ) -> QPushButton:
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

        hint = QLabel(
            "arrows = X/Y · PgUp/PgDn = Z · [ ] = plunger · M = cycle mount · "
            "Esc = quick stop · keys highlight blue while held"
        )
        hint.setWordWrap(True)
        hint.setProperty("class", "eyebrow")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _control_badge(self, text: str, *, circle: bool = False, danger: bool = False) -> QLabel:
        """A small pill or circle label used only in the Control map legend
        below the controller illustration -- plain text-on-background, not
        a QPushButton, since none of these are click-able: the physical
        control is what you actually press, this just names it."""
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        bg = ACCENT_RED if danger else "#22262B"
        fg = "#35C13A" if circle else "#FDFDFE"
        if circle:
            lbl.setFixedSize(22, 22)
            radius = 11
        else:
            lbl.setFixedSize(58, 22)
            radius = 5
        lbl.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {fg}; border-radius: {radius}px; "
            "font-weight: 700; font-size: 11px; }"
        )
        return lbl

    def _control_map_card(
        self, title: str, rows: list[tuple[QLabel, str]], *, columns: int = 1
    ) -> QFrame:
        """One category card in the Control map (Motion / Face buttons /
        Fluidics / System) -- a badge naming the physical control paired
        with a plain-text description of what it does."""
        card = QFrame()
        card.setStyleSheet("QFrame { background: #F7F9FA; border-radius: 6px; }")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)
        heading = QLabel(title)
        heading.setProperty("class", "eyebrow")
        outer.addWidget(heading)
        body = QGridLayout() if columns > 1 else QVBoxLayout()
        body.setSpacing(9)
        for i, (badge, desc) in enumerate(rows):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(badge)
            desc_label = QLabel(desc)
            # Word-wrap so a narrow panel can shrink these cards instead of
            # forcing the whole row (and everything below the illustration)
            # wider than the panel actually is.
            desc_label.setWordWrap(True)
            row.addWidget(desc_label, 1)
            if columns > 1:
                body.addLayout(row, i // columns, i % columns)
            else:
                body.addLayout(row)
        outer.addLayout(body)
        return card

    def _build_gamepad_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        # -- static reference illustration of the physical pad -- see
        # _ControllerStage's own docstring for why nothing on it (besides
        # the two sticks' live deflection) is click-able.
        stage_frame = QFrame()
        stage_frame.setProperty("class", "panel")
        # Widget-level stylesheets take precedence over the app-level one
        # regardless of selector specificity (Qt's own cascade, not CSS's)
        # -- this drops just the ".panel" class's border while its
        # background/radius still come through from app_theme.qss.
        stage_frame.setStyleSheet("QFrame { border: none; }")
        stage_layout = QVBoxLayout(stage_frame)
        stage_layout.setContentsMargins(14, 14, 14, 12)
        stage = _ControllerStage()
        # Wrapped in an HBox with a stretch on each side rather than added
        # directly (or with an alignment flag, which would collapse it to
        # sizeHint and defeat _ControllerStage's whole Expanding size
        # policy): below _PAD_MAX_WIDTH the stage's own Expanding policy
        # outcompetes the two zero-sizeHint stretches for the row's space,
        # so it keeps scaling with the panel; once it hits the cap, further
        # space has nowhere else to go and splits evenly between the two
        # stretches, centering it instead of leaving it flush left.
        stage_row = QHBoxLayout()
        stage_row.addStretch(1)
        stage_row.addWidget(stage)
        stage_row.addStretch(1)
        stage_layout.addLayout(stage_row)
        layout.addWidget(stage_frame)
        # _on_gamepad_axis drives these by name, same attributes as before
        # the sticks moved onto the illustration.
        self.stick_left = stage.stick_left
        self.stick_right = stage.stick_right
        self._controller_stage = stage

        map_title = QLabel("CONTROL MAP")
        map_title.setProperty("class", "section-title")
        layout.addWidget(map_title)

        control_map = QGridLayout()
        control_map.setSpacing(10)
        control_map.addWidget(
            self._control_map_card(
                "MOTION",
                [
                    (self._control_badge("L stick"), "jog X / Y"),
                    (self._control_badge("R stick"), "jog Z"),
                    (self._control_badge("D-pad"), "step size"),
                ],
            ),
            0,
            0,
        )
        control_map.addWidget(
            self._control_map_card(
                "FACE BUTTONS",
                [
                    (self._control_badge("A", circle=True), "stop motion"),
                    (self._control_badge("B", circle=True), "read sensor"),
                    (self._control_badge("X", circle=True), "zero Z"),
                    (self._control_badge("Y", circle=True), "cycle mount"),
                ],
                columns=2,
            ),
            0,
            1,
        )
        control_map.addWidget(
            self._control_map_card(
                "FLUIDICS",
                [
                    (self._control_badge("LT / RT"), "dispense − / aspirate +"),
                    (self._control_badge("LB / RB"), "tip up / tip drop"),
                ],
            ),
            1,
            0,
        )
        control_map.addWidget(
            self._control_map_card(
                "SYSTEM",
                [
                    (self._control_badge("-"), "home"),
                    (self._control_badge("+", danger=True), "e-stop"),
                ],
            ),
            1,
            1,
        )
        layout.addLayout(control_map)
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
        rows.setSpacing(8)

        actions = QHBoxLayout()
        self.btn_zero_z = QPushButton("Zero Z")
        self.btn_zero_z.clicked.connect(self._zero_z)
        self.btn_read_sensor = QPushButton("Read rear sensor")
        self.btn_read_sensor.clicked.connect(self._read_sensor)
        self.btn_home = QPushButton("Home")
        self.btn_home.setIcon(icon_utils.icon("home", _INK, size=16))
        self.btn_home.setIconSize(_ICON_SIZE)
        self.btn_home.clicked.connect(self.home_requested.emit)
        for b in (self.btn_zero_z, self.btn_read_sensor, self.btn_home):
            actions.addWidget(b)
        rows.addLayout(actions)

        self.btn_stop = QPushButton("EMERGENCY STOP")
        self.btn_stop.setObjectName("estop")
        self.btn_stop.setIcon(icon_utils.icon("power", _ON_ACCENT, size=18))
        self.btn_stop.setIconSize(QSize(18, 18))
        self.btn_stop.setMinimumHeight(40)
        self.btn_stop.clicked.connect(self.estop_requested.emit)
        rows.addWidget(self.btn_stop)
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

    def _jog_button(
        self, text: str, action: str, *, icon_name: str | None = None, rotation: float = 0
    ) -> QPushButton:
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
        for b in (
            self.btn_zplus,
            self.btn_zminus,
            self.btn_plunger_plus,
            self.btn_plunger_minus,
            self.btn_zero_z,
        ):
            b.setEnabled(zp_enabled)
        self.btn_read_sensor.setEnabled(connected and not locked)
        for b in self.mount_buttons.values():
            b.setEnabled(connected and not locked)
        self.btn_step.setEnabled(connected and not locked)
        self.btn_cycle_mount.setEnabled(connected and not locked)
        self.btn_home.setEnabled(connected and not locked)
        self.btn_goto.setEnabled(connected and not locked)
        for spin in self.goto_spins.values():
            spin.setEnabled(connected and not locked)
        self.goto_safe_check.setEnabled(connected and not locked)
        self.btn_stop.setEnabled(connected)
        self.btn_esc.setEnabled(connected)

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
            logger.info(
                f"{contact.side.value} z_zero captured: "
                f"{contact.z_zero_microsteps} microsteps "
                f"(tip {contact.tip_length_mm:.1f} mm)"
            )
        except Exception as exc:
            logger.error(f"zero Z failed: {exc}")

    def _go_to_point(self) -> None:
        if self.robot is None or self.jog is None or self._input_locked:
            return
        point = DeckPoint(
            self.goto_spins["X"].value(), self.goto_spins["Y"].value(), self.goto_spins["Z"].value()
        )
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
            logger.info(
                f"moved {side.value} to ({point.x:g}, {point.y:g}, "
                f"{point.z:g}) mm{' (safe)' if safe else ''}"
            )
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
                    self._stick_deflection["x"], self._stick_deflection["y"]
                )
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
        from scripts.gamepad_control import eject_tip_in_place, pickup_tip_in_place

        try:
            (pickup_tip_in_place if action == "pickup" else eject_tip_in_place)(
                self.robot, self.jog.side
            )
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

    def _on_gamepad_connected(self, connected: bool, name: str = "") -> None:
        if connected:
            _set_pill_class(self.status_pill, "pill-live")
            self.status_pill.setText(name or "pad connected")
            self.status_pill.setToolTip(name)
            self.status_pill_icon.setPixmap(
                icon_utils.icon("controller_connect", _SUCCESS, size=14).pixmap(_ICON_SIZE)
            )
        else:
            _set_pill_class(self.status_pill, "pill-warn")
            self.status_pill.setText("no gamepad")
            self.status_pill.setToolTip("")
            self.status_pill_icon.setPixmap(
                icon_utils.icon("gamepad", _MUTED, size=14).pixmap(_ICON_SIZE)
            )

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
        self.gamepad.button_highlight_changed.connect(self._controller_stage.set_button_pressed)
        self.gamepad.trigger_changed.connect(self._controller_stage.set_trigger_level)
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
        self._controller_stage.clear_live_state()

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
            self.jog.end_jog()  # every axis at once -- see JogController.end_jog
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
