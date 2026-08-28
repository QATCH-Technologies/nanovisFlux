from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from . import icon_utils
from . import style as S
from .tokens import TOKENS

_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent.parent / "configs" / "robot.yaml"
_ICON_SIZE = QSize(16, 16)
_INK = QColor(*TOKENS["flat_text"][:3])
_ON_ACCENT = QColor(*TOKENS["flat_on_accent"][:3])

_STATUS_COLORS = {
    "disconnected": S.INK_MUTED,
    "connecting": S.ACCENT_AMBER,
    "connected": S.ACCENT_GREEN,
    "error": S.ACCENT_RED,
}


class ConnectionBar(QWidget):
    connect_requested = pyqtSignal(dict)
    disconnect_requested = pyqtSignal()
    home_requested = pyqtSignal()
    estop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(10)

        brand = QLabel("nanovisFlux")
        brand.setProperty("class", "h1")
        outer.addWidget(brand)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {_STATUS_COLORS['disconnected']}; font-size: 14px;")
        self.status_text = QLabel("not connected")
        outer.addWidget(self.status_dot)
        outer.addWidget(self.status_text)

        outer.addWidget(self._vline())

        self.btn_sim = QPushButton("Simulated")
        self.btn_real = QPushButton("Real port")
        for b in (self.btn_sim, self.btn_real):
            b.setCheckable(True)
        self.btn_sim.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.btn_sim)
        mode_group.addButton(self.btn_real)
        self.btn_sim.clicked.connect(lambda: self._set_mode("sim"))
        self.btn_real.clicked.connect(lambda: self._set_mode("real"))
        outer.addWidget(self.btn_sim)
        outer.addWidget(self.btn_real)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(90)
        self.btn_refresh = QPushButton()
        self.btn_refresh.setIcon(icon_utils.icon("restart_circle", _INK, size=16))
        self.btn_refresh.setIconSize(_ICON_SIZE)
        self.btn_refresh.setFixedWidth(28)
        self.btn_refresh.setToolTip("rescan serial ports")
        self.btn_refresh.clicked.connect(self._refresh_ports)
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 2_000_000)
        self.baud_spin.setValue(115200)
        self.baud_spin.setSingleStep(100)
        outer.addWidget(self.port_combo)
        outer.addWidget(self.btn_refresh)
        outer.addWidget(self.baud_spin)

        outer.addWidget(self._vline())

        self.config_check = QCheckBox("config")
        self.config_check.setChecked(_DEFAULT_CONFIG.exists())
        self.config_edit = QLineEdit(str(_DEFAULT_CONFIG) if _DEFAULT_CONFIG.exists() else "")
        self.config_edit.setPlaceholderText("robot.yaml (deck / calibration / mounts)")
        self.config_edit.setMinimumWidth(160)
        self.btn_browse = QPushButton("…")
        self.btn_browse.setFixedWidth(24)
        self.btn_browse.clicked.connect(self._browse_config)
        outer.addWidget(self.config_check)
        outer.addWidget(self.config_edit, 1)
        outer.addWidget(self.btn_browse)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("primary")
        self.btn_connect.setIcon(icon_utils.icon("usb", _ON_ACCENT, size=16))
        self.btn_connect.setIconSize(_ICON_SIZE)
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        outer.addWidget(self.btn_connect)

        outer.addWidget(self._vline())

        self.btn_home = QPushButton("Home")
        self.btn_home.setIcon(icon_utils.icon("home", _INK, size=16))
        self.btn_home.setIconSize(_ICON_SIZE)
        self.btn_home.setEnabled(False)
        self.btn_home.clicked.connect(self.home_requested.emit)
        outer.addWidget(self.btn_home)

        self.btn_estop = QPushButton("E-STOP")
        self.btn_estop.setObjectName("estop")
        self.btn_estop.setIcon(icon_utils.icon("power", _ON_ACCENT, size=16))
        self.btn_estop.setIconSize(_ICON_SIZE)
        self.btn_estop.setEnabled(False)
        self.btn_estop.clicked.connect(self.estop_requested.emit)
        outer.addWidget(self.btn_estop)

        self._refresh_ports()
        self._set_mode("sim")

    def _vline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Plain)
        return line

    def _set_mode(self, mode: str) -> None:
        real = mode == "real"
        self.port_combo.setEnabled(real)
        self.btn_refresh.setEnabled(real)
        self.baud_spin.setEnabled(real)

    def _refresh_ports(self) -> None:
        try:
            from serial.tools import list_ports

            ports = [p.device for p in list_ports.comports()]
        except Exception:
            ports = []
        current = self.port_combo.currentText()
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current:
            self.port_combo.setEditText(current)

    def _browse_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Robot config", str(_DEFAULT_CONFIG.parent), "YAML files (*.yaml *.yml)"
        )
        if path:
            self.config_edit.setText(path)
            self.config_check.setChecked(True)

    def _on_connect_clicked(self) -> None:
        if self.btn_connect.text() == "Disconnect":
            self.disconnect_requested.emit()
            return
        mode = "real" if self.btn_real.isChecked() else "sim"
        self.connect_requested.emit(
            {
                "mode": mode,
                "port": self.port_combo.currentText().strip(),
                "baud": self.baud_spin.value(),
                "config_path": (
                    self.config_edit.text().strip() if self.config_check.isChecked() else None
                ),
            }
        )

    def set_status(self, state: str, message: str = "") -> None:
        color = _STATUS_COLORS.get(state, _STATUS_COLORS["disconnected"])
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        labels = {
            "disconnected": "not connected",
            "connecting": "connecting…",
            "connected": "connected",
            "error": "connection error",
        }
        self.status_text.setText(message or labels.get(state, state))

        connected = state == "connected"
        self.btn_connect.setText("Disconnect" if connected else "Connect")
        self.btn_connect.setEnabled(state != "connecting")
        for w in (
            self.btn_sim,
            self.btn_real,
            self.port_combo,
            self.baud_spin,
            self.btn_refresh,
            self.config_check,
            self.config_edit,
            self.btn_browse,
        ):
            w.setEnabled(
                (not connected)
                and state != "connecting"
                and (
                    w not in (self.port_combo, self.btn_refresh, self.baud_spin)
                    or self.btn_real.isChecked()
                )
            )
        self.btn_home.setEnabled(connected)
        self.btn_estop.setEnabled(connected)
