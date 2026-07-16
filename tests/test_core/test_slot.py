import pytest

from src.core.config_schema import SlotSchema
from src.core.slot import Slot


def _slot(**overrides):
    defaults = dict(x_offset_mm=0.0, y_offset_mm=0.0, width_mm=100.0, depth_mm=80.0)
    defaults.update(overrides)
    return Slot(slot_id="1", schema=SlotSchema(**defaults))


def test_new_slot_is_available():
    slot = _slot()
    assert slot.available
    assert slot.labware is None


def test_place_marks_slot_unavailable():
    slot = _slot()
    slot.place("plate")
    assert not slot.available
    assert slot.labware == "plate"


def test_place_on_occupied_slot_raises():
    slot = _slot()
    slot.place("plate")
    with pytest.raises(RuntimeError):
        slot.place("other_plate")


def test_clear_frees_slot():
    slot = _slot()
    slot.place("plate")
    slot.clear()
    assert slot.available


def test_corners_mm():
    slot = _slot(x_offset_mm=10.0, y_offset_mm=20.0, width_mm=100.0, depth_mm=80.0)
    assert slot.corners_mm() == [(10.0, 20.0), (110.0, 20.0), (110.0, 100.0), (10.0, 100.0)]


def test_is_trash_reflects_schema():
    assert not _slot().is_trash
    assert _slot(is_trash=True).is_trash
