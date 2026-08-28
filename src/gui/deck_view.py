from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
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
from . import icon_utils
from . import style as S
from .slot_detail_view import SlotDetailView
from .tokens import TOKENS

_ICON_SIZE = QSize(16, 16)

_MOUNT_COLOR = {
    MountSide.LEFT: QColor("#3E6E8E"),
    MountSide.RIGHT: QColor("#8E5B3E"),
    MountSide.REAR: QColor("#6B6B68"),
}
_MOUNT_LABEL = {MountSide.LEFT: "L", MountSide.RIGHT: "R", MountSide.REAR: "rear"}

_CORNER_NOTCH_MM = 10.0
_SEPARATOR_COLOR = QColor("#C9C3B2")
_SEPARATOR_HEIGHT_MM = 5.0
_GANTRY_HEIGHT_MM = 400.0
_WALL_COLOR = QColor("#B7AD93")
_OBSTACLE_COLOR = QColor("#8F8672")
_ENCLOSURE_COLOR = QColor("#9AA0A6")
_CAL_MARK_COLOR = QColor("#B23A3A")
_CAL_MARK_SIZE_MM = 5.0
_CAL_MARK_INSET_Z_MM = -0.1

_ZOOM_MIN = 0.25
_ZOOM_MAX = 8.0
_ZOOM_STEP = 1.15
_DRAG_THRESHOLD_PX = 4
_SPIN_DEG_PER_PX = 0.5
_ELEVATION_DEFAULT_DEG = 35.0
_ELEVATION_MIN_DEG = 8.0
_ELEVATION_MAX_DEG = 88.0


def _nice_tick_step(span: float, target_ticks: int = 6) -> float:
    if span <= 0:
        return 50.0
    raw = span / max(target_ticks, 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        step = m * magnitude
        if step >= raw:
            return step
    return 10 * magnitude


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
        self.positions: dict = {}
        self.selected_slot: str | None = None
        self._slot_paths: dict = {}
        self._home_pixmap = None
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._azimuth_deg = 0.0
        self._elevation_deg = _ELEVATION_DEFAULT_DEG
        self._drag_button = None
        self._drag_start = None
        self._drag_moved = False
        self._drag_pan_origin = (0.0, 0.0)
        self._drag_azimuth_origin = 0.0
        self._drag_elevation_origin = _ELEVATION_DEFAULT_DEG

    def _home_icon_pixmap(self):
        if self._home_pixmap is None:
            self._home_pixmap = icon_utils.icon(
                "home", QColor(*TOKENS["flat_text"][:3]), size=12
            ).pixmap(QSize(12, 12))
        return self._home_pixmap

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
        self.reset_view()

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._azimuth_deg = 0.0
        self._elevation_deg = _ELEVATION_DEFAULT_DEG
        self.update()

    def refresh_labware(self) -> None:
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

    def _common_footprint(self):
        if not self.deck or not self.deck.slots:
            return None
        footprints = [self._slot_footprint(s) for s in self.deck.slots.values()]
        return max(set(footprints), key=footprints.count)

    def _slots_bbox(self):
        if not self.deck or not self.deck.slots:
            return None
        minx = miny = math.inf
        maxx = maxy = -math.inf
        for slot in self.deck.slots.values():
            w, h = self._slot_footprint(slot)
            ox, oy = slot.origin.x, slot.origin.y
            minx, maxx = min(minx, ox), max(maxx, ox + w)
            miny, maxy = min(miny, oy), max(maxy, oy + h)
        return (minx, miny, maxx, maxy)

    def _separator_segments(
        self,
        notch: float = None,
        min_overlap: float = 5.0,
        max_gap: float = 30.0,
        thin_width: float = 1.0,
    ) -> list:

        common = self._common_footprint()
        if common is None:
            return []
        notch = notch if notch is not None else _CORNER_NOTCH_MM
        slots = list(self.deck.slots.values())
        rects = []
        is_regular = []
        for s in slots:
            w, h = self._slot_footprint(s)
            rects.append((s.origin.x, s.origin.y, s.origin.x + w, s.origin.y + h))
            is_regular.append((w, h) == common)
        n = len(rects)
        has_neighbor = [[False, False, False, False] for _ in range(n)]
        gap_widths = []
        segments = []

        for i in range(n):
            ax0, ay0, ax1, ay1 = rects[i]
            for j in range(i + 1, n):
                bx0, by0, bx1, by1 = rects[j]
                both_regular = is_regular[i] and is_regular[j]

                oy0, oy1 = max(ay0, by0), min(ay1, by1)
                if oy1 - oy0 >= min_overlap:
                    y0, y1 = oy0 + notch, oy1 - notch
                    if 0 <= bx0 - ax1 <= max_gap:
                        has_neighbor[i][1] = has_neighbor[j][0] = True
                        if y1 > y0:
                            if both_regular:
                                gap_widths.append(bx0 - ax1)
                                segments.append((ax1, y0, bx0, y1))
                            else:
                                mid = (ax1 + bx0) / 2
                                segments.append(
                                    (mid - thin_width / 2, y0, mid + thin_width / 2, y1)
                                )
                    elif 0 <= ax0 - bx1 <= max_gap:
                        has_neighbor[i][0] = has_neighbor[j][1] = True
                        if y1 > y0:
                            if both_regular:
                                gap_widths.append(ax0 - bx1)
                                segments.append((bx1, y0, ax0, y1))
                            else:
                                mid = (bx1 + ax0) / 2
                                segments.append(
                                    (mid - thin_width / 2, y0, mid + thin_width / 2, y1)
                                )

                ox0, ox1 = max(ax0, bx0), min(ax1, bx1)
                if ox1 - ox0 >= min_overlap:
                    x0, x1 = ox0 + notch, ox1 - notch
                    if 0 <= by0 - ay1 <= max_gap:
                        has_neighbor[i][3] = has_neighbor[j][2] = True
                        if x1 > x0:
                            if both_regular:
                                gap_widths.append(by0 - ay1)
                                segments.append((x0, ay1, x1, by0))
                            else:
                                mid = (ay1 + by0) / 2
                                segments.append(
                                    (x0, mid - thin_width / 2, x1, mid + thin_width / 2)
                                )
                    elif 0 <= ay0 - by1 <= max_gap:
                        has_neighbor[i][2] = has_neighbor[j][3] = True
                        if x1 > x0:
                            if both_regular:
                                gap_widths.append(ay0 - by1)
                                segments.append((x0, by1, x1, ay0))
                            else:
                                mid = (by1 + ay0) / 2
                                segments.append(
                                    (x0, mid - thin_width / 2, x1, mid + thin_width / 2)
                                )

        perimeter_width = min(gap_widths) if gap_widths else notch / 2
        for i in range(n):
            if not is_regular[i]:
                continue
            ax0, ay0, ax1, ay1 = rects[i]
            y0, y1 = ay0 + notch, ay1 - notch
            x0, x1 = ax0 + notch, ax1 - notch
            if not has_neighbor[i][0] and y1 > y0:
                segments.append((ax0 - perimeter_width, y0, ax0, y1))
            if not has_neighbor[i][1] and y1 > y0:
                segments.append((ax1, y0, ax1 + perimeter_width, y1))
            if not has_neighbor[i][2] and x1 > x0:
                segments.append((x0, ay0 - perimeter_width, x1, ay0))
            if not has_neighbor[i][3] and x1 > x0:
                segments.append((x0, ay1, x1, ay1 + perimeter_width))

        return segments

    def _compute_plate_bounds(self):
        margins = getattr(self.deck, "margins", None)
        if not margins or not self.deck.slots:
            return None
        common = self._common_footprint()
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
        frame_margins = getattr(self.deck, "frame_margins", None)
        if not frame_margins or plate_bounds is None:
            return None
        minx, miny, maxx, maxy = plate_bounds
        return (
            minx - frame_margins.get("left", 0),
            miny - frame_margins.get("front", 0),
            maxx + frame_margins.get("right", 0),
            maxy + frame_margins.get("rear", 0),
        )

    def _labware_height(self, lw) -> float:
        if lw is None or not lw.wells:
            return 0.0
        return max(well.offset.z for well in lw.wells.values())

    def _box_faces(
        self,
        ox: float,
        oy: float,
        w: float,
        h: float,
        height_mm: float,
        top_color: QColor,
        side_color_a: QColor,
        side_color_b: QColor,
    ) -> list:
        faces = {
            "front": [(ox, oy, 0), (ox + w, oy, 0), (ox + w, oy, height_mm), (ox, oy, height_mm)],
            "back": [
                (ox, oy + h, 0),
                (ox + w, oy + h, 0),
                (ox + w, oy + h, height_mm),
                (ox, oy + h, height_mm),
            ],
            "left": [(ox, oy, 0), (ox, oy + h, 0), (ox, oy + h, height_mm), (ox, oy, height_mm)],
            "right": [
                (ox + w, oy, 0),
                (ox + w, oy + h, 0),
                (ox + w, oy + h, height_mm),
                (ox + w, oy, height_mm),
            ],
        }
        visible = self._visible_side_faces()
        shades = {visible[0]: side_color_a, visible[1]: side_color_b}

        out = []
        for face_name in visible:
            pts = faces[face_name]
            cx = sum(pt[0] for pt in pts) / 4
            cy = sum(pt[1] for pt in pts) / 4
            cz = sum(pt[2] for pt in pts) / 4
            out.append((self._camera_depth(cx, cy, cz), pts, shades[face_name]))
        top_pts = [
            (ox, oy, height_mm),
            (ox + w, oy, height_mm),
            (ox + w, oy + h, height_mm),
            (ox, oy + h, height_mm),
        ]
        out.append((self._camera_depth(ox + w / 2, oy + h / 2, height_mm), top_pts, top_color))
        return out

    def _draw_face(self, p: QPainter, to_screen, pts: list, color: QColor) -> None:
        screen = [to_screen(self._project(x, y, z)) for x, y, z in pts]
        path = QPainterPath()
        path.moveTo(*screen[0])
        for sp in screen[1:]:
            path.lineTo(*sp)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path)

    def _rib_faces(self, gminx: float, gminy: float, gmaxx: float, gmaxy: float) -> list:
        return self._box_faces(
            gminx,
            gminy,
            gmaxx - gminx,
            gmaxy - gminy,
            _SEPARATOR_HEIGHT_MM,
            _SEPARATOR_COLOR.lighter(108),
            _SEPARATOR_COLOR.darker(118),
            _SEPARATOR_COLOR.darker(106),
        )

    def _draw_separator_rib_flat(
        self, p: QPainter, to_screen, gminx: float, gminy: float, gmaxx: float, gmaxy: float
    ) -> None:
        corners = [
            (gminx, gminy, 0.0),
            (gmaxx, gminy, 0.0),
            (gmaxx, gmaxy, 0.0),
            (gminx, gmaxy, 0.0),
        ]
        self._draw_face(p, to_screen, corners, _SEPARATOR_COLOR)

    def _slot_wall_rects(self, slot) -> list:
        t = slot.wall_thickness_mm
        if t <= 0:
            return []
        w, h = self._slot_footprint(slot)
        ox, oy = slot.origin.x, slot.origin.y
        return [
            (ox, oy, ox + w, oy + t),  # front (min-y) wall
            (ox, oy + h - t, ox + w, oy + h),  # back (max-y) wall
            (ox, oy, ox + t, oy + h),  # left (min-x) wall
            (ox + w - t, oy, ox + w, oy + h),  # right (max-x) wall
        ]

    def _draw_slot_floor(
        self, p: QPainter, to_screen, name: str, common_footprint, scale: float
    ) -> None:
        slot = self.deck.slots[name]
        w, h = self._slot_footprint(slot)
        ox, oy = slot.origin.x, slot.origin.y
        corners = [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
        screen_pts = [to_screen(self._project(cx, cy)) for cx, cy in corners]
        path = QPainterPath()
        path.moveTo(*screen_pts[0])
        for sp in screen_pts[1:]:
            path.lineTo(*sp)
        path.closeSubpath()
        centroid = (
            sum(s[0] for s in screen_pts) / len(screen_pts),
            sum(s[1] for s in screen_pts) / len(screen_pts),
        )
        self._slot_paths[name] = (path, centroid)

        has_labware = name in self._labware_by_slot
        selected = name == self.selected_slot
        oversized = (w, h) != common_footprint
        draw_box = (
            self.projection == "iso" and self._labware_height(self._labware_by_slot.get(name)) > 0
        )
        p.setBrush(
            QColor(S.PANEL) if draw_box else (QColor("#E4EEE7") if has_labware else QColor(S.PANEL))
        )
        if selected:
            pen = QPen(QColor(S.INK))
            pen.setWidthF(2.2)
            p.setPen(pen)
        elif oversized:
            pen = QPen(QColor(S.BORDER_STRONG))
            pen.setWidthF(max(2.0 * scale, 1.0))
            p.setPen(pen)
        else:
            p.setPen(Qt.NoPen)
        p.drawPath(path)

        p.setPen(QColor(S.INK_MUTED))
        p.drawText(int(centroid[0] - 24), int(centroid[1] - 8), 48, 16, Qt.AlignCenter, name)

    def _draw_wells(self, p: QPainter, to_screen, lw, ox: float, oy: float, z: float) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(S.INK_MUTED))
        for well in lw.wells.values():
            wx = ox + well.offset.x
            wy = oy + well.offset.y
            wsx, wsy = to_screen(self._project(wx, wy, z))
            p.drawEllipse(QPointF(wsx, wsy), 1.5, 1.5)

    def _home_deck_point(self):
        if self.robot is None or getattr(self.robot, "calibration", None) is None:
            return None
        try:
            return self.robot.calibration.motor_to_deck_xy(0, 0)
        except Exception:
            return None

    def _project(self, x: float, y: float, z: float = 0.0) -> tuple:
        if self.projection != "iso":
            return (x, -y)
        az = math.radians(self._azimuth_deg)
        cos_a, sin_a = math.cos(az), math.sin(az)
        x1, y1 = x * cos_a - y * sin_a, x * sin_a + y * cos_a
        el = math.radians(self._elevation_deg)
        cos_e, sin_e = math.cos(el), math.sin(el)
        return (x1, -(y1 * sin_e + z * cos_e))

    def _camera_depth(self, x: float, y: float, z: float = 0.0) -> float:
        if self.projection != "iso":
            return 0.0
        az = math.radians(self._azimuth_deg)
        cos_a, sin_a = math.cos(az), math.sin(az)
        x1, y1 = x * cos_a - y * sin_a, x * sin_a + y * cos_a
        el = math.radians(self._elevation_deg)
        cos_e, sin_e = math.cos(el), math.sin(el)
        return y1 * cos_e - z * sin_e

    def _visible_side_faces(self) -> list:
        phi = math.radians(-self._azimuth_deg)
        cos_p, sin_p = math.cos(phi), math.sin(phi)
        base_x, base_y = -1.0, -1.0
        cam_x = base_x * cos_p - base_y * sin_p
        cam_y = base_x * sin_p + base_y * cos_p
        normals = {
            "front": (0.0, -1.0),
            "back": (0.0, 1.0),
            "left": (-1.0, 0.0),
            "right": (1.0, 0.0),
        }
        ranked = sorted(normals, key=lambda n: -(normals[n][0] * cam_x + normals[n][1] * cam_y))
        return ranked[:2]

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            self._drag_button = event.button()
            self._drag_start = event.pos()
            self._drag_moved = False
            self._drag_pan_origin = (self._pan_x, self._pan_y)
            self._drag_azimuth_origin = self._azimuth_deg
            self._drag_elevation_origin = self._elevation_deg

    def mouseMoveEvent(self, event) -> None:
        if self._drag_button is None or self._drag_start is None:
            return
        delta = event.pos() - self._drag_start
        if not self._drag_moved and (
            abs(delta.x()) > _DRAG_THRESHOLD_PX or abs(delta.y()) > _DRAG_THRESHOLD_PX
        ):
            self._drag_moved = True
        if not self._drag_moved:
            return
        if self._drag_button == Qt.LeftButton:
            self._pan_x = self._drag_pan_origin[0] + delta.x()
            self._pan_y = self._drag_pan_origin[1] + delta.y()
        elif self._drag_button == Qt.RightButton:
            self._azimuth_deg = (self._drag_azimuth_origin + delta.x() * _SPIN_DEG_PER_PX) % 360
            self._elevation_deg = min(
                _ELEVATION_MAX_DEG,
                max(_ELEVATION_MIN_DEG, self._drag_elevation_origin - delta.y() * _SPIN_DEG_PER_PX),
            )
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self._drag_moved:
            pt = event.pos()
            for name, (path, _centroid) in self._slot_paths.items():
                if path.contains(QPointF(pt)):
                    self.selected_slot = name
                    self.slot_clicked.emit(name)
                    self.update()
                    break
        self._drag_button = None
        self._drag_start = None
        self._drag_moved = False

    def wheelEvent(self, event) -> None:
        steps = event.angleDelta().y() / 120.0
        if not steps:
            return
        self._zoom = min(_ZOOM_MAX, max(_ZOOM_MIN, self._zoom * (_ZOOM_STEP**steps)))
        self.update()

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

        common_footprint = self._common_footprint()
        is_3d = self.projection == "iso"
        all_pts = []
        for slot in self.deck.slots.values():
            w, h = self._slot_footprint(slot)
            ox, oy = slot.origin.x, slot.origin.y
            all_pts.extend(
                self._project(cx, cy)
                for cx, cy in ((ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h))
            )

        separator_segments = self._separator_segments()
        if is_3d:
            for name, lw in self._labware_by_slot.items():
                height = self._labware_height(lw)
                slot = self.deck.slots.get(name)
                if height <= 0 or slot is None:
                    continue
                w, h = self._slot_footprint(slot)
                ox, oy = slot.origin.x, slot.origin.y
                all_pts.extend(
                    self._project(cx, cy, height)
                    for cx, cy in ((ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h))
                )
            for gminx, gminy, gmaxx, gmaxy in separator_segments:
                all_pts.extend(
                    self._project(cx, cy, _SEPARATOR_HEIGHT_MM)
                    for cx, cy in ((gminx, gminy), (gmaxx, gminy), (gmaxx, gmaxy), (gminx, gmaxy))
                )
            for slot in self.deck.slots.values():
                if slot.wall_height_mm > 0:
                    for wx0, wy0, wx1, wy1 in self._slot_wall_rects(slot):
                        all_pts.extend(
                            self._project(cx, cy, slot.wall_height_mm)
                            for cx, cy in ((wx0, wy0), (wx1, wy0), (wx1, wy1), (wx0, wy1))
                        )
                for obs in slot.obstacles:
                    oox, ooy = slot.origin.x + obs.offset[0], slot.origin.y + obs.offset[1]
                    ow, oh = obs.size
                    all_pts.extend(
                        self._project(cx, cy, obs.height_mm)
                        for cx, cy in (
                            (oox, ooy),
                            (oox + ow, ooy),
                            (oox + ow, ooy + oh),
                            (oox, ooy + oh),
                        )
                    )
            for pt in self.positions.values():
                if pt is not None:
                    all_pts.append(self._project(pt.x, pt.y, pt.z if pt.z else _GANTRY_HEIGHT_MM))

        plate_bounds = self._compute_plate_bounds()
        plate_corners_proj = None
        if plate_bounds is not None:
            pminx, pminy, pmaxx, pmaxy = plate_bounds
            plate_corners_proj = [
                self._project(cx, cy)
                for cx, cy in ((pminx, pminy), (pmaxx, pminy), (pmaxx, pmaxy), (pminx, pmaxy))
            ]
            all_pts.extend(plate_corners_proj)

        frame_bounds = self._compute_frame_bounds(plate_bounds)
        frame_corners_proj = None
        if frame_bounds is not None:
            fminx, fminy, fmaxx, fmaxy = frame_bounds
            frame_corners_proj = [
                self._project(cx, cy)
                for cx, cy in ((fminx, fminy), (fmaxx, fminy), (fmaxx, fmaxy), (fminx, fmaxy))
            ]
            all_pts.extend(frame_corners_proj)

        enclosure_h = getattr(self.deck, "enclosure_height_mm", None)
        enclosure_top_proj = None
        if is_3d and enclosure_h and frame_bounds is not None:
            fminx, fminy, fmaxx, fmaxy = frame_bounds
            enclosure_top_proj = [
                self._project(cx, cy, enclosure_h)
                for cx, cy in ((fminx, fminy), (fmaxx, fminy), (fmaxx, fmaxy), (fminx, fmaxy))
            ]

        home_xy = self._home_deck_point()
        home_proj = self._project(*home_xy) if home_xy is not None else None
        if home_proj is not None:
            all_pts.append(home_proj)
        visible_marks = []
        if self.deck is not None:
            for mark in self.deck.calibration_marks.values():
                if mark.slot in self._labware_by_slot:
                    continue
                z = mark.point.z + _CAL_MARK_INSET_Z_MM
                center_proj = self._project(mark.point.x, mark.point.y, z)
                visible_marks.append((mark, z))
                all_pts.append(center_proj)

        xs = [pt[0] for pt in all_pts]
        ys = [pt[1] for pt in all_pts]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        pad = 34
        span_x = max(maxx - minx, 1e-6)
        span_y = max(maxy - miny, 1e-6)
        scale = (
            min(max(self.width() - 2 * pad, 10) / span_x, max(self.height() - 2 * pad, 10) / span_y)
            * self._zoom
        )
        cx0, cy0 = (minx + maxx) / 2, (miny + maxy) / 2

        def to_screen(pt):
            return (
                self.width() / 2 + (pt[0] - cx0) * scale + self._pan_x,
                self.height() / 2 + (pt[1] - cy0) * scale + self._pan_y,
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

        if enclosure_top_proj is not None:
            base_screen = [to_screen(pt) for pt in frame_corners_proj]
            top_screen = [to_screen(pt) for pt in enclosure_top_proj]
            pen = QPen(_ENCLOSURE_COLOR)
            pen.setStyle(Qt.DashLine)
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            top_path = QPainterPath()
            top_path.moveTo(*top_screen[0])
            for sp in top_screen[1:]:
                top_path.lineTo(*sp)
            top_path.closeSubpath()
            p.drawPath(top_path)
            for b, t in zip(base_screen, top_screen):
                p.drawLine(QPointF(*b), QPointF(*t))

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
        drawables = []
        for gminx, gminy, gmaxx, gmaxy in separator_segments:
            if is_3d:
                for depth, pts, color in self._rib_faces(gminx, gminy, gmaxx, gmaxy):
                    drawables.append(
                        (
                            depth,
                            lambda pts=pts, color=color: self._draw_face(p, to_screen, pts, color),
                        )
                    )
            else:
                depth = self._camera_depth((gminx + gmaxx) / 2, (gminy + gmaxy) / 2)
                drawables.append(
                    (
                        depth,
                        lambda a=gminx, b=gminy, c=gmaxx, d=gmaxy: self._draw_separator_rib_flat(
                            p, to_screen, a, b, c, d
                        ),
                    )
                )

        for name, slot in self.deck.slots.items():
            w, h = self._slot_footprint(slot)
            ox, oy = slot.origin.x, slot.origin.y
            floor_depth = self._camera_depth(ox + w / 2, oy + h / 2, 0.0)
            drawables.append(
                (
                    floor_depth,
                    lambda n=name: self._draw_slot_floor(p, to_screen, n, common_footprint, scale),
                )
            )

            if slot.wall_height_mm > 0:
                for wx0, wy0, wx1, wy1 in self._slot_wall_rects(slot):
                    if is_3d:
                        for depth, pts, color in self._box_faces(
                            wx0,
                            wy0,
                            wx1 - wx0,
                            wy1 - wy0,
                            slot.wall_height_mm,
                            _WALL_COLOR.lighter(112),
                            _WALL_COLOR.darker(118),
                            _WALL_COLOR.darker(106),
                        ):
                            drawables.append(
                                (
                                    depth,
                                    lambda pts=pts, color=color: self._draw_face(
                                        p, to_screen, pts, color
                                    ),
                                )
                            )
                    else:
                        wall_depth = self._camera_depth((wx0 + wx1) / 2, (wy0 + wy1) / 2)
                        drawables.append(
                            (
                                wall_depth,
                                lambda a=wx0, b=wy0, c=wx1, d=wy1: self._draw_face(
                                    p,
                                    to_screen,
                                    [(a, b, 0.0), (c, b, 0.0), (c, d, 0.0), (a, d, 0.0)],
                                    _WALL_COLOR,
                                ),
                            )
                        )
            for obs in slot.obstacles:
                oox, ooy = ox + obs.offset[0], oy + obs.offset[1]
                ow, oh = obs.size
                if is_3d:
                    for depth, pts, color in self._box_faces(
                        oox,
                        ooy,
                        ow,
                        oh,
                        obs.height_mm,
                        _OBSTACLE_COLOR.lighter(115),
                        _OBSTACLE_COLOR.darker(122),
                        _OBSTACLE_COLOR.darker(108),
                    ):
                        drawables.append(
                            (
                                depth,
                                lambda pts=pts, color=color: self._draw_face(
                                    p, to_screen, pts, color
                                ),
                            )
                        )
                else:
                    obs_depth = self._camera_depth(oox + ow / 2, ooy + oh / 2)
                    drawables.append(
                        (
                            obs_depth,
                            lambda a=oox, b=ooy, c=ow, d=oh: self._draw_face(
                                p,
                                to_screen,
                                [
                                    (a, b, 0.0),
                                    (a + c, b, 0.0),
                                    (a + c, b + d, 0.0),
                                    (a, b + d, 0.0),
                                ],
                                _OBSTACLE_COLOR,
                            ),
                        )
                    )

            lw = self._labware_by_slot.get(name)
            if lw is None:
                continue
            height = self._labware_height(lw) if is_3d else 0.0
            if height > 0:
                for depth, pts, color in self._box_faces(
                    ox, oy, w, h, height, QColor("#E4EEE7"), QColor("#AFC9BA"), QColor("#C7DBCD")
                ):
                    drawables.append(
                        (
                            depth,
                            lambda pts=pts, color=color: self._draw_face(p, to_screen, pts, color),
                        )
                    )
                wells_depth = self._camera_depth(ox + w / 2, oy + h / 2, height)
                drawables.append(
                    (
                        wells_depth,
                        lambda lw=lw, ox=ox, oy=oy, z=height: self._draw_wells(
                            p, to_screen, lw, ox, oy, z
                        ),
                    )
                )
            else:
                drawables.append(
                    (
                        floor_depth,
                        lambda lw=lw, ox=ox, oy=oy: self._draw_wells(p, to_screen, lw, ox, oy, 0.0),
                    )
                )

        drawables.sort(key=lambda d: d[0], reverse=True)
        for _depth, draw_fn in drawables:
            draw_fn()

        for side, pt in self.positions.items():
            if pt is None:
                continue
            color = _MOUNT_COLOR.get(side, QColor(S.INK))
            if is_3d:
                gantry_z = pt.z if pt.z else _GANTRY_HEIGHT_MM
                top_screen = to_screen(self._project(pt.x, pt.y, gantry_z))
                base_screen = to_screen(self._project(pt.x, pt.y, 0.0))
                pen = QPen(color)
                pen.setStyle(Qt.DashLine)
                pen.setWidthF(1.2)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawLine(QPointF(*base_screen), QPointF(*top_screen))
                p.setPen(QPen(QColor(S.PANEL), 1.0))
                p.setBrush(color.lighter(160))
                p.drawEllipse(QPointF(*base_screen), 3.5, 3.5)
                sx, sy = top_screen
            else:
                sx, sy = to_screen(self._project(pt.x, pt.y))
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
            p.drawPixmap(int(hx) + 8, int(hy) - 8, self._home_icon_pixmap())
            p.drawText(int(hx) + 22, int(hy) + 4, "home")

        if visible_marks:
            pen = QPen(_CAL_MARK_COLOR)
            pen.setWidthF(1.6)
            p.setPen(pen)
            half = _CAL_MARK_SIZE_MM / 2
            for mark, z in visible_marks:
                cx, cy = mark.point.x, mark.point.y
                x0, y0 = to_screen(self._project(cx - half, cy, z))
                x1, y1 = to_screen(self._project(cx + half, cy, z))
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
                x0, y0 = to_screen(self._project(cx, cy - half, z))
                x1, y1 = to_screen(self._project(cx, cy + half, z))
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

        tick_bounds = frame_bounds or plate_bounds or self._slots_bbox()
        if tick_bounds is not None:
            self._draw_dimension_ticks(p, to_screen, tick_bounds)

    def _draw_dimension_ticks(self, p: QPainter, to_screen, bounds: tuple) -> None:
        minx, miny, maxx, maxy = bounds
        span_x, span_y = maxx - minx, maxy - miny
        step_x = _nice_tick_step(span_x)
        step_y = _nice_tick_step(span_y)
        tick_len = 7

        p.setFont(QFont(S.UI_FONT, 7))
        pen = QPen(QColor(S.INK_MUTED))
        pen.setWidthF(1.0)
        p.setPen(pen)

        center = to_screen(self._project((minx + maxx) / 2, (miny + maxy) / 2))

        edge_mid = to_screen(self._project((minx + maxx) / 2, miny))
        ux, uy = edge_mid[0] - center[0], edge_mid[1] - center[1]
        ulen = math.hypot(ux, uy) or 1.0
        ux, uy = ux / ulen, uy / ulen
        x = math.ceil(minx / step_x) * step_x
        while x <= maxx + 1e-6:
            sx, sy = to_screen(self._project(x, miny))
            ex, ey = sx + ux * tick_len, sy + uy * tick_len
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))
            p.drawText(
                int(ex - 15),
                int(ey + (2 if uy >= 0 else -12)),
                30,
                12,
                Qt.AlignHCenter | Qt.AlignTop if uy >= 0 else Qt.AlignHCenter | Qt.AlignBottom,
                f"{x:g}",
            )
            x += step_x

        edge_mid = to_screen(self._project(minx, (miny + maxy) / 2))
        ux, uy = edge_mid[0] - center[0], edge_mid[1] - center[1]
        ulen = math.hypot(ux, uy) or 1.0
        ux, uy = ux / ulen, uy / ulen
        y = math.ceil(miny / step_y) * step_y
        while y <= maxy + 1e-6:
            sx, sy = to_screen(self._project(minx, y))
            ex, ey = sx + ux * tick_len, sy + uy * tick_len
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))
            p.drawText(
                int(ex - 32 if ux <= 0 else ex + 2),
                int(ey - 6),
                30,
                12,
                Qt.AlignRight | Qt.AlignVCenter if ux <= 0 else Qt.AlignLeft | Qt.AlignVCenter,
                f"{y:g}",
            )
            y += step_y


class DeckView(QWidget):
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
        self.btn_reset_view = QPushButton("Reset View")
        self.btn_reset_view.setIcon(
            icon_utils.icon("restart_circle", QColor(*TOKENS["flat_text"][:3]), size=16)
        )
        self.btn_reset_view.setIconSize(_ICON_SIZE)
        self.btn_reset_view.clicked.connect(lambda: self.canvas.reset_view())
        header.addWidget(self.btn_reset_view)
        grid_layout.addLayout(header)

        self.canvas = DeckCanvas()
        self.canvas.setToolTip("Drag to pan · right-drag to orbit (3D) · scroll to zoom")
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
