"""Reusable physical definitions for standard laboratory labware.

This module defines immutable specifications for common grid-addressed
labware types, including well plates, reservoirs, and disposable-tip racks.
A definition describes the physical properties that are intrinsic to a
labware type—such as footprint, height, grid dimensions, spacing, well or
tip geometry, capacity, and the fixed offset of A1 from the labware origin.

Definitions are intentionally separate from placement. A definition can be
used to instantiate and place the same labware type on different deck slots,
with well and tip locations derived consistently from the definition rather
than encoded as individual coordinates.

The primary types are:

    GridLabwareDefinition:
        Common base definition for rectangular, row/column-addressed
        labware.

    WellPlateDefinition:
        Definition for liquid-handling well plates.

    ReservoirDefinition:
        Specialized well-plate definition for troughs and reservoirs.

    TipRackDefinition:
        Definition for disposable-tip racks, including tip geometry and
        capacity.

Definitions do not represent a particular physical placement on the deck.
Calling ``place`` on a concrete definition creates a :class:`Labware`
instance whose geometry is derived from the definition and associates it
with a specific deck slot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry.coordinates import DeckPoint
from ..tools.tips import TipGeometry
from .labware import BottomShape, Labware, WellGeometry, WellShape


@dataclass(frozen=True)
class GridLabwareDefinition:
    """Reusable physical definition for rectangular, grid-addressed labware.

    Defines the common geometry and addressing scheme shared by well plates,
    reservoirs, and tip racks. The grid is addressed conventionally by row
    and column (for example, ``A1``, ``A2``, ..., ``B1``), with spacing and
    the A1 reference position defined relative to the labware's own origin.

    ``grid_offset`` specifies the centre of A1 relative to the labware's
    top-left corner. ``stacking_offset`` provides an additional fixed offset
    used when the labware is mounted on an adapter, module, or other
    supporting labware rather than directly on a deck slot.

    Definitions describe a labware *type*, not a particular placement.
    Concrete subclasses use the definition to construct a :class:`Labware`
    instance when placed on a deck slot.

    Args:
        identifier: Unique identifier for the labware type.
        footprint_mm: Labware footprint as ``(length_x_mm, width_y_mm)``.
        height_mm: Overall physical height of the labware in millimetres.
        rows: Number of rows in the labware grid.
        cols: Number of columns in the labware grid.
        row_spacing_mm: Centre-to-centre spacing between adjacent rows.
        col_spacing_mm: Centre-to-centre spacing between adjacent columns.
        grid_offset: A1 centre position relative to the labware's top-left
            corner.
        stacking_offset: Additional grid offset applied when the labware is
            placed in a stacked configuration.
    """

    identifier: str
    footprint_mm: tuple  # (length_x_mm, width_y_mm)
    height_mm: float
    rows: int
    cols: int
    row_spacing_mm: float
    col_spacing_mm: float
    grid_offset: DeckPoint = field(default_factory=lambda: DeckPoint(0, 0, 0))
    stacking_offset: DeckPoint = field(default_factory=lambda: DeckPoint(0, 0, 0))

    def _grid_origin(self, stacked: bool) -> DeckPoint:
        """Return the grid origin appropriate for the placement mode.

        Args:
            stacked: Whether the labware is mounted on an adapter, module,
                or another supporting surface.

        Returns:
            The deck-space offset of the grid origin relative to the
            labware's own origin.
        """
        return self.grid_offset + self.stacking_offset if stacked else self.grid_offset

    def _check_fits(self, slot) -> None:
        sx, sy = slot.size
        lx, ly = self.footprint_mm
        if sx and sy and (lx > sx + 1e-6 or ly > sy + 1e-6):
            raise ValueError(
                f"{self.identifier!r} footprint {self.footprint_mm} mm exceeds "
                f"slot {slot.name!r} size {slot.size} mm"
            )


@dataclass(frozen=True)
class WellPlateDefinition(GridLabwareDefinition):
    """Physical definition for a grid-addressed liquid-handling well plate.

    Extends the common grid geometry with the dimensions, capacity, shape,
    and bottom characteristics required to describe individual wells.
    """

    well_volume_ul: float = 0.0
    well_shape: WellShape = WellShape.CIRCULAR
    well_diameter_mm: float = 0.0  # circular wells
    well_width_mm: float = 0.0  # rectangular wells, x
    well_length_mm: float = 0.0  # rectangular wells, y
    well_depth_mm: float = 0.0
    well_bottom: BottomShape = BottomShape.FLAT
    bottom_clearance_mm: float = 1.0

    def well_geometry(self) -> WellGeometry:
        """Construct the well geometry represented by this definition.

        Returns:
            A :class:`WellGeometry` containing the configured well shape,
            dimensions, depth, bottom geometry, clearance, and maximum
            volume.
        """
        return WellGeometry(
            shape=self.well_shape,
            diameter_mm=self.well_diameter_mm,
            width_mm=self.well_width_mm,
            length_mm=self.well_length_mm,
            depth_mm=self.well_depth_mm,
            bottom=self.well_bottom,
            bottom_clearance_mm=self.bottom_clearance_mm,
            max_volume_ul=self.well_volume_ul,
        )

    def place(self, slot, *, stacked: bool = False) -> Labware:
        """Instantiate and place the defined well plate on a deck slot.

        Args:
            slot: Deck slot on which the well plate will be placed.
            stacked: Whether to apply the definition's stacking offset.

        Returns:
            The newly created and placed :class:`Labware` instance.

        Raises:
            ValueError: If the well plate footprint exceeds the slot's
                defined footprint.
        """
        self._check_fits(slot)
        labware = Labware.grid(
            self.identifier,
            rows=self.rows,
            cols=self.cols,
            origin=self._grid_origin(stacked),
            row_spacing_mm=self.row_spacing_mm,
            col_spacing_mm=self.col_spacing_mm,
            geometry=self.well_geometry(),
        )
        labware.place(slot)
        return labware


@dataclass(frozen=True)
class ReservoirDefinition(WellPlateDefinition):
    """Physical definition for a trough or multi-channel reservoir.

    A reservoir uses the same geometric model as a well plate but is kept as
    a distinct definition type so higher-level routines can distinguish
    shared-pool reservoir behavior from independently addressable wells.
    """


@dataclass(frozen=True)
class TipRackDefinition(GridLabwareDefinition):
    """Physical definition for a grid-addressed disposable-tip rack.

    Defines the tip capacity and physical tip length in addition to the
    common grid and footprint geometry. Tip racks use the grid solely to
    describe tip positions; they do not model liquid-well shape or bottom
    geometry.
    """

    tip_volume_ul: float = 0.0
    tip_length_mm: float = 0.0  # nozzle-reference to tip end; feeds a TipGeometry

    def tip_geometry(self) -> TipGeometry:
        """Construct the tip geometry represented by this definition.

        Returns:
            A :class:`TipGeometry` containing the tip type identifier,
            physical length, and maximum supported liquid volume.
        """
        return TipGeometry(
            name=self.identifier, length_mm=self.tip_length_mm, max_volume_ul=self.tip_volume_ul
        )

    def place(self, slot, *, stacked: bool = False) -> Labware:
        """Instantiate and place the defined tip rack on a deck slot.

        Args:
            slot: Deck slot on which the tip rack will be placed.
            stacked: Whether to apply the definition's stacking offset.

        Returns:
            The newly created and placed :class:`Labware` instance.

        Raises:
            ValueError: If the tip rack footprint exceeds the slot's defined
                footprint.
        """
        self._check_fits(slot)
        # Tip wells aren't liquid-handling wells i.e., no shape/bottom to model,
        # just the top (first-contact) height carried by the grid itself.
        labware = Labware.grid(
            self.identifier,
            rows=self.rows,
            cols=self.cols,
            origin=self._grid_origin(stacked),
            row_spacing_mm=self.row_spacing_mm,
            col_spacing_mm=self.col_spacing_mm,
            geometry=WellGeometry(
                depth_mm=self.tip_length_mm,
                max_volume_ul=self.tip_volume_ul,
                bottom_clearance_mm=0.0,
            ),
        )
        labware.place(slot)
        return labware
