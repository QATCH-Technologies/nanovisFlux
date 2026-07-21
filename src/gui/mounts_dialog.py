"""Lets an operator attach/detach tools on each mount without editing a YAML
config -- useful when connecting bare (no config loaded) or swapping a tool
mid-session."""
from __future__ import annotations

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit,
                             QDoubleSpinBox, QPushButton, QGroupBox, QDialogButtonBox,
                             QStackedWidget, QWidget)

from ..core import MountSide
from ..tools import Pipette, PlungerModel, UltrasonicSensor, TouchProbe

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
        self.stack.addWidget(QWidget())   # "none"

        self.pipette_page = QWidget()
        pf = QFormLayout(self.pipette_page)
        self.p_name = QLineEdit("p300")
        self.p_msteps_per_ul = QDoubleSpinBox()
        self.p_msteps_per_ul.setRange(0.01, 10000)
        self.p_msteps_per_ul.setValue(50)
        self.p_max_volume = QDoubleSpinBox()
        self.p_max_volume.setRange(1, 10000)
        self.p_max_volume.setValue(300)
        pf.addRow("name", self.p_name)
        pf.addRow("microsteps / µL", self.p_msteps_per_ul)
        pf.addRow("max volume (µL)", self.p_max_volume)
        self.stack.addWidget(self.pipette_page)

        self.ultrasonic_page = QWidget()
        uf = QFormLayout(self.ultrasonic_page)
        self.u_off_x = QDoubleSpinBox(); self.u_off_x.setRange(-1000, 1000)
        self.u_off_y = QDoubleSpinBox(); self.u_off_y.setRange(-1000, 1000); self.u_off_y.setValue(-40)
        self.u_off_z = QDoubleSpinBox(); self.u_off_z.setRange(-1000, 1000); self.u_off_z.setValue(130)
        self.u_range = QDoubleSpinBox(); self.u_range.setRange(1, 20000); self.u_range.setValue(4000)
        uf.addRow("offset x (mm)", self.u_off_x)
        uf.addRow("offset y (mm)", self.u_off_y)
        uf.addRow("offset z (mm)", self.u_off_z)
        uf.addRow("max range (mm)", self.u_range)
        self.stack.addWidget(self.ultrasonic_page)

        self.stack.addWidget(QWidget())   # "touch probe" -- no parameters

        self.kind_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)

        tool = robot.mounts[side].tool if robot is not None else None
        if isinstance(tool, Pipette):
            self.kind_combo.setCurrentText("pipette")
            self.p_name.setText(tool.name)
            self.p_msteps_per_ul.setValue(tool.plunger.microsteps_per_ul)
            self.p_max_volume.setValue(tool.max_volume_ul)
        elif isinstance(tool, UltrasonicSensor):
            self.kind_combo.setCurrentText("ultrasonic")
            ox, oy, oz = tool.offset_mm
            self.u_off_x.setValue(ox)
            self.u_off_y.setValue(oy)
            self.u_off_z.setValue(oz)
            self.u_range.setValue(tool.max_range_mm)
        elif isinstance(tool, TouchProbe):
            self.kind_combo.setCurrentText("touch probe")
        else:
            self.kind_combo.setCurrentText("none")
        self.stack.setCurrentIndex(self.kind_combo.currentIndex())

    def build_tool(self):
        kind = self.kind_combo.currentText()
        if kind == "pipette":
            return Pipette(name=self.p_name.text().strip() or "pipette",
                           plunger=PlungerModel(microsteps_per_ul=self.p_msteps_per_ul.value()),
                           max_volume_ul=self.p_max_volume.value())
        if kind == "ultrasonic":
            return UltrasonicSensor(offset_mm=(self.u_off_x.value(), self.u_off_y.value(), self.u_off_z.value()),
                                    max_range_mm=self.u_range.value())
        if kind == "touch probe":
            return TouchProbe()
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
