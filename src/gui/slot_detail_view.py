from __future__ import annotations

import re

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..deck import WellShape
from . import icon_utils
from . import style as S
from .labware_dialog import LabwareDialog
from .tokens import TOKENS

_WELL_RE = re.compile(r"([A-Za-z]+)(\d+)")
_ICON_SIZE = QSize(16, 16)
_INK = QColor(*TOKENS["flat_text"][:3])


class LabwareCanvas(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 280)
        self.slot = None
        self.labware = None

    def set_content(self, slot, labware) -> None:
        self.slot = slot
        self.labware = labware
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(S.PANEL))
        if self.slot is None:
            return

        sw, sh = self.slot.size if (self.slot.size and self.slot.size[0]) else (100.0, 100.0)
        wells = list(self.labware.wells.items()) if self.labware is not None else []

        minx, miny, maxx, maxy = 0.0, 0.0, sw, sh

        pad = 36
        span_x, span_y = max(maxx - minx, 1e-6), max(maxy - miny, 1e-6)
        scale = min(
            max(self.width() - 2 * pad, 10) / span_x, max(self.height() - 2 * pad, 10) / span_y
        )
        cx0, cy0 = (minx + maxx) / 2, (miny + maxy) / 2

        def to_screen(x, y):
            return (self.width() / 2 + (x - cx0) * scale, self.height() / 2 - (y - cy0) * scale)

        pen = QPen(QColor(S.BORDER_STRONG))
        pen.setStyle(Qt.DashLine)
        pen.setWidthF(1.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        corners = [to_screen(0, 0), to_screen(sw, 0), to_screen(sw, sh), to_screen(0, sh)]
        path = QPainterPath()
        path.moveTo(*corners[0])
        for c in corners[1:]:
            path.lineTo(*c)
        path.closeSubpath()
        p.drawPath(path)

        if not wells:
            return

        p.setClipPath(path)

        p.setPen(QPen(QColor(S.INK_MUTED), 1))
        p.setBrush(QColor("#E4EEE7"))
        for _name, well in wells:
            geo = well.geometry
            cx, cy = to_screen(well.offset.x, well.offset.y)
            if geo.shape == WellShape.CIRCULAR:
                r = max((geo.diameter_mm / 2) * scale, 1.5)
                p.drawEllipse(QPointF(cx, cy), r, r)
            else:
                w_, l_ = max(geo.width_mm * scale, 3), max(geo.length_mm * scale, 3)
                p.drawRect(QRectF(cx - w_ / 2, cy - l_ / 2, w_, l_))

        p.setClipping(False)

        by_row, by_col = {}, {}
        for name, well in wells:
            m = _WELL_RE.match(name)
            if not m:
                continue
            row, col = m.group(1), m.group(2)
            if row not in by_row or well.offset.x < by_row[row].offset.x:
                by_row[row] = well
            if col not in by_col or well.offset.y < by_col[col].offset.y:
                by_col[col] = well

        p.setFont(QFont(S.UI_FONT, 8))
        p.setPen(QColor(S.INK_MUTED))
        for row, well in by_row.items():
            x, y = to_screen(well.offset.x, well.offset.y)
            p.drawText(int(x - 30), int(y - 8), 22, 16, Qt.AlignRight | Qt.AlignVCenter, row)
        for col, well in by_col.items():
            x, y = to_screen(well.offset.x, well.offset.y)
            p.drawText(int(x - 12), int(y + 8), 24, 14, Qt.AlignHCenter | Qt.AlignTop, col)


def _row_count(labware) -> int:
    return len({m.group(1) for name in labware.wells if (m := _WELL_RE.match(name))})


def _col_count(labware) -> int:
    return len({m.group(2) for name in labware.wells if (m := _WELL_RE.match(name))})


class SlotDetailView(QWidget):
    back_requested = pyqtSignal()
    labware_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.robot = None
        self.slot_name = None

        root = QVBoxLayout(self)
        header = QHBoxLayout()
        self.btn_back = QPushButton("Deck")
        self.btn_back.setIcon(icon_utils.icon("chevron", _INK, size=16, rotation=270))
        self.btn_back.setIconSize(_ICON_SIZE)
        self.btn_back.clicked.connect(self.back_requested.emit)
        header.addWidget(self.btn_back)
        self.title = QLabel("")
        self.title.setProperty("class", "h1")
        header.addWidget(self.title, 1)
        root.addLayout(header)

        self.size_label = QLabel("")
        self.size_label.setProperty("class", "eyebrow")
        root.addWidget(self.size_label)

        body = QHBoxLayout()
        self.canvas = LabwareCanvas()
        body.addWidget(self.canvas, 2)

        side = QVBoxLayout()
        self.empty_prompt = QLabel("no labware in this slot")
        self.empty_prompt.setWordWrap(True)
        self.empty_prompt.setProperty("class", "eyebrow")
        side.addWidget(self.empty_prompt)
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setProperty("class", "mono")
        side.addWidget(self.info_label)
        side.addStretch(1)

        self.btn_add = QPushButton("Add Labware…")
        self.btn_add.setIcon(icon_utils.icon("add_circle", _INK, size=16))
        self.btn_add.setIconSize(_ICON_SIZE)
        self.btn_add.clicked.connect(self._add_labware)
        self.btn_swap = QPushButton("Swap Labware…")
        self.btn_swap.clicked.connect(self._swap_labware)
        self.btn_remove = QPushButton("Remove Labware")
        self.btn_remove.setIcon(icon_utils.icon("minus_circle", _INK, size=16))
        self.btn_remove.setIconSize(_ICON_SIZE)
        self.btn_remove.clicked.connect(self._remove_labware)
        side.addWidget(self.btn_add)
        side.addWidget(self.btn_swap)
        side.addWidget(self.btn_remove)

        body.addLayout(side, 1)
        root.addLayout(body, 1)

    def set_context(self, robot, slot_name: str) -> None:
        self.robot = robot
        self.slot_name = slot_name
        self._refresh()

    def _current_labware(self):
        if self.robot is None or self.slot_name is None:
            return None
        for lw in self.robot.labware.values():
            if lw.slot is not None and lw.slot.name == self.slot_name:
                return lw
        return None

    def _refresh(self) -> None:
        if self.robot is None or self.slot_name is None:
            return
        slot = self.robot.deck.slots[self.slot_name]
        labware = self._current_labware()
        self.title.setText(f"SLOT {slot.name}")
        sw, sh = slot.size if (slot.size and slot.size[0]) else (0, 0)
        self.size_label.setText(
            f"slot footprint: {sw:.1f} × {sh:.1f} mm" if sw else "slot size not set"
        )
        self.canvas.set_content(slot, labware)

        has = labware is not None
        self.empty_prompt.setVisible(not has)
        self.btn_add.setVisible(not has)
        self.btn_swap.setVisible(has)
        self.btn_remove.setVisible(has)

        if not has:
            self.info_label.setText("")
            return

        wells = list(labware.wells.values())
        geo = wells[0].geometry if wells else None
        lines = [
            f"LABWARE  ·  {labware.name}",
            f"{len(wells)} wells  ({_row_count(labware)} × {_col_count(labware)})",
        ]
        if geo is not None:
            if geo.shape == WellShape.CIRCULAR:
                lines.append(f"⌀ {geo.diameter_mm:.1f} mm")
            else:
                lines.append(f"{geo.width_mm:.1f} × {geo.length_mm:.1f} mm")
            lines.append(f"depth {geo.depth_mm:.1f} mm  ·  {geo.bottom.value} bottom")
            lines.append(f"clearance {geo.bottom_clearance_mm:.1f} mm")
            if geo.max_volume_ul:
                lines.append(f"max volume {geo.max_volume_ul:.0f} µL")
        tip = self.robot.tips.get(labware.name)
        if tip is not None:
            lines.append(f"tip length {tip.length_mm:.1f} mm")
        self.info_label.setText("\n".join(lines))

    def _add_labware(self) -> None:
        self._open_dialog(swap=False)

    def _swap_labware(self) -> None:
        self._open_dialog(swap=True)

    def _open_dialog(self, swap: bool) -> None:
        slot = self.robot.deck.slots[self.slot_name]
        dlg = LabwareDialog(slot, self)
        if dlg.exec_() != QDialog.Accepted or dlg.definition is None:
            return

        new_name = dlg.definition.identifier
        existing = self.robot.labware.get(new_name)
        if existing is not None and (existing.slot is None or existing.slot.name != self.slot_name):
            other = existing.slot.name if existing.slot else "?"
            QMessageBox.warning(
                self,
                "Name already used",
                f"{new_name!r} is already placed on slot {other}. " "Choose a different name.",
            )
            return

        if swap:
            self._delete_current()
        try:
            self.robot.load(dlg.definition, self.slot_name)
        except Exception as exc:
            QMessageBox.warning(self, "Could not place labware", str(exc))
            return
        self._refresh()
        self.labware_changed.emit()

    def _delete_current(self) -> None:
        current = self._current_labware()
        if current is None:
            return
        del self.robot.labware[current.name]
        self.robot.tips.pop(current.name, None)

    def _remove_labware(self) -> None:
        self._delete_current()
        self._refresh()
        self.labware_changed.emit()
