
from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import MountSide
from ..tools import Pipette, PlungerModel, TouchProbe, UltrasonicSensor

_TOOL_KINDS = ("none", "pipette", "ultrasonic", "touch probe")


class _MountEditor(QWidget):
    def __init__(self, side: MountSide, robot, parent=None):
        super().__init__(parent)
        self.side = side
        layout = QVBoxLayout(self)
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(_TOOL_KINDS)
        layout.addWidget(self.kind_combo)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.stack.addWidget(QWidget())

        self.pipette_page = QWidget()
        pf = QFormLayout(self.pipette_page)
        self.p_name = QLineEdit("p300")
        self.p_brand = QLineEdit()
        self.p_channels = QSpinBox()
        self.p_channels.setRange(1, 96)
        self.p_channels.setValue(1)
        self.p_msteps_per_ul = QDoubleSpinBox()
        self.p_msteps_per_ul.setRange(0.01, 10000)
        self.p_msteps_per_ul.setValue(50)
        self.p_max_volume = QDoubleSpinBox()
        self.p_max_volume.setRange(1, 10000)
        self.p_max_volume.setValue(300)
        pf.addRow("name", self.p_name)
        pf.addRow("brand", self.p_brand)
        pf.addRow("channels", self.p_channels)
        pf.addRow("microsteps / µL", self.p_msteps_per_ul)
        pf.addRow("max volume (µL)", self.p_max_volume)
        self.stack.addWidget(self.pipette_page)

        self.ultrasonic_page = QWidget()
        uf = QFormLayout(self.ultrasonic_page)
        self.u_name = QLineEdit("ultrasonic")
        self.u_brand = QLineEdit()
        self.u_range = QDoubleSpinBox()
        self.u_range.setRange(1, 20000)
        self.u_range.setValue(4000)
        uf.addRow("name", self.u_name)
        uf.addRow("brand", self.u_brand)
        uf.addRow("max range (mm)", self.u_range)
        self.stack.addWidget(self.ultrasonic_page)

        self.probe_page = QWidget()
        tpf = QFormLayout(self.probe_page)
        self.tp_name = QLineEdit("3d_touch_probe")
        self.tp_brand = QLineEdit()
        self.tp_length = QDoubleSpinBox()
        self.tp_length.setRange(0, 500)
        tpf.addRow("name", self.tp_name)
        tpf.addRow("brand", self.tp_brand)
        tpf.addRow("length (mm)", self.tp_length)
        self.stack.addWidget(self.probe_page)

        self.kind_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        tool = robot.mounts[side].tool if robot is not None else None
        if isinstance(tool, Pipette):
            self.kind_combo.setCurrentText("pipette")
            self.p_name.setText(tool.name)
            self.p_brand.setText(tool.brand)
            self.p_channels.setValue(tool.channels)
            self.p_msteps_per_ul.setValue(tool.plunger.microsteps_per_ul)
            self.p_max_volume.setValue(tool.max_volume_ul)
        elif isinstance(tool, UltrasonicSensor):
            self.kind_combo.setCurrentText("ultrasonic")
            self.u_name.setText(tool.name)
            self.u_brand.setText(tool.brand)
            self.u_range.setValue(tool.max_range_mm)
        elif isinstance(tool, TouchProbe):
            self.kind_combo.setCurrentText("touch probe")
            self.tp_name.setText(tool.name)
            self.tp_brand.setText(tool.brand)
            self.tp_length.setValue(tool.length_mm)
        else:
            self.kind_combo.setCurrentText("none")
        self.stack.setCurrentIndex(self.kind_combo.currentIndex())

    def build_tool(self):
        kind = self.kind_combo.currentText()
        if kind == "pipette":
            return Pipette(
                name=self.p_name.text().strip() or "pipette",
                plunger=PlungerModel(microsteps_per_ul=self.p_msteps_per_ul.value()),
                max_volume_ul=self.p_max_volume.value(),
                brand=self.p_brand.text().strip(),
                channels=self.p_channels.value(),
            )
        if kind == "ultrasonic":
            return UltrasonicSensor(
                max_range_mm=self.u_range.value(),
                name=self.u_name.text().strip() or "ultrasonic",
                brand=self.u_brand.text().strip(),
            )
        if kind == "touch probe":
            return TouchProbe(
                name=self.tp_name.text().strip() or "touch-probe",
                length_mm=self.tp_length.value(),
                brand=self.tp_brand.text().strip(),
            )
        return None


class MountsDialog(QDialog):
    def __init__(self, robot, parent=None):
        super().__init__(parent)
        self.robot = robot
        self.setWindowTitle("Configure Mounts")
        self.resize(440, 480)
        root = QVBoxLayout(self)
        self.editors = {}
        for side in (MountSide.LEFT, MountSide.RIGHT, MountSide.REAR):
            group = QGroupBox(f"{side.value} mount")
            gl = QVBoxLayout(group)
            editor = _MountEditor(side, robot)
            gl.addWidget(editor)
            root.addWidget(group)
            self.editors[side] = editor

        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _apply(self) -> None:
        for side, editor in self.editors.items():
            tool = editor.build_tool()
            self.robot.mounts[side].tool = None
            if tool is not None:
                self.robot.attach(side, tool)
        self.accept()
