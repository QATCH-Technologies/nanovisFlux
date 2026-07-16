import pytest

from src.core.axes import PhysicalAxis, VirtualAxis


def test_physical_axis_origin_is_zero_for_all_six_axes():
    origin = PhysicalAxis.origin()
    assert origin == {"A": 0.0, "B": 0.0, "C": 0.0, "X": 0.0, "Y": 0.0, "Z": 0.0}


def test_virtual_axis_origin_is_zero_for_xyz():
    assert VirtualAxis.origin() == {"X": 0.0, "Y": 0.0, "Z": 0.0}


def test_active_axis_tracks_last_engaged():
    PhysicalAxis.Z.active()
    assert PhysicalAxis.get_active() is PhysicalAxis.Z
    PhysicalAxis.A.active()
    assert PhysicalAxis.get_active() is PhysicalAxis.A


def test_set_envelope_and_query():
    PhysicalAxis.clear_all_envelopes()
    PhysicalAxis.X.set_envelope(0.0, 1000.0)
    assert PhysicalAxis.X.envelope() == (0.0, 1000.0)
    assert PhysicalAxis.X.has_envelope()
    assert PhysicalAxis.X.in_envelope(500.0)
    assert not PhysicalAxis.X.in_envelope(1500.0)


def test_axis_without_envelope_is_always_in_envelope():
    PhysicalAxis.clear_all_envelopes()
    assert PhysicalAxis.Y.envelope() is None
    assert not PhysicalAxis.Y.has_envelope()
    assert PhysicalAxis.Y.in_envelope(999999.0)


def test_set_envelope_rejects_non_positive_span():
    with pytest.raises(ValueError):
        PhysicalAxis.X.set_envelope(100.0, 100.0)
    with pytest.raises(ValueError):
        PhysicalAxis.X.set_envelope(100.0, 50.0)


def test_clear_envelope_removes_single_axis():
    PhysicalAxis.clear_all_envelopes()
    PhysicalAxis.X.set_envelope(0.0, 10.0)
    PhysicalAxis.Y.set_envelope(0.0, 10.0)
    PhysicalAxis.X.clear_envelope()
    assert not PhysicalAxis.X.has_envelope()
    assert PhysicalAxis.Y.has_envelope()
    PhysicalAxis.clear_all_envelopes()
