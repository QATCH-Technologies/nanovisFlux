"""Calibration wizard.

The deck<->motor XY affine (see geometry.transform.AffineTransform2D) is
fit from a set of fixed, physically-marked reference points
(``robot.deck.calibration_marks`` -- see config/robot.example.yaml's
``deck.calibration_marks`` comment and deck.deck.inset_corner_point): jog a
chosen *reference mount* to touch each mark you want to use, capture, check
its box, repeat for at least 3 (up to however many marks the deck has), then
fit. Unlike the old free-typed-deck-mm convention, every mark's nominal
deck (x, y) is fixed and known ahead of time -- the operator only supplies
the motor position found there.

Whichever mount is actually touching each point (the "reference mount")
almost never sits exactly on the gantry's own shared X/Y reference point --
see motion.mounts.MOUNT_OFFSET_MM -- so each captured deck point is shifted
by that mount's known offset before fitting, exactly mirroring the math
DeckCalibration.deck_to_motor uses at move time (see its _reference_xy
docstring). Get this step wrong and every subsequent RIGHT-mount move would
be off by the mount spacing again.

A per-mount Z touch-off (jog the tip down onto a known-flat surface, then
capture) finds that mount's nozzle-reference z_zero the same way
JogController.capture_z_zero / DeckCalibration.touch_off_z_zero do, just
walked through explicitly here since there may be no calibration yet for
those to build on.
"""
from __future__ import annotations

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                             QDoubleSpinBox, QPushButton, QGroupBox, QComboBox, QCheckBox,
                             QScrollArea, QWidget, QDialogButtonBox, QMessageBox, QFileDialog)

from ..core import AxisId, MountSide
from ..geometry import AffineTransform2D, AxisScale, DeckCalibration
from ..motion.mounts import MOUNT_OFFSET_MM

_REF_MOUNT_CHOICES = (MountSide.LEFT, MountSide.RIGHT, MountSide.REAR)
_MIN_CALIBRATION_POINTS = 3


def _mark_sort_key(name: str):
    """Numeric marks (slot names like "1", "10") sort in slot order rather
    than lexicographic ("1", "10", "3", ...); anything non-numeric falls
    back to plain string order after all the numeric ones."""
    try:
        return (0, int(name))
    except ValueError:
        return (1, name)


class CalibrationDialog(QDialog):
    def __init__(self, robot, jog=None, parent=None):
        super().__init__(parent)
        self.robot = robot
        self.setWindowTitle("Calibrate Deck")
        self.resize(680, 620)

        root = QVBoxLayout(self)

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Reference mount (the one you're jogging to touch each point below):"))
        self.ref_mount_combo = QComboBox()
        self.ref_mount_combo.addItems([s.value for s in _REF_MOUNT_CHOICES])
        default_side = jog.side if jog is not None else MountSide.LEFT
        self.ref_mount_combo.setCurrentText(default_side.value)
        ref_row.addWidget(self.ref_mount_combo)
        ref_row.addStretch(1)
        root.addLayout(ref_row)

        xy_group = QGroupBox(f"XY calibration — select {_MIN_CALIBRATION_POINTS}+ deck reference marks")
        xy_outer = QVBoxLayout(xy_group)

        self._mark_rows = []
        marks = getattr(robot.deck, "calibration_marks", None) if robot.deck is not None else None
        if not marks:
            xy_outer.addWidget(QLabel("no calibration marks configured on this deck "
                                      "(see deck.calibration_marks in the robot config)"))
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

        note = QLabel("Jog the reference mount's tip (or a dedicated calibration probe) down onto a "
                      "known-flat reference surface before capturing its Z touch-off. For XY, jog the "
                      "same mount to touch each mark you want to use, capture its motor position, and "
                      "make sure its checkbox is ticked -- at least 3 captured, checked points are "
                      "required before you can apply or save.")
        note.setWordWrap(True)
        note.setProperty("class", "eyebrow")
        root.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        save_btn = buttons.addButton("Save calibration to file…", QDialogButtonBox.ActionRole)
        save_btn.clicked.connect(self._save_to_file)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # -- one row per configured calibration mark -------------------------
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

    # -- shared by Apply and Save-to-file --------------------------------
    def _reference_points(self):
        """(deck_pts, motor_pts) for the checked, captured marks, each deck
        point shifted from "where the reference mount touched" to "what the
        gantry's own shared reference point was" -- see
        DeckCalibration._reference_xy for the matching math this mirrors.
        Returns (None, None) (after warning the operator why) if fewer than
        _MIN_CALIBRATION_POINTS marks are checked-and-captured."""
        if not self._mark_rows:
            QMessageBox.warning(self, "No calibration marks",
                                "this deck has no calibration_marks configured")
            return None, None

        side = MountSide(self.ref_mount_combo.currentText())
        ox, oy = MOUNT_OFFSET_MM[side]
        checked = [r for r in self._mark_rows if r["checkbox"].isChecked()]
        missing = [r["mark"].name for r in checked if r["state"]["motor"] is None]
        if missing:
            QMessageBox.warning(self, "Incomplete",
                                "capture motor XY for: " + ", ".join(missing))
            return None, None
        if len(checked) < _MIN_CALIBRATION_POINTS:
            QMessageBox.warning(self, "Not enough points",
                                f"select at least {_MIN_CALIBRATION_POINTS} calibration marks "
                                f"({len(checked)} checked)")
            return None, None

        deck_pts = [(r["mark"].point.x - ox, r["mark"].point.y - oy) for r in checked]
        motor_pts = [r["state"]["motor"] for r in checked]
        return deck_pts, motor_pts

    def _z_zero_microsteps(self) -> dict:
        z_scale = AxisScale(steps_per_mm=self.z_steps_per_mm.value())
        return {side: int(z_scale.to_microsteps(state["tip_length"]) + state["contact"])
                for side, state in self._z_zero.items() if state["contact"] is not None}

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
        self.robot.calibration = DeckCalibration(xy=xy, z_scale=z_scale, z_zero=self._z_zero_microsteps())
        QMessageBox.information(self, "Calibration applied", "Deck calibration updated for this session.")

    def _save_to_file(self) -> None:
        deck_pts, motor_pts = self._reference_points()
        if deck_pts is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save calibration", "calibration.yaml",
                                              "YAML files (*.yaml *.yml)")
        if not path:
            return
        data = {
            "calibration": {
                "points": {
                    "deck": [{"x": x, "y": y} for x, y in deck_pts],
                    "motor": [list(m) for m in motor_pts],
                },
                "z_scale": {"steps_per_mm": self.z_steps_per_mm.value()},
                "z_zero": {side.value: msteps for side, msteps in self._z_zero_microsteps().items()},
            }
        }
        try:
            import yaml  # lazy dependency, matches config/loader.py's own convention
            with open(path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, sort_keys=False)
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        QMessageBox.information(self, "Calibration saved", f"Wrote {path}\n\n"
                                "Load it later via the connection bar's config path field.")
