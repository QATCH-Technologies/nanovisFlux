"""GridLabwareDefinition/WellPlateDefinition/TipRackDefinition/
ReservoirDefinition: reusable physical specs that build a placed Labware via
.place(slot, stacked=...). None of these classes were previously exercised
directly by any test (robot.load() tests use hand-built Labware/mock
definitions instead), so .place()'s footprint-fit check, the stacked vs.
unstacked grid-origin math, and the well/tip geometry it attaches were all
untested."""

import pytest

from src.deck import (
    BottomShape,
    ReservoirDefinition,
    Slot,
    TipRackDefinition,
    WellPlateDefinition,
    WellShape,
)
from src.geometry import DeckPoint


def _slot(size=(127.76, 85.9), origin=(0.0, 0.0)) -> Slot:
    return Slot(name="1", origin=DeckPoint(*origin), size=size)


# -- GridLabwareDefinition._check_fits (via WellPlateDefinition.place) -----
def test_check_fits_raises_when_footprint_exceeds_slot():
    defn = WellPlateDefinition(
        identifier="oversized_plate",
        footprint_mm=(150.0, 100.0),
        height_mm=14.0,
        rows=1,
        cols=1,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
    )
    with pytest.raises(ValueError, match="oversized_plate") as excinfo:
        defn.place(_slot(size=(127.76, 85.9)))
    assert "1" in str(excinfo.value)  # names the offending slot too


def test_check_fits_allows_footprint_matching_slot_exactly():
    defn = WellPlateDefinition(
        identifier="exact_fit_plate",
        footprint_mm=(127.76, 85.9),
        height_mm=14.0,
        rows=1,
        cols=1,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
    )
    labware = defn.place(_slot(size=(127.76, 85.9)))
    assert labware.slot is not None


def test_check_fits_skips_when_slot_has_no_footprint():
    # A slot with no declared size (0.0, 0.0) can't be fit-checked, so an
    # otherwise-oversized definition is still allowed to place.
    slot = Slot(name="undeclared", origin=DeckPoint(0, 0))
    defn = WellPlateDefinition(
        identifier="huge_plate",
        footprint_mm=(500.0, 500.0),
        height_mm=14.0,
        rows=1,
        cols=1,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
    )
    labware = defn.place(slot)  # does not raise
    assert labware.slot is slot


# -- GridLabwareDefinition._grid_origin (stacked vs. unstacked) ------------
def _stackable_defn() -> WellPlateDefinition:
    return WellPlateDefinition(
        identifier="plate",
        footprint_mm=(0.0, 0.0),
        height_mm=14.0,
        rows=1,
        cols=1,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
        grid_offset=DeckPoint(10.0, 20.0, 1.0),
        stacking_offset=DeckPoint(5.0, 5.0, 2.0),
    )


def test_unstacked_place_uses_grid_offset_only():
    # size (0.0, 0.0) so _check_fits is skipped and no row-flip is applied.
    slot = Slot(name="1", origin=DeckPoint(100.0, 200.0))
    labware = _stackable_defn().place(slot, stacked=False)
    assert labware.well("A1") == DeckPoint(110.0, 220.0, 1.0)


def test_stacked_place_adds_stacking_offset():
    slot = Slot(name="1", origin=DeckPoint(100.0, 200.0))
    labware = _stackable_defn().place(slot, stacked=True)
    assert labware.well("A1") == DeckPoint(115.0, 225.0, 3.0)


# -- WellPlateDefinition.well_geometry / .place -----------------------------
def test_well_geometry_maps_all_configured_fields():
    defn = WellPlateDefinition(
        identifier="plate96",
        footprint_mm=(0.0, 0.0),
        height_mm=14.0,
        rows=8,
        cols=12,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
        well_volume_ul=360.0,
        well_shape=WellShape.RECTANGULAR,
        well_width_mm=8.0,
        well_length_mm=8.0,
        well_depth_mm=10.9,
        well_bottom=BottomShape.V,
        bottom_clearance_mm=1.5,
    )
    geom = defn.well_geometry()
    assert geom.shape is WellShape.RECTANGULAR
    assert geom.width_mm == 8.0
    assert geom.length_mm == 8.0
    assert geom.depth_mm == 10.9
    assert geom.bottom is BottomShape.V
    assert geom.bottom_clearance_mm == 1.5
    assert geom.max_volume_ul == 360.0


def test_well_plate_definition_place_builds_full_named_grid():
    defn = WellPlateDefinition(
        identifier="plate96",
        footprint_mm=(127.76, 85.9),
        height_mm=14.0,
        rows=8,
        cols=12,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
        well_volume_ul=360.0,
        well_diameter_mm=6.4,
        well_depth_mm=10.9,
    )
    labware = defn.place(_slot())
    assert labware.name == "plate96"
    assert set(labware.wells) == {f"{r}{c}" for r in "ABCDEFGH" for c in range(1, 13)}
    a1_geometry = labware.wells["A1"].geometry
    assert a1_geometry.max_volume_ul == 360.0
    assert a1_geometry.diameter_mm == 6.4
    assert a1_geometry.depth_mm == 10.9


# -- ReservoirDefinition (shares WellPlateDefinition placement logic) ------
def test_reservoir_definition_places_like_a_well_plate_but_keeps_its_own_type():
    defn = ReservoirDefinition(
        identifier="trough_12",
        footprint_mm=(127.76, 85.9),
        height_mm=31.4,
        rows=1,
        cols=12,
        row_spacing_mm=0.0,
        col_spacing_mm=9.0,
        well_volume_ul=22000.0,
    )
    labware = defn.place(_slot())
    assert len(labware.wells) == 12
    assert type(defn) is ReservoirDefinition
    assert isinstance(defn, WellPlateDefinition)  # reuses well_geometry()/place()


# -- TipRackDefinition.tip_geometry / .place --------------------------------
def test_tip_rack_definition_check_fits_raises_when_oversized():
    defn = TipRackDefinition(
        identifier="big_tips",
        footprint_mm=(150.0, 100.0),
        height_mm=60.0,
        rows=1,
        cols=1,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
    )
    with pytest.raises(ValueError, match="big_tips"):
        defn.place(_slot(size=(127.76, 85.9)))


def test_tip_rack_definition_place_builds_tip_wells_not_liquid_wells():
    defn = TipRackDefinition(
        identifier="tips_300",
        footprint_mm=(127.76, 85.9),
        height_mm=60.0,
        rows=8,
        cols=12,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
        tip_volume_ul=300.0,
        tip_length_mm=51.7,
    )
    labware = defn.place(_slot())
    assert len(labware.wells) == 96
    a1_geometry = labware.wells["A1"].geometry
    # Tip wells carry only depth/volume/clearance -- no shape or bottom
    # profile since tips aren't modeled as liquid-handling wells.
    assert a1_geometry.depth_mm == 51.7
    assert a1_geometry.max_volume_ul == 300.0
    assert a1_geometry.bottom_clearance_mm == 0.0


def test_tip_rack_definition_tip_geometry_matches_configured_values():
    defn = TipRackDefinition(
        identifier="tips_300",
        footprint_mm=(0.0, 0.0),
        height_mm=60.0,
        rows=1,
        cols=1,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
        tip_volume_ul=300.0,
        tip_length_mm=51.7,
    )
    tip = defn.tip_geometry()
    assert tip.name == "tips_300"
    assert tip.length_mm == 51.7
    assert tip.max_volume_ul == 300.0
