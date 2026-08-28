from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..deck import (
    BottomShape,
    ReservoirDefinition,
    TipRackDefinition,
    WellPlateDefinition,
    WellShape,
)
from ..geometry.coordinates import DeckPoint

_KINDS = ("well plate", "reservoir", "tip rack")


class LabwareDialog(QDialog):
    def __init__(self, slot, parent=None):
        super().__init__(parent)
        self.definition = None
        self.setWindowTitle(f"Labware — slot {slot.name}")
        self.resize(440, 520)

        root = QVBoxLayout(self)
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(_KINDS)
        root.addWidget(self.kind_combo)

        common = QWidget()
        cf = QFormLayout(common)
        sw, sh = slot.size if (slot.size and slot.size[0]) else (85.0, 128.0)
        self.identifier = QLineEdit("labware1")
        self.footprint_x = QDoubleSpinBox()
        self.footprint_x.setRange(1, 1000)
        self.footprint_x.setValue(sw)
        self.footprint_y = QDoubleSpinBox()
        self.footprint_y.setRange(1, 1000)
        self.footprint_y.setValue(sh)
        self.height = QDoubleSpinBox()
        self.height.setRange(0, 500)
        self.height.setValue(14.4)
        self.rows = QSpinBox()
        self.rows.setRange(1, 64)
        self.rows.setValue(8)
        self.cols = QSpinBox()
        self.cols.setRange(1, 64)
        self.cols.setValue(12)
        self.row_spacing = QDoubleSpinBox()
        self.row_spacing.setRange(0.1, 500)
        self.row_spacing.setValue(9.0)
        self.col_spacing = QDoubleSpinBox()
        self.col_spacing.setRange(0.1, 500)
        self.col_spacing.setValue(9.0)
        self.origin_x = QDoubleSpinBox()
        self.origin_x.setRange(-500, 500)
        self.origin_x.setValue(14.4)
        self.origin_y = QDoubleSpinBox()
        self.origin_y.setRange(-500, 500)
        self.origin_y.setValue(11.2)
        self.origin_z = QDoubleSpinBox()
        self.origin_z.setRange(-500, 500)
        self.origin_z.setValue(14.4)
        cf.addRow("name", self.identifier)
        cf.addRow("footprint x (mm)", self.footprint_x)
        cf.addRow("footprint y (mm)", self.footprint_y)
        cf.addRow("height (mm)", self.height)
        cf.addRow("rows", self.rows)
        cf.addRow("cols", self.cols)
        cf.addRow("row spacing (mm)", self.row_spacing)
        cf.addRow("col spacing (mm)", self.col_spacing)
        cf.addRow("A1 offset x, from left (mm)", self.origin_x)
        cf.addRow("A1 offset y, from top (mm)", self.origin_y)
        cf.addRow("A1 offset / top z (mm)", self.origin_z)
        root.addWidget(common)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self.well_page = QWidget()
        wf = QFormLayout(self.well_page)
        self.well_shape = QComboBox()
        self.well_shape.addItems(["circular", "rectangular"])
        self.well_diameter = QDoubleSpinBox()
        self.well_diameter.setRange(0, 200)
        self.well_diameter.setValue(6.9)
        self.well_width = QDoubleSpinBox()
        self.well_width.setRange(0, 200)
        self.well_length = QDoubleSpinBox()
        self.well_length.setRange(0, 200)
        self.well_depth = QDoubleSpinBox()
        self.well_depth.setRange(0, 200)
        self.well_depth.setValue(10.9)
        self.well_bottom = QComboBox()
        self.well_bottom.addItems(["flat", "round", "v"])
        self.well_bottom.setCurrentText("round")
        self.bottom_clearance = QDoubleSpinBox()
        self.bottom_clearance.setRange(0, 100)
        self.bottom_clearance.setValue(1.5)
        self.well_volume = QDoubleSpinBox()
        self.well_volume.setRange(0, 100000)
        self.well_volume.setValue(360)
        wf.addRow("well shape", self.well_shape)
        wf.addRow("well diameter (mm)", self.well_diameter)
        wf.addRow("well width (mm)", self.well_width)
        wf.addRow("well length (mm)", self.well_length)
        wf.addRow("well depth (mm)", self.well_depth)
        wf.addRow("well bottom", self.well_bottom)
        wf.addRow("bottom clearance (mm)", self.bottom_clearance)
        wf.addRow("max volume (µL)", self.well_volume)
        self.stack.addWidget(self.well_page)

        self.tip_page = QWidget()
        tf = QFormLayout(self.tip_page)
        self.tip_length = QDoubleSpinBox()
        self.tip_length.setRange(0, 200)
        self.tip_length.setValue(51.7)
        self.tip_volume = QDoubleSpinBox()
        self.tip_volume.setRange(0, 10000)
        self.tip_volume.setValue(300)
        tf.addRow("tip length (mm)", self.tip_length)
        tf.addRow("tip volume (µL)", self.tip_volume)
        self.stack.addWidget(self.tip_page)

        self.kind_combo.currentIndexChanged.connect(
            lambda i: self.stack.setCurrentIndex(1 if i == 2 else 0)
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_accept(self) -> None:
        kind = self.kind_combo.currentText()
        common_kwargs = dict(
            identifier=self.identifier.text().strip() or "labware",
            footprint_mm=(self.footprint_x.value(), self.footprint_y.value()),
            height_mm=self.height.value(),
            rows=self.rows.value(),
            cols=self.cols.value(),
            row_spacing_mm=self.row_spacing.value(),
            col_spacing_mm=self.col_spacing.value(),
            grid_offset=DeckPoint(
                self.origin_x.value(), self.origin_y.value(), self.origin_z.value()
            ),
        )
        try:
            if kind == "tip rack":
                self.definition = TipRackDefinition(
                    **common_kwargs,
                    tip_volume_ul=self.tip_volume.value(),
                    tip_length_mm=self.tip_length.value(),
                )
            else:
                cls = ReservoirDefinition if kind == "reservoir" else WellPlateDefinition
                self.definition = cls(
                    **common_kwargs,
                    well_volume_ul=self.well_volume.value(),
                    well_shape=WellShape(self.well_shape.currentText()),
                    well_diameter_mm=self.well_diameter.value(),
                    well_width_mm=self.well_width.value(),
                    well_length_mm=self.well_length.value(),
                    well_depth_mm=self.well_depth.value(),
                    well_bottom=BottomShape(self.well_bottom.currentText()),
                    bottom_clearance_mm=self.bottom_clearance.value(),
                )
        except Exception as exc:
            QMessageBox.warning(self, "Invalid labware", str(exc))
            return
        self.accept()
