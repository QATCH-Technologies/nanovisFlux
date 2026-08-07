"""Calibration wizard.

A deck origin plus two calibration points -- each captured by jogging a
chosen *reference mount* to a physical reference point and reading back the
controller's position -- build the deck<->motor affine transform (see
geometry.transform.AffineTransform2D). By convention (see
config/robot.example.yaml's calibration comment) the X calibration point
shares the origin's deck Y (it defines the X axis's direction/scale) and the
Y calibration point shares the origin's deck X (it defines the Y axis's).
The dialog keeps those two fields synced to the origin automatically, up
until an operator edits one directly -- after that it's a free 3-point fit,
same as before.

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
                             QDoubleSpinBox, QPushButton, QGroupBox, QComboBox,
                             QDialogButtonBox, QMessageBox, QFileDialog)

from ..core import AxisId, MountSide
from ..geometry import AffineTransform2D, AxisScale, DeckCalibration
from ..motion.mounts import MOUNT_OFFSET_MM

_REF_MOUNT_CHOICES = (MountSide.LEFT, MountSide.RIGHT, MountSide.REAR)


class CalibrationDialog(QDialog):
    def __init__(self, robot, jog=None, parent=None):
        super().__init__(parent)
        self.robot = robot
        self.setWindowTitle("Calibrate Deck")
        self.resize(640, 520)

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

        xy_group = QGroupBox("XY calibration — deck origin + two calibration points")
        xy_layout = QVBoxLayout(xy_group)

        def make_row(label_text: str):
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
            row.addWidget(QLabel(label_text))
            row.addWidget(deck_x)
            row.addWidget(deck_y)
            row.addWidget(btn)
            row.addWidget(captured_label)
            xy_layout.addLayout(row)
            return deck_x, deck_y, state

        self.origin_x, self.origin_y, self._origin_state = make_row("1. Deck origin")
        self.xpt_x, self.xpt_y, self._xpt_state = make_row("2. X calibration point")
        self.ypt_x, self.ypt_y, self._ypt_state = make_row("3. Y calibration point")
        root.addWidget(xy_group)

        # -- keep the X/Y calibration points' "shared" coordinate synced to
        # the origin (see class docstring) until the operator overrides it
        # directly -- a blockSignals()-guarded programmatic set never flips
        # the touched flag, only a genuine edit does.
        self._xpt_y_touched = False
        self._ypt_x_touched = False

        def sync_xpt_y():
            if not self._xpt_y_touched:
                self.xpt_y.blockSignals(True)
                self.xpt_y.setValue(self.origin_y.value())
                self.xpt_y.blockSignals(False)

        def sync_ypt_x():
            if not self._ypt_x_touched:
                self.ypt_x.blockSignals(True)
                self.ypt_x.setValue(self.origin_x.value())
                self.ypt_x.blockSignals(False)

        self.origin_y.valueChanged.connect(sync_xpt_y)
        self.origin_x.valueChanged.connect(sync_ypt_x)
        self.xpt_y.valueChanged.connect(lambda: setattr(self, "_xpt_y_touched", True))
        self.ypt_x.valueChanged.connect(lambda: setattr(self, "_ypt_x_touched", True))
        sync_xpt_y()
        sync_ypt_x()

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
                      "known-flat reference surface before capturing its Z touch-off. The X calibration "
                      "point's deck Y and the Y calibration point's deck X track the origin automatically "
                      "until you edit them yourself.")
        note.setWordWrap(True)
        note.setProperty("class", "eyebrow")
        root.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        save_btn = buttons.addButton("Save calibration to file…", QDialogButtonBox.ActionRole)
        save_btn.clicked.connect(self._save_to_file)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # -- shared by Apply and Save-to-file --------------------------------
    def _reference_points(self):
        """(deck_pts, motor_pts) for the 3 captured points, each deck point
        shifted from "where the reference mount touched" to "what the
        gantry's own shared reference point was" -- see
        DeckCalibration._reference_xy for the matching math this mirrors.
        Returns (None, None) if any point hasn't been captured yet."""
        side = MountSide(self.ref_mount_combo.currentText())
        ox, oy = MOUNT_OFFSET_MM[side]
        rows = ((self.origin_x, self.origin_y, self._origin_state),
                (self.xpt_x, self.xpt_y, self._xpt_state),
                (self.ypt_x, self.ypt_y, self._ypt_state))
        deck_pts, motor_pts = [], []
        for dx, dy, state in rows:
            if state["motor"] is None:
                return None, None
            deck_pts.append((dx.value() - ox, dy.value() - oy))
            motor_pts.append(state["motor"])
        return deck_pts, motor_pts

    def _z_zero_microsteps(self) -> dict:
        z_scale = AxisScale(steps_per_mm=self.z_steps_per_mm.value())
        return {side: int(z_scale.to_microsteps(state["tip_length"]) + state["contact"])
                for side, state in self._z_zero.items() if state["contact"] is not None}

    def _apply(self) -> None:
        deck_pts, motor_pts = self._reference_points()
        if deck_pts is None:
            QMessageBox.warning(self, "Incomplete", "capture all three point pairs first")
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
            QMessageBox.warning(self, "Incomplete", "capture all three point pairs first")
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
