from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from ..geometry.coordinates import DeckPoint


class WellShape(Enum):
    CIRCULAR = "circular"
    RECTANGULAR = "rectangular"


class BottomShape(Enum):
    """Profile of the well's deepest point -- affects how much dead volume
    sits below the safe aspirate clearance, not the motion math itself."""
    FLAT = "flat"
    ROUND = "round"
    V = "v"


@dataclass(frozen=True)
class WellGeometry:
    """Physical shape of a well, shared by every well of a labware unless a
    specific well overrides it (e.g. an odd calibration well in a reservoir).

    ``depth_mm`` is measured from the well's opening (top) to its deepest
    point. ``bottom_clearance_mm`` is the default standoff kept above that
    deepest point when a routine resolves a well "at clearance" -- the usual
    reference for aspirating without dragging the tip through solids or
    crashing into a conical/round bottom.
    """
    shape: WellShape = WellShape.CIRCULAR
    diameter_mm: float = 0.0          # circular wells
    width_mm: float = 0.0             # rectangular wells, x
    length_mm: float = 0.0            # rectangular wells, y
    depth_mm: float = 0.0
    bottom: BottomShape = BottomShape.FLAT
    bottom_clearance_mm: float = 1.0
    max_volume_ul: float = 0.0

    def z_delta(self, ref: str, clearance_mm: float | None = None) -> float:
        """Deck-z offset from the well's top for a named reference point."""
        if ref == "top":
            return 0.0
        if ref == "bottom":
            return -self.depth_mm
        if ref == "clearance":
            clr = self.bottom_clearance_mm if clearance_mm is None else clearance_mm
            return -max(0.0, self.depth_mm - clr)
        raise ValueError(f"unknown well reference {ref!r} (expected top/bottom/clearance)")


@dataclass
class Well:
    """A named location in a labware.

    ``offset`` is the well's centre, relative to the labware origin, with z
    at the well's TOP (opening/rim) -- the one unambiguous, directly
    measurable datum. Bottom and clearance heights are derived from
    ``geometry.depth_mm`` on resolve, never baked into the offset itself.
    """
    name: str
    offset: DeckPoint
    geometry: WellGeometry = field(default_factory=WellGeometry)

    def at(self, ref: str = "top", clearance_mm: float | None = None) -> DeckPoint:
        return self.offset + DeckPoint(0, 0, self.geometry.z_delta(ref, clearance_mm))


_ROW_LETTERS = "ABCDEFGHIJKLMNOP"


@dataclass
class Labware:
    """Generic, data-driven labware: a named set of addressable wells.

    Build a uniform plate with ``Labware.grid`` (regular row/col pitch), or
    hand-list ``wells`` for irregular spacing -- mixed pitches, a reservoir
    with one big well, per-well geometry overrides, etc.
    """
    name: str
    wells: dict = field(default_factory=dict)
    slot: object = None  # a deck.Slot once placed

    def place(self, slot) -> None:
        self.slot = slot

    def well(self, name: str, ref: str = "top", clearance_mm: float | None = None) -> DeckPoint:
        """Absolute deck point for a well at the given reference height:
        "top" (opening/rim, the default here), "bottom" (deepest point), or
        "clearance" (a safe standoff above the bottom -- what routines use
        for aspirate/dispense by default)."""
        if self.slot is None:
            raise RuntimeError(f"labware {self.name!r} is not placed on the deck")
        return self.slot.origin + self.wells[name].at(ref, clearance_mm)

    @classmethod
    def grid(cls, name: str, *, rows: int, cols: int, origin: DeckPoint,
             row_spacing_mm: float, col_spacing_mm: float,
             geometry: WellGeometry | None = None) -> "Labware":
        """Uniform rows x cols grid, named the conventional way (A1, A2, ...,
        B1, ...). ``origin`` is well A1's centre (z at the well top),
        relative to the labware/slot origin; every well shares ``geometry``."""
        geometry = geometry or WellGeometry()
        wells = {}
        for r in range(rows):
            for c in range(cols):
                well_name = f"{_ROW_LETTERS[r]}{c + 1}"
                pos = DeckPoint(origin.x + c * col_spacing_mm,
                                origin.y + r * row_spacing_mm, origin.z)
                wells[well_name] = Well(well_name, pos, geometry)
        return cls(name=name, wells=wells)

    @classmethod
    def from_dict(cls, data: dict) -> "Labware":
        default_geometry = _geometry_from_dict(data.get("well_geometry", {}))
        if "grid" in data:
            g = data["grid"]
            return cls.grid(
                name=data["name"], rows=g["rows"], cols=g["cols"],
                origin=DeckPoint(g["origin"]["x"], g["origin"]["y"], g["origin"].get("z", 0.0)),
                row_spacing_mm=g["row_spacing_mm"], col_spacing_mm=g["col_spacing_mm"],
                geometry=default_geometry)
        wells = {}
        for n, o in data.get("wells", {}).items():
            offset = DeckPoint(o["x"], o["y"], o.get("z", 0.0))
            geometry = _geometry_from_dict(o["geometry"]) if "geometry" in o else default_geometry
            wells[n] = Well(n, offset, geometry)
        return cls(name=data["name"], wells=wells)


def _geometry_from_dict(d: dict) -> WellGeometry:
    if not d:
        return WellGeometry()
    return WellGeometry(
        shape=WellShape(d.get("shape", "circular")),
        diameter_mm=d.get("diameter_mm", 0.0),
        width_mm=d.get("width_mm", 0.0),
        length_mm=d.get("length_mm", 0.0),
        depth_mm=d.get("depth_mm", 0.0),
        bottom=BottomShape(d.get("bottom", "flat")),
        bottom_clearance_mm=d.get("bottom_clearance_mm", 1.0),
        max_volume_ul=d.get("max_volume_ul", 0.0))
