"""WellGeometry.z_delta / Well.at / Labware.well: the vertical-reference and
well-resolution chain used to turn a named well address (e.g. "A1") plus a
ref ("top"/"bottom"/"clearance") into an absolute deck-space DeckPoint.
Nothing in the existing suite calls this chain directly -- routines/location.py
and gui/routine_model.py are the only production callers -- so its edge
cases (unplaced labware, unknown well name, unsupported ref, clearance
overrides) were untested."""

import pytest

from src.deck import Labware, Slot, Well, WellGeometry
from src.geometry import DeckPoint


# -- WellGeometry.z_delta ---------------------------------------------------
def test_z_delta_top_is_zero():
    geom = WellGeometry(depth_mm=12.0, bottom_clearance_mm=3.0)
    assert geom.z_delta("top") == 0.0


def test_z_delta_bottom_is_negative_full_depth():
    geom = WellGeometry(depth_mm=12.0)
    assert geom.z_delta("bottom") == -12.0


def test_z_delta_clearance_uses_configured_default():
    geom = WellGeometry(depth_mm=12.0, bottom_clearance_mm=3.0)
    assert geom.z_delta("clearance") == -9.0


def test_z_delta_clearance_override_beats_configured_default():
    geom = WellGeometry(depth_mm=12.0, bottom_clearance_mm=3.0)
    assert geom.z_delta("clearance", clearance_mm=5.0) == -7.0


def test_z_delta_clearance_clamps_when_override_exceeds_depth():
    # A clearance request deeper than the well itself clamps to the well
    # opening rather than reporting a position above "top".
    geom = WellGeometry(depth_mm=5.0)
    assert geom.z_delta("clearance", clearance_mm=50.0) == 0.0


def test_z_delta_unknown_ref_raises_value_error():
    geom = WellGeometry(depth_mm=12.0)
    with pytest.raises(ValueError, match="unknown well reference"):
        geom.z_delta("side")


# -- Well.at ------------------------------------------------------------
def test_well_at_top_is_the_well_offset_unchanged():
    well = Well("A1", DeckPoint(10, 20, 0), WellGeometry(depth_mm=12.0, bottom_clearance_mm=3.0))
    assert well.at("top") == DeckPoint(10, 20, 0)


def test_well_at_bottom_and_clearance_apply_z_delta_to_the_offset():
    well = Well("A1", DeckPoint(10, 20, 5), WellGeometry(depth_mm=12.0, bottom_clearance_mm=3.0))
    assert well.at("bottom") == DeckPoint(10, 20, -7.0)  # 5 - 12
    assert well.at("clearance") == DeckPoint(10, 20, -4.0)  # 5 - 9
    assert well.at("clearance", clearance_mm=2.0) == DeckPoint(10, 20, -5.0)  # 5 - 10


def test_well_at_default_ref_is_top():
    well = Well("A1", DeckPoint(1, 2, 3), WellGeometry(depth_mm=12.0))
    assert well.at() == well.at("top")


# -- Labware.well ---------------------------------------------------------
def _placed_labware() -> Labware:
    geometry = WellGeometry(depth_mm=10.0, bottom_clearance_mm=2.0, max_volume_ul=200.0)
    labware = Labware.grid(
        "plate",
        rows=2,
        cols=2,
        origin=DeckPoint(5.0, 5.0, 0.0),
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
        geometry=geometry,
    )

    slot = Slot(name="1", origin=DeckPoint(100.0, 200.0, 0.0), size=(50.0, 50.0))
    labware.place(slot)
    return labware


def test_well_raises_runtime_error_when_not_placed():
    labware = Labware.grid(
        "plate",
        rows=1,
        cols=1,
        origin=DeckPoint(0, 0, 0),
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
    )
    with pytest.raises(RuntimeError, match="not placed on the deck"):
        labware.well("A1")


def test_well_raises_key_error_for_unknown_well_name():
    labware = _placed_labware()
    with pytest.raises(KeyError):
        labware.well("Z9")


def test_well_raises_value_error_for_unsupported_ref():
    labware = _placed_labware()
    with pytest.raises(ValueError, match="unknown well reference"):
        labware.well("A1", "side")


def test_well_resolves_absolute_position_including_row_flip_and_slot_origin():
    labware = _placed_labware()
    # Grid rows are flipped against the slot height (50mm) during place(), so
    # A1 (grid row 0, local y=5) ends up at slot-relative y = 50 - 5 = 45,
    # then offset by the slot's own deck-space origin.
    assert labware.well("A1", "top") == DeckPoint(105.0, 245.0, 0.0)
    assert labware.well("B1", "top") == DeckPoint(105.0, 236.0, 0.0)  # local y=14 -> 50-14=36


def test_well_bottom_and_clearance_apply_the_well_geometry():
    labware = _placed_labware()
    assert labware.well("A1", "bottom") == DeckPoint(105.0, 245.0, -10.0)
    assert labware.well("A1", "clearance") == DeckPoint(105.0, 245.0, -8.0)  # depth 10 - clr 2


def test_well_clearance_override_propagates_through_to_the_geometry():
    labware = _placed_labware()
    assert labware.well("A1", "clearance", clearance_mm=3.0) == DeckPoint(105.0, 245.0, -7.0)
