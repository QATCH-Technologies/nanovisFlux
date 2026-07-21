"""Calibration wizard.

Three deck/motor XY point pairs -- each captured by jogging to a physical
reference point and reading back the controller's position -- build the
deck<->motor affine transform (see geometry.transform.AffineTransform2D).
A per-mount Z touch-off (jog the tip down onto a known-flat surface, then
capture) finds that mount's nozzle-reference z_zero the same way
JogController.capture_z_zero / DeckCalibration.touch_off_z_zero do, just
walked through explicitly here since there may be no calibration yet for
those to build on.
"""
from __future__ import annotations

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                             QDoubleSpinBox, QPushButton, QGroupBox, QDialogButtonBox, QMessageBox)

from ..core import AxisId, MountSide
from ..geometry import AffineTransform2D, AxisScale, DeckCalibration


class CalibrationDialog(QDialog):
    def __init__(self, robot, parent=None):
        super().__init__(parent)
        self.robot = robot
        self.setWindowTitle("Calibrate Deck")
        self.resize(560, 440)

        root = QVBoxLayout(self)

        xy_group = QGroupBox("XY calibration — 3 deck / motor point pairs")
        xy_layout = QVBoxLayout(xy_group)
        self._points = []
        for i in range(3):
            row = QHBoxLayout()
            deck_x = QDoubleSpinBox()
            deck_x.setRange(-2000, 2000)
            deck_x.setSuffix(" mm")
            deck_y = QDoubleSpinBox()
            deck_y.setRange(-2000, 2000)
            deck_y.setSuffix(" mm")
            captured_label = QLabel("not captured")
            captured_label.setProperty("class", "mono")
            btn = QPushButton("Capture motor XY")
            state = {"motor": None}

            def make_capture(state=state, label=captured_label):
                def capture():
                    pos = self.robot.controller.report_position()
                    mx, my = pos.get(AxisId.X), pos.get(AxisId.Y)
                    if mx is None or my is None:
                        label.setText("no position (home first)")
                        return
                    state["motor"] = (mx, my)
                    label.setText(f"X{mx} Y{my}")
                return capture

            btn.clicked.connect(make_capture())
            row.addWidget(QLabel(f"{i + 1}. deck"))
            row.addWidget(deck_x)
            row.addWidget(deck_y)
            row.addWidget(btn)
            row.addWidget(captured_label)
            xy_layout.addLayout(row)
            self._points.append({"deck_x": deck_x, "deck_y": deck_y, "state": state})
        root.addWidget(xy_group)

        z_group = QGroupBox("Z calibration")
        z_layout = QFormLayout(z_group)
        self.z_steps_per_mm = QDoubleSpinBox()
        self.z_steps_per_mm.setRange(0.1, 1000)
        self.z_steps_per_mm.setDecimals(2)
        self.z_steps_per_mm.setValue(25.0)
        z_layout.addRow("steps per mm", self.z_steps_per_mm)

        self._z_zero = {}
        for side in (MountSide.LEFT, MountSide.RIGHT):
            row = QHBoxLayout()
            label = QLabel("not captured")
            label.setProperty("class", "mono")
            btn = QPushButton("Capture from current position")
            state = {"contact": None, "tip_length": 0.0}

            def make_zcapture(side=side, state=state, label=label):
                def capture():
                    vertical = AxisId.Z if side is MountSide.LEFT else AxisId.A
                    pos = self.robot.controller.report_position()
                    contact = pos.get(vertical)
                    if contact is None:
                        label.setText("no position (home first)")
                        return
                    tip_length = self.robot.tip_offset(side)
                    state["contact"], state["tip_length"] = contact, tip_length
                    label.setText(f"contact {contact}  (tip {tip_length:.1f} mm)")
                return capture

            btn.clicked.connect(make_zcapture())
            row.addWidget(btn)
            row.addWidget(label)
            z_layout.addRow(f"{side.value} touch-off", row)
            self._z_zero[side] = state
        root.addWidget(z_group)

        note = QLabel("Jog the active mount's tip (or a dedicated calibration probe) down onto a "
                      "known-flat reference surface before capturing its Z touch-off.")
        note.setWordWrap(True)
        note.setProperty("class", "eyebrow")
        root.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _apply(self) -> None:
        deck_pts, motor_pts = [], []
        for p in self._points:
            if p["state"]["motor"] is None:
                QMessageBox.warning(self, "Incomplete", "capture all three point pairs first")
                return
            deck_pts.append((p["deck_x"].value(), p["deck_y"].value()))
            motor_pts.append(p["state"]["motor"])
        try:
            xy = AffineTransform2D.from_point_pairs(deck_pts, motor_pts)
        except ValueError as exc:
            QMessageBox.warning(self, "Calibration failed", str(exc))
            return

        z_scale = AxisScale(steps_per_mm=self.z_steps_per_mm.value())
        z_zero = {}
        for side, state in self._z_zero.items():
            if state["contact"] is not None:
                z_zero[side] = z_scale.to_microsteps(state["tip_length"]) + state["contact"]

        self.robot.calibration = DeckCalibration(xy=xy, z_scale=z_scale, z_zero=z_zero)
        QMessageBox.information(self, "Calibration applied", "Deck calibration updated for this session.")
