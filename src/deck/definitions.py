"""Standard labware type definitions.

A definition is the reusable physical spec of a piece of labware -- the
things a vendor datasheet gives you: footprint, height, well/tip grid,
volume, shape, spacing, and the fixed offset from the labware's own corner
to well A1. Declare one per labware type, then ``place`` it on any slot --
the well/tip offsets are computed from the definition, never hand-picked.
"""
from __future__ import annotations
from dataclasses import dataclass
from ..geometry.coordinates import DeckPoint
from ..tools.tips import TipGeometry
from .labware import Labware, WellGeometry, WellShape, BottomShape


@dataclass(frozen=True)
class GridLabwareDefinition:
    """Shared shape for grid-addressed labware (well plates, reservoirs,
    tip racks): a rectangular footprint holding a rows x cols grid, named
    the conventional way (A1, A2, ..., B1, ...).

    ``grid_offset`` is well/tip A1's centre (z at its top), relative to the
    labware's own origin corner -- a fixed property of the labware type,
    independent of which slot it ends up in.

    ``stacking_offset`` is only added when this labware sits on an adapter,
    module, or another piece of labware instead of directly on a bare deck
    slot (``place(..., stacked=True)``); it is the zero vector for the
    common case.

    Not meant to be instantiated directly -- use WellPlateDefinition,
    ReservoirDefinition, or TipRackDefinition.
    """
    identifier: str
    footprint_mm: tuple           # (length_x_mm, width_y_mm)
    height_mm: float
    rows: int
    cols: int
    row_spacing_mm: float
    col_spacing_mm: float
    grid_offset: DeckPoint = DeckPoint(0, 0, 0)
    stacking_offset: DeckPoint = DeckPoint(0, 0, 0)

    def _grid_origin(self, stacked: bool) -> DeckPoint:
        return self.grid_offset + self.stacking_offset if stacked else self.grid_offset

    def _check_fits(self, slot) -> None:
        sx, sy = slot.size
        lx, ly = self.footprint_mm
        if sx and sy and (lx > sx + 1e-6 or ly > sy + 1e-6):
            raise ValueError(
                f"{self.identifier!r} footprint {self.footprint_mm} mm exceeds "
                f"slot {slot.name!r} size {slot.size} mm")


@dataclass(frozen=True)
class WellPlateDefinition(GridLabwareDefinition):
    """A standard well plate (e.g. a 96-well flat-bottom plate)."""
    well_volume_ul: float = 0.0
    well_shape: WellShape = WellShape.CIRCULAR
    well_diameter_mm: float = 0.0     # circular wells
    well_width_mm: float = 0.0        # rectangular wells, x
    well_length_mm: float = 0.0       # rectangular wells, y
    well_depth_mm: float = 0.0
    well_bottom: BottomShape = BottomShape.FLAT
    bottom_clearance_mm: float = 1.0

    def well_geometry(self) -> WellGeometry:
        return WellGeometry(shape=self.well_shape, diameter_mm=self.well_diameter_mm,
                            width_mm=self.well_width_mm, length_mm=self.well_length_mm,
                            depth_mm=self.well_depth_mm, bottom=self.well_bottom,
                            bottom_clearance_mm=self.bottom_clearance_mm,
                            max_volume_ul=self.well_volume_ul)

    def place(self, slot, *, stacked: bool = False) -> Labware:
        self._check_fits(slot)
        labware = Labware.grid(self.identifier, rows=self.rows, cols=self.cols,
                               origin=self._grid_origin(stacked),
                               row_spacing_mm=self.row_spacing_mm,
                               col_spacing_mm=self.col_spacing_mm,
                               geometry=self.well_geometry())
        labware.place(slot)
        return labware


@dataclass(frozen=True)
class ReservoirDefinition(WellPlateDefinition):
    """A trough/reservoir. Physically the same shape as a well plate --
    commonly a 1 x N grid of long wells sharing one liquid pool -- kept as
    its own type since routines may want to branch on it (e.g. treat every
    "well" as drawing from the same pool rather than N independent ones)."""


@dataclass(frozen=True)
class TipRackDefinition(GridLabwareDefinition):
    """A standard tip rack."""
    tip_volume_ul: float = 0.0
    tip_length_mm: float = 0.0    # nozzle-reference to tip end; feeds a TipGeometry

    def tip_geometry(self) -> TipGeometry:
        return TipGeometry(name=self.identifier, length_mm=self.tip_length_mm,
                           max_volume_ul=self.tip_volume_ul)

    def place(self, slot, *, stacked: bool = False) -> Labware:
        self._check_fits(slot)
        # Tip wells aren't liquid-handling wells -- no shape/bottom to model,
        # just the top (first-contact) height carried by the grid itself.
        labware = Labware.grid(self.identifier, rows=self.rows, cols=self.cols,
                               origin=self._grid_origin(stacked),
                               row_spacing_mm=self.row_spacing_mm,
                               col_spacing_mm=self.col_spacing_mm,
                               geometry=WellGeometry(depth_mm=self.tip_length_mm,
                                                      max_volume_ul=self.tip_volume_ul,
                                                      bottom_clearance_mm=0.0))
        labware.place(slot)
        return labware
