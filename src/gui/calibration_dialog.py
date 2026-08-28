from __future__ import annotations

import math

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config.loader import calibration_sidecar_path
from ..core import AxisId, MountSide
from ..geometry import (
    MICROSTEPS_PER_STEP,
    AffineTransform2D,
    AxisScale,
    DeckCalibration,
)
from ..motion.mounts import MOUNT_OFFSET_MM

_REF_MOUNT_CHOICES = (MountSide.LEFT, MountSide.RIGHT, MountSide.REAR)
_MIN_CALIBRATION_POINTS = 3


def _mark_sort_key(name: str):
    try:
        return (0, int(name))
    except ValueError:
        return (1, name)


class CalibrationDialog(QDialog):
    def __init__(self, robot, jog=None, parent=None, config_path: str | None = None):
        super().__init__(parent)
        self.robot = robot
        self.config_path = config_path
        self.setWindowTitle("Calibrate Deck")
        self.resize(680, 620)

        root = QVBoxLayout(self)

        ref_row = QHBoxLayout()
        ref_row.addWidget(
            QLabel("Reference mount (the one you're jogging to touch each point below):")
        )
        self.ref_mount_combo = QComboBox()
        self.ref_mount_combo.addItems([s.value for s in _REF_MOUNT_CHOICES])
        default_side = jog.side if jog is not None else MountSide.LEFT
        self.ref_mount_combo.setCurrentText(default_side.value)
        ref_row.addWidget(self.ref_mount_combo)
        ref_row.addStretch(1)
        root.addLayout(ref_row)

        xy_group = QGroupBox(
            f"XY calibration — select {_MIN_CALIBRATION_POINTS}+ deck reference marks"
        )
        xy_outer = QVBoxLayout(xy_group)

        self._mark_rows = []
        marks = getattr(robot.deck, "calibration_marks", None) if robot.deck is not None else None
        if not marks:
            xy_outer.addWidget(
                QLabel(
                    "no calibration marks configured on this deck "
                    "(see deck.calibration_marks in the robot config)"
                )
            )
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll_body = QWidget()
            rows_layout = QVBoxLayout(scroll_body)
            for mark in sorted(marks.values(), key=lambda m: _mark_sort_key(m.name)):
                rows_layout.addLayout(self._make_mark_row(mark))
            rows_layout.addStretch(1)
            scroll.setWidget(scroll_body)
            xy_outer.addWidget(scroll)
        root.addWidget(xy_group, 1)

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

        note_text = (
            "Jog the reference mount's tip (or a dedicated calibration probe) down onto a "
            "known-flat reference surface before capturing its Z touch-off. For XY, jog the "
            "same mount to touch each mark you want to use, capture its motor position, and "
            "make sure its checkbox is ticked -- at least 3 captured, checked points are "
            'required before you can apply or save. "Apply" only affects this session; '
            '"Save calibration..." persists it'
        )
        note_text += (
            f" to {calibration_sidecar_path(self.config_path).name} next to the loaded "
            "config, so it's picked up automatically the next time you connect with it."
            if self.config_path
            else " to a file -- connect with a config to have it picked up automatically next time."
        )
        note = QLabel(note_text)
        note.setWordWrap(True)
        note.setProperty("class", "eyebrow")
        root.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        save_btn = buttons.addButton("Save calibration…", QDialogButtonBox.ActionRole)
        save_btn.clicked.connect(self._save_to_file)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _make_mark_row(self, mark) -> QHBoxLayout:
        row = QHBoxLayout()
        corner_label = mark.corner.value.replace("_", "-")
        checkbox = QCheckBox(f"Slot {mark.slot} ({corner_label})")
        checkbox.setChecked(True)
        nominal = QLabel(f"deck ({mark.point.x:g}, {mark.point.y:g}) mm")
        nominal.setProperty("class", "mono")
        captured_label = QLabel("not captured")
        captured_label.setProperty("class", "mono")
        btn = QPushButton("Capture motor XY")
        state = {"motor": None}

        def capture():
            pos = self.robot.controller.report_position()
            mx, my = pos.get(AxisId.X), pos.get(AxisId.Y)
            if mx is None or my is None:
                captured_label.setText("no position (home first)")
                return
            state["motor"] = (mx, my)
            captured_label.setText(f"X{mx} Y{my}")

        btn.clicked.connect(capture)
        row.addWidget(checkbox)
        row.addWidget(nominal)
        row.addWidget(btn)
        row.addWidget(captured_label, 1)
        self._mark_rows.append({"mark": mark, "checkbox": checkbox, "state": state})
        return row

    def _reference_points(self):
        if not self._mark_rows:
            QMessageBox.warning(
                self, "No calibration marks", "this deck has no calibration_marks configured"
            )
            return None, None

        side = MountSide(self.ref_mount_combo.currentText())
        ox, oy = MOUNT_OFFSET_MM[side]
        checked = [r for r in self._mark_rows if r["checkbox"].isChecked()]
        missing = [r["mark"].name for r in checked if r["state"]["motor"] is None]
        if missing:
            QMessageBox.warning(self, "Incomplete", "capture motor XY for: " + ", ".join(missing))
            return None, None
        if len(checked) < _MIN_CALIBRATION_POINTS:
            QMessageBox.warning(
                self,
                "Not enough points",
                f"select at least {_MIN_CALIBRATION_POINTS} calibration marks "
                f"({len(checked)} checked)",
            )
            return None, None

        deck_pts = [(r["mark"].point.x - ox, r["mark"].point.y - oy) for r in checked]
        motor_pts = [r["state"]["motor"] for r in checked]
        return deck_pts, motor_pts

    def _z_zero_microsteps(self) -> dict:
        z_scale = AxisScale(steps_per_mm=self.z_steps_per_mm.value())
        return {
            side: int(z_scale.to_microsteps(state["tip_length"]) + state["contact"])
            for side, state in self._z_zero.items()
            if state["contact"] is not None
        }

    def _fit_residual_report(self, xy: AffineTransform2D, deck_pts, motor_pts) -> str:
        inv = xy.inverse()
        errors = [
            math.hypot(*(a - b for a, b in zip(inv.apply(*motor), deck)))
            for deck, motor in zip(deck_pts, motor_pts)
        ]
        rms = math.sqrt(sum(e * e for e in errors) / len(errors))
        return f"fit residual: {rms:.2f} mm RMS, {max(errors):.2f} mm worst-case, {len(errors)} point(s)"

    def _scale_sanity_check(self, xy: AffineTransform2D) -> str | None:
        x_axis, y_axis = self.robot.axes.get(AxisId.X), self.robot.axes.get(AxisId.Y)
        if x_axis is None or y_axis is None:
            return None
        axis_x_scale = x_axis.config.steps_per_mm
        axis_y_scale = y_axis.config.steps_per_mm
        if not axis_x_scale or not axis_y_scale:
            return None
        fit_x = math.hypot(xy.a, xy.c) / MICROSTEPS_PER_STEP
        fit_y = math.hypot(xy.b, xy.d) / MICROSTEPS_PER_STEP
        dx_pct = (fit_x / axis_x_scale - 1) * 100
        dy_pct = (fit_y / axis_y_scale - 1) * 100
        if abs(dx_pct) < 2 and abs(dy_pct) < 2:
            return None
        return (
            f"note: this fit implies {fit_x:.2f}/{fit_y:.2f} steps/mm (X/Y) vs. the axis "
            f"config's {axis_x_scale:.2f}/{axis_y_scale:.2f} ({dx_pct:+.1f}% / {dy_pct:+.1f}%). "
            "A consistent mismatch on both axes usually means the calibration marks' assumed "
            "deck geometry (deck.calibration_marks / deck.slots in the robot config) doesn't "
            "match the physical deck -- verify the marks' real positions with calipers, or "
            "recalibrate with more/further-spread marks."
        )

    def _apply(self) -> None:
        deck_pts, motor_pts = self._reference_points()
        if deck_pts is None:
            return
        try:
            xy = AffineTransform2D.from_point_pairs(deck_pts, motor_pts)
        except ValueError as exc:
            QMessageBox.warning(self, "Calibration failed", str(exc))
            return

        z_scale = AxisScale(steps_per_mm=self.z_steps_per_mm.value())
        self.robot.calibration = DeckCalibration(
            xy=xy, z_scale=z_scale, z_zero=self._z_zero_microsteps()
        )

        lines = [
            "Deck calibration updated for this session.",
            "",
            self._fit_residual_report(xy, deck_pts, motor_pts),
        ]
        scale_note = self._scale_sanity_check(xy)
        if scale_note:
            lines += ["", scale_note]
        QMessageBox.information(self, "Calibration applied", "\n".join(lines))

    def _save_to_file(self) -> None:
        deck_pts, motor_pts = self._reference_points()
        if deck_pts is None:
            return
        default_path = (
            str(calibration_sidecar_path(self.config_path))
            if self.config_path
            else "calibration.yaml"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Save calibration", default_path, "YAML files (*.yaml *.yml)"
        )
        if not path:
            return
        data = {
            "calibration": {
                "points": {
                    "deck": [{"x": x, "y": y} for x, y in deck_pts],
                    "motor": [list(m) for m in motor_pts],
                },
                "z_scale": {"steps_per_mm": self.z_steps_per_mm.value()},
                "z_zero": {
                    side.value: msteps for side, msteps in self._z_zero_microsteps().items()
                },
            }
        }
        try:
            import yaml

            with open(path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, sort_keys=False)
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        from pathlib import Path

        is_sidecar = self.config_path is not None and Path(path) == calibration_sidecar_path(
            self.config_path
        )
        detail = (
            "It will be picked up automatically next time you connect with this config."
            if is_sidecar
            else "Load it later via the connection bar's config path field, or move/rename it to "
            f"{calibration_sidecar_path(self.config_path).name if self.config_path else '<config>.calibration.yaml'} "
            "next to your robot config to have it load automatically."
        )
        QMessageBox.information(self, "Calibration saved", f"Wrote {path}\n\n{detail}")
