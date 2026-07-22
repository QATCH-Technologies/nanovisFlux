"""Deck visualization: slots, divider ribs, placed labware, and a live
marker per mount, projected either top-down ("2D", a plain blueprint) or
as a real 3D model ("3D": a proper orthographic camera that orbits the
deck, painter's-algorithm sorted so height and occlusion both come out
correctly -- see ``_project``, ``_camera_depth``). Still QPainter, not a
3D engine -- an orthographic camera projected by hand is plenty for a
deck laid out flat, and stays simple to reason about.

Both projections support the same camera controls: left-drag to pan,
right-drag to orbit (horizontal = azimuth/spin around the vertical axis,
vertical = elevation/tilt -- "2D" only has azimuth, since tilting a flat
blueprint doesn't mean anything), and the scroll wheel to zoom. See
``reset_view``.

In "3D", divider ribs and labware are drawn with real height (see
``_SEPARATOR_HEIGHT_MM``, ``_labware_height``), and each mount is drawn at
the gantry's actual height above the deck (``pt.z``, falling back to
``_GANTRY_HEIGHT_MM`` -- about 40cm -- when no live z is reported) with a
dashed projection line straight down to the deck point it's hovering over.

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

_CORNER_NOTCH_MM = 10.0     # square gap left empty at each end of a separator rib
_SEPARATOR_COLOR = QColor("#C9C3B2")   # solid rib filling the gap between adjacent slots
_SEPARATOR_HEIGHT_MM = 5.0  # divider ribs are raised material, not painted-on flat lines
_GANTRY_HEIGHT_MM = 400.0   # ~40cm: fallback mount height when no live z is reported

_ZOOM_MIN = 0.25
_ZOOM_MAX = 8.0
_ZOOM_STEP = 1.15           # scale factor applied per wheel notch
_DRAG_THRESHOLD_PX = 4      # movement below this still counts as a slot click
_SPIN_DEG_PER_PX = 0.5      # right-drag sensitivity (azimuth and elevation alike)
_ELEVATION_DEFAULT_DEG = 35.0
_ELEVATION_MIN_DEG = 8.0    # clamped away from a flat, edge-on side view
_ELEVATION_MAX_DEG = 88.0   # clamped away from a perfectly top-down view (degenerate box faces)


def _nice_tick_step(span: float, target_ticks: int = 6) -> float:
    """A "round" mm step (1/2/2.5/5 x a power of ten) giving roughly
    ``target_ticks`` ticks across ``span`` -- the usual auto-ruler rule."""
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
        self.positions: dict = {}  # MountSide -> DeckPoint | None
        self.selected_slot: str | None = None
        self._slot_paths: dict = {}  # name -> (QPainterPath, centroid)

        # -- camera: zoom/pan/orbit, layered on top of the auto-fit view
        # computed fresh each paint (see paintEvent) -- works the same in
        # both projections since it's applied to the already-projected
        # screen coordinates (pan/zoom) or before projection (azimuth/
        # elevation, a full 3D orbit around the deck; see _project).
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
        self.reset_view()

    def reset_view(self) -> None:
        """Back to the auto-fit camera: no zoom or pan, default orbit."""
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._azimuth_deg = 0.0
        self._elevation_deg = _ELEVATION_DEFAULT_DEG
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

    def _common_footprint(self):
        """The deck's most common slot (w, h) -- the "regular" slots (1-11
        in the example deck) as opposed to one-off oversized slots (e.g. a
        trash slot). None if there are no slots."""
        if not self.deck or not self.deck.slots:
            return None
        footprints = [self._slot_footprint(s) for s in self.deck.slots.values()]
        return max(set(footprints), key=footprints.count)

    def _slots_bbox(self):
        """(minx, miny, maxx, maxy) spanning every slot's own footprint --
        a fallback reference for the dimension ruler when the deck declares
        no margins (so plate/frame bounds aren't available)."""
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

    def _separator_segments(self, notch: float = None, min_overlap: float = 5.0,
                            max_gap: float = 30.0, thin_width: float = 1.0) -> list:
        """Deck-space (minx, miny, maxx, maxy) rects for the solid separator
        ribs between and around slots.

        Each rib runs along the straight edge between two facing slot
        corners but stops ``notch`` mm short at each end, leaving the
        corner itself empty (the square cutout) -- the rib is the space
        *between* the corner squares, not the squares themselves. Between
        two regular (common-footprint) slots the rib fills the slots'
        actual gap; a regular slot's side with no neighbour (the outer edge
        of the slots 1-11 block) still gets a rib of that same width,
        facing outward -- the separators around the outer perimeter. A
        regular slot bordering a one-off slot (e.g. the oversized trash
        slot) gets a thin ``thin_width`` mm rib centred in that gap instead,
        a lighter partial divider rather than a full structural joint."""
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
        # has_neighbor[i] = [left, right, front(-y), rear(+y)]
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
                                segments.append((mid - thin_width / 2, y0, mid + thin_width / 2, y1))
                    elif 0 <= ax0 - bx1 <= max_gap:
                        has_neighbor[i][0] = has_neighbor[j][1] = True
                        if y1 > y0:
                            if both_regular:
                                gap_widths.append(ax0 - bx1)
                                segments.append((bx1, y0, ax0, y1))
                            else:
                                mid = (bx1 + ax0) / 2
                                segments.append((mid - thin_width / 2, y0, mid + thin_width / 2, y1))

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
                                segments.append((x0, mid - thin_width / 2, x1, mid + thin_width / 2))
                    elif 0 <= ay0 - by1 <= max_gap:
                        has_neighbor[i][2] = has_neighbor[j][3] = True
                        if x1 > x0:
                            if both_regular:
                                gap_widths.append(ay0 - by1)
                                segments.append((x0, by1, x1, ay0))
                            else:
                                mid = (by1 + ay0) / 2
                                segments.append((x0, mid - thin_width / 2, x1, mid + thin_width / 2))

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
        """(minx, miny, maxx, maxy) of the plate's outer edge, built from
        deck.margins -- None if the deck declares no margins. Slots whose
        footprint matches the deck's most common one get the directional
        front/left/right/rear margin; any other size (e.g. an oversized
        trash slot) gets the flat "oversized" margin instead."""
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

    def _labware_height(self, lw) -> float:
        """Labware body height above the deck, in mm -- read from its
        wells' own z (``Well.offset.z`` is the well TOP's absolute deck
        height -- see deck/labware.py), the only per-labware height already
        tracked, so no new field is needed on ``Labware`` itself. 0 for a
        labware with no wells (no extrusion drawn)."""
        if lw is None or not lw.wells:
            return 0.0
        return max(well.offset.z for well in lw.wells.values())

    def _box_faces(self, ox: float, oy: float, w: float, h: float, height_mm: float,
                   top_color: QColor, side_color_a: QColor, side_color_b: QColor) -> list:
        """The visible faces of a ``height_mm``-tall extrusion of a
        footprint, as (depth, points, color) triples -- whichever 2 of the
        4 side faces currently face the camera (see ``_visible_side_faces``
        -- this changes as the view orbits) plus the top face, each with
        its OWN depth from its own centroid.

        Deliberately per-face rather than one draw call for the whole box:
        painter's-algorithm sorting by a single depth per *object* (e.g.
        the whole box, or the whole slot) can misorder things wherever two
        objects' silhouettes genuinely overlap on screen -- a farther box
        with enough height can have a corner that's actually nearer the
        camera than a shorter-but-closer object's, and no single scalar
        captures that. Sorting individual faces alongside every other face
        in the scene (see paintEvent) resolves the vast majority of those
        cases; only faces whose planes truly interpenetrate would still
        need per-pixel (z-buffer) resolution, which this QPainter-based
        renderer doesn't do."""
        faces = {
            "front": [(ox, oy, 0), (ox + w, oy, 0), (ox + w, oy, height_mm), (ox, oy, height_mm)],
            "back": [(ox, oy + h, 0), (ox + w, oy + h, 0),
                    (ox + w, oy + h, height_mm), (ox, oy + h, height_mm)],
            "left": [(ox, oy, 0), (ox, oy + h, 0), (ox, oy + h, height_mm), (ox, oy, height_mm)],
            "right": [(ox + w, oy, 0), (ox + w, oy + h, 0),
                     (ox + w, oy + h, height_mm), (ox + w, oy, height_mm)],
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
        top_pts = [(ox, oy, height_mm), (ox + w, oy, height_mm),
                  (ox + w, oy + h, height_mm), (ox, oy + h, height_mm)]
        out.append((self._camera_depth(ox + w / 2, oy + h / 2, height_mm), top_pts, top_color))
        return out

    def _draw_face(self, p: QPainter, to_screen, pts: list, color: QColor) -> None:
        """One flat quad, given its 3D (x, y, z) corners -- the shared
        primitive behind every filled shape in the scene (slot floors,
        divider ribs, box faces) so they can all be depth-sorted together
        as equally-sized units (see paintEvent)."""
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
        """Face-level drawables for one separator rib's 3D extrusion --
        see ``_box_faces``; ribs need the same per-face treatment as
        labware boxes so the two interleave correctly wherever they're
        close enough on screen to matter."""
        return self._box_faces(gminx, gminy, gmaxx - gminx, gmaxy - gminy, _SEPARATOR_HEIGHT_MM,
                               _SEPARATOR_COLOR.lighter(108), _SEPARATOR_COLOR.darker(118),
                               _SEPARATOR_COLOR.darker(106))

    def _draw_separator_rib_flat(self, p: QPainter, to_screen, gminx: float, gminy: float,
                                 gmaxx: float, gmaxy: float) -> None:
        """A separator rib in "2d": a flat fill (height doesn't show in
        plan view, so there's nothing to extrude)."""
        corners = [(gminx, gminy, 0.0), (gmaxx, gminy, 0.0), (gmaxx, gmaxy, 0.0), (gminx, gmaxy, 0.0)]
        self._draw_face(p, to_screen, corners, _SEPARATOR_COLOR)

    def _draw_slot_floor(self, p: QPainter, to_screen, name: str, common_footprint, scale: float) -> None:
        """A slot's own footprint: fill, border, and name label -- always
        flat at z=0. Its labware (if any and if it has height) is drawn
        separately as its own depth-sorted faces (see ``_box_faces`` and
        paintEvent) rather than bundled into this call, so a tall box can
        correctly interleave with whatever else is nearby on screen."""
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
        centroid = (sum(s[0] for s in screen_pts) / len(screen_pts),
                   sum(s[1] for s in screen_pts) / len(screen_pts))
        self._slot_paths[name] = (path, centroid)

        has_labware = name in self._labware_by_slot
        selected = name == self.selected_slot
        oversized = (w, h) != common_footprint
        draw_box = (self.projection == "iso"
                   and self._labware_height(self._labware_by_slot.get(name)) > 0)
        p.setBrush(QColor(S.PANEL) if draw_box
                  else (QColor("#E4EEE7") if has_labware else QColor(S.PANEL)))
        if selected:
            pen = QPen(QColor(S.INK))
            pen.setWidthF(2.2)
            p.setPen(pen)
        elif oversized:
            # Not part of the regular 1-11 grid (no separator ribs of its
            # own), so it keeps a plain physical-scale border instead.
            pen = QPen(QColor(S.BORDER_STRONG))
            pen.setWidthF(max(2.0 * scale, 1.0))
            p.setPen(pen)
        else:
            p.setPen(Qt.NoPen)
        p.drawPath(path)

        p.setPen(QColor(S.INK_MUTED))
        p.drawText(int(centroid[0] - 24), int(centroid[1] - 8), 48, 16, Qt.AlignCenter, name)

    def _draw_wells(self, p: QPainter, to_screen, lw, ox: float, oy: float, z: float) -> None:
        """A labware's well markers, all at the same z (its top surface in
        "3D", or 0 -- the deck floor -- in "2d"). Drawn as one depth-sorted
        unit since every well in a labware shares the same z: there is no
        internal ordering ambiguity to resolve between them."""
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(S.INK_MUTED))
        for well in lw.wells.values():
            wx = ox + well.offset.x
            wy = oy + well.offset.y
            wsx, wsy = to_screen(self._project(wx, wy, z))
            p.drawEllipse(QPointF(wsx, wsy), 1.5, 1.5)

    def _home_deck_point(self):
        """(x, y) the gantry's shared X/Y reference homes to -- the
        calibration's own answer for motor (0, 0), so the home marker
        automatically agrees with the live mount markers once homed rather
        than being a second, independently-guessed location. None without a
        calibration (motor (0, 0) has no known deck point)."""
        if self.robot is None or getattr(self.robot, "calibration", None) is None:
            return None
        try:
            return self.robot.calibration.motor_to_deck_xy(0, 0)
        except Exception:
            return None

    def _project(self, x: float, y: float, z: float = 0.0) -> tuple:
        """Deck (x, y, z) in mm -> unscaled screen-ish coords, +y screen-down.

        "2d" is a plain top-down blueprint: ``(x, -y)``, ``z`` unused (height
        doesn't foreshorten in plan view).

        "3D" is a real orthographic camera orbiting the deck: rotate (x, y)
        around the vertical (Z) axis by ``self._azimuth_deg`` (spin), then
        rotate the resulting depth/height plane around the (now-rotated) X
        axis by ``self._elevation_deg`` (tilt). At elevation 90 deg this
        collapses to the "2d" formula (straight down); at 0 deg it collapses
        to a pure side-on view (height only, no depth) -- see
        ``_ELEVATION_MIN_DEG``/``_MAX_DEG`` for why we never actually reach
        either extreme. ``y`` is deck depth (slot row "1" at y=0 in front,
        row "12" at max y in back -- see robot.example.yaml's deck: comment):
        the near corner (min x, min y) lands at the bottom of the screen,
        the far corner (max x, max y) at the top, so the front row renders
        nearest the viewer.
        """
        if self.projection != "iso":
            return (x, -y)
        az = math.radians(self._azimuth_deg)
        cos_a, sin_a = math.cos(az), math.sin(az)
        x1, y1 = x * cos_a - y * sin_a, x * sin_a + y * cos_a
        el = math.radians(self._elevation_deg)
        cos_e, sin_e = math.cos(el), math.sin(el)
        return (x1, -(y1 * sin_e + z * cos_e))

    def _camera_depth(self, x: float, y: float, z: float = 0.0) -> float:
        """Camera-space depth at deck point (x, y, z) -- larger means
        farther from the viewer. Rotated/tilted the same way ``_project``
        transforms points, so painter's-algorithm draw ordering (see
        ``paintEvent``) stays correct as the view orbits, not just in the
        unrotated default view. Only meaningful in "iso" -- "2d" has no
        real depth axis (everything is drawn flat, in an arbitrary but
        harmless order)."""
        if self.projection != "iso":
            return 0.0
        az = math.radians(self._azimuth_deg)
        cos_a, sin_a = math.cos(az), math.sin(az)
        x1, y1 = x * cos_a - y * sin_a, x * sin_a + y * cos_a
        el = math.radians(self._elevation_deg)
        cos_e, sin_e = math.cos(el), math.sin(el)
        return y1 * cos_e - z * sin_e

    def _visible_side_faces(self) -> list:
        """Which 2 of a box's 4 side faces (front/back/left/right) face the
        camera right now, so ``_box_faces``'s shading stays correct as the
        view orbits instead of always highlighting the faces that were
        nearest before rotation. Side-face visibility only depends on
        azimuth -- a vertical wall is either facing the camera's bearing or
        it isn't, regardless of how steeply we're looking down at it."""
        phi = math.radians(-self._azimuth_deg)
        cos_p, sin_p = math.cos(phi), math.sin(phi)
        base_x, base_y = -1.0, -1.0
        cam_x = base_x * cos_p - base_y * sin_p
        cam_y = base_x * sin_p + base_y * cos_p
        normals = {"front": (0.0, -1.0), "back": (0.0, 1.0),
                  "left": (-1.0, 0.0), "right": (1.0, 0.0)}
        ranked = sorted(normals, key=lambda n: -(normals[n][0] * cam_x + normals[n][1] * cam_y))
        return ranked[:2]

    # -- camera: pan (left-drag), orbit (right-drag), zoom (wheel) ---------
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
        if not self._drag_moved and (abs(delta.x()) > _DRAG_THRESHOLD_PX
                                     or abs(delta.y()) > _DRAG_THRESHOLD_PX):
            self._drag_moved = True
        if not self._drag_moved:
            return
        if self._drag_button == Qt.LeftButton:
            self._pan_x = self._drag_pan_origin[0] + delta.x()
            self._pan_y = self._drag_pan_origin[1] + delta.y()
        elif self._drag_button == Qt.RightButton:
            # Horizontal drag orbits around the deck (azimuth); vertical
            # drag tilts the camera up/down (elevation) -- the usual
            # click-drag "orbit" gesture for a 3D viewport.
            self._azimuth_deg = (self._drag_azimuth_origin
                                 + delta.x() * _SPIN_DEG_PER_PX) % 360
            self._elevation_deg = min(_ELEVATION_MAX_DEG, max(_ELEVATION_MIN_DEG,
                                      self._drag_elevation_origin - delta.y() * _SPIN_DEG_PER_PX))
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        # A left click that never turned into a drag still selects a slot.
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
        self._zoom = min(_ZOOM_MAX, max(_ZOOM_MIN, self._zoom * (_ZOOM_STEP ** steps)))
        self.update()

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

        common_footprint = self._common_footprint()
        is_3d = self.projection == "iso"
        all_pts = []
        for slot in self.deck.slots.values():
            w, h = self._slot_footprint(slot)
            ox, oy = slot.origin.x, slot.origin.y
            all_pts.extend(self._project(cx, cy) for cx, cy in
                           ((ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)))

        separator_segments = self._separator_segments()
        if is_3d:
            for name, lw in self._labware_by_slot.items():
                height = self._labware_height(lw)
                slot = self.deck.slots.get(name)
                if height <= 0 or slot is None:
                    continue
                w, h = self._slot_footprint(slot)
                ox, oy = slot.origin.x, slot.origin.y
                all_pts.extend(self._project(cx, cy, height) for cx, cy in
                               ((ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)))
            for gminx, gminy, gmaxx, gmaxy in separator_segments:
                all_pts.extend(self._project(cx, cy, _SEPARATOR_HEIGHT_MM) for cx, cy in
                               ((gminx, gminy), (gmaxx, gminy), (gmaxx, gmaxy), (gminx, gmaxy)))
            for pt in self.positions.values():
                if pt is not None:
                    all_pts.append(self._project(pt.x, pt.y, pt.z if pt.z else _GANTRY_HEIGHT_MM))

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

        home_xy = self._home_deck_point()
        home_proj = self._project(*home_xy) if home_xy is not None else None
        if home_proj is not None:
            all_pts.append(home_proj)

        xs = [pt[0] for pt in all_pts]
        ys = [pt[1] for pt in all_pts]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        pad = 34
        span_x = max(maxx - minx, 1e-6)
        span_y = max(maxy - miny, 1e-6)
        # Auto-fit scale for the current (rotated) content, then the user's
        # own zoom/pan camera layers on top -- see reset_view/wheelEvent/
        # mouseMoveEvent. Recomputing the fit from scratch each paint keeps
        # the orbit well-behaved (the fit always matches the current
        # azimuth/elevation) without fighting the persistent zoom/pan state.
        scale = min(
            max(self.width() - 2 * pad, 10) / span_x, max(self.height() - 2 * pad, 10) / span_y
        ) * self._zoom
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

        # Painter's algorithm over individual FACES (slot floors, labware
        # box faces, divider rib faces) rather than whole objects: draw
        # farthest first, nearest last, so a tall labware box is correctly
        # painted over anything behind it instead of a farther-but-later-
        # drawn object cutting across its front. Sorting per-face (not
        # per-slot/per-box) is what actually fixes that in the general
        # case -- see ``_box_faces`` for why a single depth per object
        # isn't enough once objects' silhouettes genuinely overlap.
        drawables = []
        for gminx, gminy, gmaxx, gmaxy in separator_segments:
            if is_3d:
                for depth, pts, color in self._rib_faces(gminx, gminy, gmaxx, gmaxy):
                    drawables.append((depth, lambda pts=pts, color=color:
                                     self._draw_face(p, to_screen, pts, color)))
            else:
                depth = self._camera_depth((gminx + gmaxx) / 2, (gminy + gmaxy) / 2)
                drawables.append((depth, lambda a=gminx, b=gminy, c=gmaxx, d=gmaxy:
                                 self._draw_separator_rib_flat(p, to_screen, a, b, c, d)))

        for name, slot in self.deck.slots.items():
            w, h = self._slot_footprint(slot)
            ox, oy = slot.origin.x, slot.origin.y
            floor_depth = self._camera_depth(ox + w / 2, oy + h / 2, 0.0)
            drawables.append((floor_depth, lambda n=name:
                             self._draw_slot_floor(p, to_screen, n, common_footprint, scale)))

            lw = self._labware_by_slot.get(name)
            if lw is None:
                continue
            height = self._labware_height(lw) if is_3d else 0.0
            if height > 0:
                for depth, pts, color in self._box_faces(ox, oy, w, h, height, QColor("#E4EEE7"),
                                                         QColor("#AFC9BA"), QColor("#C7DBCD")):
                    drawables.append((depth, lambda pts=pts, color=color:
                                     self._draw_face(p, to_screen, pts, color)))
                wells_depth = self._camera_depth(ox + w / 2, oy + h / 2, height)
                drawables.append((wells_depth, lambda lw=lw, ox=ox, oy=oy, z=height:
                                 self._draw_wells(p, to_screen, lw, ox, oy, z)))
            else:
                drawables.append((floor_depth, lambda lw=lw, ox=ox, oy=oy:
                                 self._draw_wells(p, to_screen, lw, ox, oy, 0.0)))

        drawables.sort(key=lambda d: d[0], reverse=True)
        for _depth, draw_fn in drawables:
            draw_fn()

        # Mount markers are drawn last, always on top -- a HUD-style aid so
        # the operator can always see where each tool is, rather than one
        # occasionally being hidden behind a tall piece of labware.
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
            p.drawText(int(hx) + 8, int(hy) + 4, "⌂ home")

        tick_bounds = frame_bounds or plate_bounds or self._slots_bbox()
        if tick_bounds is not None:
            self._draw_dimension_ticks(p, to_screen, tick_bounds)

    def _draw_dimension_ticks(self, p: QPainter, to_screen, bounds: tuple) -> None:
        """Ruler-style tick marks + mm labels along the deck's front edge
        (x dimension) and left edge (y dimension), so the projected view
        carries a sense of physical scale."""
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

        # X ruler along the front edge (y = miny): outward = away from the
        # deck's centre, toward the front edge's own midpoint.
        edge_mid = to_screen(self._project((minx + maxx) / 2, miny))
        ux, uy = edge_mid[0] - center[0], edge_mid[1] - center[1]
        ulen = math.hypot(ux, uy) or 1.0
        ux, uy = ux / ulen, uy / ulen
        x = math.ceil(minx / step_x) * step_x
        while x <= maxx + 1e-6:
            sx, sy = to_screen(self._project(x, miny))
            ex, ey = sx + ux * tick_len, sy + uy * tick_len
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))
            p.drawText(int(ex - 15), int(ey + (2 if uy >= 0 else -12)), 30, 12,
                      Qt.AlignHCenter | Qt.AlignTop if uy >= 0 else Qt.AlignHCenter | Qt.AlignBottom,
                      f"{x:g}")
            x += step_x

        # Y ruler along the left edge (x = minx).
        edge_mid = to_screen(self._project(minx, (miny + maxy) / 2))
        ux, uy = edge_mid[0] - center[0], edge_mid[1] - center[1]
        ulen = math.hypot(ux, uy) or 1.0
        ux, uy = ux / ulen, uy / ulen
        y = math.ceil(miny / step_y) * step_y
        while y <= maxy + 1e-6:
            sx, sy = to_screen(self._project(minx, y))
            ex, ey = sx + ux * tick_len, sy + uy * tick_len
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))
            p.drawText(int(ex - 32 if ux <= 0 else ex + 2), int(ey - 6), 30, 12,
                      Qt.AlignRight | Qt.AlignVCenter if ux <= 0 else Qt.AlignLeft | Qt.AlignVCenter,
                      f"{y:g}")
            y += step_y


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
        self.btn_reset_view = QPushButton("Reset View")
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
