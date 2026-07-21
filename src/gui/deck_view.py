"""Deck visualization: slots, placed labware (as a well grid), and a live
marker per mount, projected either top-down ("2D") or in a simple dimetric
"isometric" projection -- no 3D engine, just a 2D affine trick, which is
plenty for a deck laid out flat.

``Slot`` objects (see deck/deck.py) carry an origin but usually no ``size``
(``Deck.grid`` never sets one) -- there is nothing in the model to draw a
footprint from. Rather than draw dimensionless points, this widget derives a
nominal square footprint from the closest spacing between any two slots on
the deck, and only falls back to a fixed guess when there is nothing to
measure (a single-slot deck).
"""

from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import MountSide
from . import style as S
from .slot_detail_view import SlotDetailView

_MOUNT_COLOR = {
    MountSide.LEFT: QColor("#3E6E8E"),
    MountSide.RIGHT: QColor("#8E5B3E"),
    MountSide.REAR: QColor("#6B6B68"),
}
_MOUNT_LABEL = {MountSide.LEFT: "L", MountSide.RIGHT: "R", MountSide.REAR: "rear"}


class DeckCanvas(QWidget):
    slot_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 300)
        self.robot = None
        self.deck = None
        self._labware_by_slot: dict = {}
        self._nominal_slot_size = 30.0
        self.projection = "iso"
        self.positions: dict = {}  # MountSide -> DeckPoint | None
        self.selected_slot: str | None = None
        self._slot_paths: dict = {}  # name -> (QPainterPath, centroid)

    # -- data -----------------------------------------------------------
    def set_robot(self, robot) -> None:
        self.robot = robot
        self.deck = getattr(robot, "deck", None) if robot else None
        self._labware_by_slot = {}
        if robot is not None:
            for lw in robot.labware.values():
                if lw.slot is not None:
                    self._labware_by_slot[lw.slot.name] = lw
        self._nominal_slot_size = self._compute_nominal_slot_size()
        self.selected_slot = None
        self.update()

    def refresh_labware(self) -> None:
        """Re-reads robot.labware -- call after adding/swapping/removing
        labware via the slot detail view so the grid's fill/dots follow."""
        self._labware_by_slot = {}
        if self.robot is not None:
            for lw in self.robot.labware.values():
                if lw.slot is not None:
                    self._labware_by_slot[lw.slot.name] = lw
        self.update()

    def update_positions(self, positions: dict) -> None:
        self.positions = positions
        self.update()

    def set_projection(self, mode: str) -> None:
        self.projection = mode
        self.update()

    def _compute_nominal_slot_size(self) -> float:
        if not self.deck or len(self.deck.slots) < 2:
            return 30.0
        origins = [s.origin for s in self.deck.slots.values()]
        best = None
        for i in range(len(origins)):
            for j in range(i + 1, len(origins)):
                d = math.hypot(origins[i].x - origins[j].x, origins[i].y - origins[j].y)
                if d > 1e-6 and (best is None or d < best):
                    best = d
        return (best or 30.0) * 0.82

    def _slot_footprint(self, slot) -> tuple:
        if slot.size and slot.size[0] and slot.size[1]:
            return slot.size
        return self._nominal_slot_size, self._nominal_slot_size

    def _compute_plate_bounds(self):
        """(minx, miny, maxx, maxy) of the plate's outer edge, built from
        deck.margins -- None if the deck declares no margins. Slots whose
        footprint matches the deck's most common one get the directional
        front/left/right/rear margin; any other size (e.g. an oversized
        trash slot) gets the flat "oversized" margin instead."""
        margins = getattr(self.deck, "margins", None)
        if not margins or not self.deck.slots:
            return None
        footprints = [self._slot_footprint(s) for s in self.deck.slots.values()]
        common = max(set(footprints), key=footprints.count)
        minx = miny = math.inf
        maxx = maxy = -math.inf
        for slot in self.deck.slots.values():
            w, h = self._slot_footprint(slot)
            ox, oy = slot.origin.x, slot.origin.y
            if (w, h) == common:
                left, right = margins.get("left", 0), margins.get("right", 0)
                front, rear = margins.get("front", 0), margins.get("rear", 0)
            else:
                left = right = front = rear = margins.get("oversized", 0)
            minx, maxx = min(minx, ox - left), max(maxx, ox + w + right)
            miny, maxy = min(miny, oy - front), max(maxy, oy + h + rear)
        return (minx, miny, maxx, maxy)

    def _compute_frame_bounds(self, plate_bounds):
        """(minx, miny, maxx, maxy) of the robot's outer frame, expanding
        ``plate_bounds`` by deck.frame_margins -- None if either is
        unavailable. The deck plate is mounted with this much frame to
        spare beyond its own edge on each side (0 is a valid margin, e.g.
        the front edge sitting flush with the frame)."""
        frame_margins = getattr(self.deck, "frame_margins", None)
        if not frame_margins or plate_bounds is None:
            return None
        minx, miny, maxx, maxy = plate_bounds
        return (minx - frame_margins.get("left", 0),
               miny - frame_margins.get("front", 0),
               maxx + frame_margins.get("right", 0),
               maxy + frame_margins.get("rear", 0))

    def _home_projected(self):
        """Projected (unscaled) deck point the gantry's shared X/Y reference
        homes to -- the calibration's own answer for motor (0, 0), so it
        automatically agrees with the live mount markers once homed rather
        than being a second, independently-guessed "home" location. None
        without a calibration (motor (0, 0) has no known deck point)."""
        if self.robot is None or getattr(self.robot, "calibration", None) is None:
            return None
        try:
            x, y = self.robot.calibration.motor_to_deck_xy(0, 0)
        except Exception:
            return None
        return self._project(x, y)

    def _project(self, x: float, y: float) -> tuple:
        """Deck (x, y) in mm -> unscaled screen-ish coords, +y screen-down.

        ``y`` is deck depth (slot row "1" at y=0 in front, row "12" at max
        y in back -- see robot.example.yaml's deck: comment). The near
        corner (min x, min y) must land at the *bottom* of the projected
        diamond and the far corner (max x, max y) at the *top*, so the front
        row renders nearest the viewer -- hence the y term is negated here
        (unlike the classic (x-y, x+y) form, which puts min-y at the top).
        """
        if self.projection == "iso":
            rad = math.radians(30)
            return ((x - y) * math.cos(rad), -(x + y) * math.sin(rad))
        return (x, -y)

    # -- hit testing ------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        pt = event.pos()
        for name, (path, _centroid) in self._slot_paths.items():
            if path.contains(QPointF(pt)):
                self.selected_slot = name
                self.slot_clicked.emit(name)
                self.update()
                return

    # -- painting ---------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(S.PANEL))

        if not self.deck or not self.deck.slots:
            p.setPen(QColor(S.INK_MUTED))
            p.drawText(
                self.rect(),
                Qt.AlignCenter,
                "no deck configured\n(connect with a robot config to visualize slots)",
            )
            return

        projected = {}
        all_pts = []
        for name, slot in self.deck.slots.items():
            w, h = self._slot_footprint(slot)
            ox, oy = slot.origin.x, slot.origin.y
            corners = [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
            proj = [self._project(cx, cy) for cx, cy in corners]
            projected[name] = proj
            all_pts.extend(proj)

        plate_bounds = self._compute_plate_bounds()
        plate_corners_proj = None
        if plate_bounds is not None:
            pminx, pminy, pmaxx, pmaxy = plate_bounds
            plate_corners_proj = [self._project(cx, cy) for cx, cy in
                                  ((pminx, pminy), (pmaxx, pminy), (pmaxx, pmaxy), (pminx, pmaxy))]
            all_pts.extend(plate_corners_proj)

        frame_bounds = self._compute_frame_bounds(plate_bounds)
        frame_corners_proj = None
        if frame_bounds is not None:
            fminx, fminy, fmaxx, fmaxy = frame_bounds
            frame_corners_proj = [self._project(cx, cy) for cx, cy in
                                  ((fminx, fminy), (fmaxx, fminy), (fmaxx, fmaxy), (fminx, fmaxy))]
            all_pts.extend(frame_corners_proj)

        home_proj = self._home_projected()
        if home_proj is not None:
            all_pts.append(home_proj)

        xs = [pt[0] for pt in all_pts]
        ys = [pt[1] for pt in all_pts]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        pad = 34
        span_x = max(maxx - minx, 1e-6)
        span_y = max(maxy - miny, 1e-6)
        scale = min(
            max(self.width() - 2 * pad, 10) / span_x, max(self.height() - 2 * pad, 10) / span_y
        )
        cx0, cy0 = (minx + maxx) / 2, (miny + maxy) / 2

        def to_screen(pt):
            return (
                self.width() / 2 + (pt[0] - cx0) * scale,
                self.height() / 2 + (pt[1] - cy0) * scale,
            )

        if frame_corners_proj is not None:
            screen_corners = [to_screen(pt) for pt in frame_corners_proj]
            frame_path = QPainterPath()
            frame_path.moveTo(*screen_corners[0])
            for sp in screen_corners[1:]:
                frame_path.lineTo(*sp)
            frame_path.closeSubpath()
            pen = QPen(QColor(S.BORDER))
            pen.setStyle(Qt.DashLine)
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(frame_path)

        if plate_corners_proj is not None:
            screen_corners = [to_screen(pt) for pt in plate_corners_proj]
            plate_path = QPainterPath()
            plate_path.moveTo(*screen_corners[0])
            for sp in screen_corners[1:]:
                plate_path.lineTo(*sp)
            plate_path.closeSubpath()
            pen = QPen(QColor(S.BORDER))
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(plate_path)

        self._slot_paths = {}
        font = QFont(S.UI_FONT, 8)
        p.setFont(font)
        for name, proj in projected.items():
            screen_pts = [to_screen(pt) for pt in proj]
            path = QPainterPath()
            path.moveTo(*screen_pts[0])
            for sp in screen_pts[1:]:
                path.lineTo(*sp)
            path.closeSubpath()
            centroid = (sum(s[0] for s in screen_pts) / 4, sum(s[1] for s in screen_pts) / 4)
            self._slot_paths[name] = (path, centroid)

            has_labware = name in self._labware_by_slot
            selected = name == self.selected_slot
            p.setBrush(QColor("#E4EEE7") if has_labware else QColor(S.PANEL))
            pen = QPen(QColor(S.INK if selected else S.BORDER_STRONG))
            pen.setWidthF(2.2 if selected else 1.0)
            p.setPen(pen)
            p.drawPath(path)

            p.setPen(QColor(S.INK_MUTED))
            p.drawText(int(centroid[0] - 24), int(centroid[1] - 8), 48, 16, Qt.AlignCenter, name)

            lw = self._labware_by_slot.get(name)
            if lw is not None:
                slot = self.deck.slots[name]
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(S.INK_MUTED))
                for well in lw.wells.values():
                    wx = slot.origin.x + well.offset.x
                    wy = slot.origin.y + well.offset.y
                    wsx, wsy = to_screen(self._project(wx, wy))
                    p.drawEllipse(QPointF(wsx, wsy), 1.5, 1.5)

        for side, pt in self.positions.items():
            if pt is None:
                continue
            sx, sy = to_screen(self._project(pt.x, pt.y))
            color = _MOUNT_COLOR.get(side, QColor(S.INK))
            p.setPen(QPen(QColor(S.PANEL), 1.5))
            p.setBrush(color)
            p.drawEllipse(QPointF(sx, sy), 6, 6)
            p.setPen(color)
            p.drawText(int(sx) + 8, int(sy) - 6, _MOUNT_LABEL.get(side, "?"))

        if home_proj is not None:
            hx, hy = to_screen(home_proj)
            p.setPen(QPen(QColor(S.INK), 1.5))
            p.setBrush(QColor(S.INK))
            hs = 5
            p.drawRect(QRectF(hx - hs, hy - hs, hs * 2, hs * 2))
            p.drawText(int(hx) + 8, int(hy) + 4, "⌂ home")


class DeckView(QWidget):
    """DeckCanvas plus the 2D/iso toggle and a one-line selection readout,
    mirroring the "DECK VIEW" panel + status line from the wireframe.

    Clicking a slot zooms into it (SlotDetailView), rendered independently
    of the whole-deck scale so a plate's actual well grid is legible; that
    view also owns adding/swapping/removing labware for that slot.
    """

    slot_selected = pyqtSignal(str)
    labware_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.robot = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        grid_page = QWidget()
        grid_layout = QVBoxLayout(grid_page)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("DECK VIEW")
        title.setProperty("class", "eyebrow")
        header.addWidget(title)
        header.addStretch(1)
        self.btn_2d = QPushButton("2D")
        self.btn_iso = QPushButton("3D")
        for b in (self.btn_2d, self.btn_iso):
            b.setCheckable(True)
            b.setFixedWidth(40)
        self.btn_iso.setChecked(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.btn_2d)
        group.addButton(self.btn_iso)
        self.btn_2d.clicked.connect(lambda: self._set_projection("2d"))
        self.btn_iso.clicked.connect(lambda: self._set_projection("iso"))
        header.addWidget(self.btn_2d)
        header.addWidget(self.btn_iso)
        grid_layout.addLayout(header)

        self.canvas = DeckCanvas()
        self.canvas.slot_clicked.connect(self._on_slot_clicked)
        grid_layout.addWidget(self.canvas, 1)

        self.info_label = QLabel("no deck configured")
        self.info_label.setProperty("class", "mono")
        grid_layout.addWidget(self.info_label)
        self.stack.addWidget(grid_page)

        self.detail = SlotDetailView()
        self.detail.back_requested.connect(self._show_grid)
        self.detail.labware_changed.connect(self._on_labware_changed)
        self.stack.addWidget(self.detail)

    def set_robot(self, robot) -> None:
        self.robot = robot
        self.canvas.set_robot(robot)
        if robot is None:
            self.info_label.setText("not connected")
        elif robot.deck is None:
            self.info_label.setText("no deck configured")
        else:
            self.info_label.setText(
                f"{len(robot.deck.slots)} slots · {len(robot.labware)} labware placed"
            )
        self._show_grid()

    def update_positions(self, positions: dict) -> None:
        self.canvas.update_positions(positions)

    def _set_projection(self, mode: str) -> None:
        self.canvas.set_projection(mode)

    def _on_slot_clicked(self, name: str) -> None:
        lw = self.canvas._labware_by_slot.get(name)
        if lw is not None:
            self.info_label.setText(f"slot {name} · {lw.name} ({len(lw.wells)} wells)")
        else:
            self.info_label.setText(f"slot {name} · empty")
        self.slot_selected.emit(name)
        if self.robot is not None and self.robot.deck is not None:
            self.detail.set_context(self.robot, name)
            self.stack.setCurrentWidget(self.detail)

    def _show_grid(self) -> None:
        self.stack.setCurrentIndex(0)

    def _on_labware_changed(self) -> None:
        self.canvas.refresh_labware()
        if self.robot is not None and self.robot.deck is not None:
            self.info_label.setText(
                f"{len(self.robot.deck.slots)} slots · {len(self.robot.labware)} labware placed"
            )
        self.labware_changed.emit()
