import pytest

from src.core.axes import PhysicalAxis
from src.core.physical_envelope import PhysicalEnvelope

CORNERS = [
    {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0},
    {"X": 0.0, "Y": 0.0, "Z": 160000.0, "A": 0.0},
    {"X": 60000.0, "Y": 0.0, "Z": 0.0, "A": 0.0},
    {"X": 60000.0, "Y": 0.0, "Z": 160000.0, "A": 0.0},
    {"X": 60000.0, "Y": 52000.0, "Z": 0.0, "A": 0.0},
    {"X": 60000.0, "Y": 52000.0, "Z": 160000.0, "A": 0.0},
    {"X": 0.0, "Y": 52000.0, "Z": 0.0, "A": 0.0},
    {"X": 0.0, "Y": 52000.0, "Z": 160000.0, "A": 0.0},
]


def teardown_function(_function):
    PhysicalAxis.clear_all_envelopes()


def test_from_corners_derives_min_max_bounds():
    envelope = PhysicalEnvelope.from_corners(CORNERS)
    assert envelope.axis_range("X") == (0.0, 60000.0)
    assert envelope.axis_range("Y") == (0.0, 52000.0)
    assert envelope.axis_range("Z") == (0.0, 160000.0)


def test_bounds_are_stored_directly_on_the_physical_axis():
    PhysicalEnvelope.from_corners(CORNERS)
    assert PhysicalAxis.X.envelope() == (0.0, 60000.0)
    assert PhysicalAxis.X.in_envelope(30000.0)
    assert not PhysicalAxis.X.in_envelope(70000.0)


def test_constant_axis_excluded_from_bounds():
    envelope = PhysicalEnvelope.from_corners(CORNERS)
    assert "A" not in envelope.known_axes()
    assert not PhysicalAxis.A.has_envelope()
    with pytest.raises(KeyError):
        envelope.axis_range("A")


def test_span():
    envelope = PhysicalEnvelope.from_corners(CORNERS)
    assert envelope.span("X") == 60000.0


def test_contains_within_bounds():
    envelope = PhysicalEnvelope.from_corners(CORNERS)
    assert envelope.contains({"X": 30000.0, "Y": 26000.0, "Z": 80000.0})


def test_violations_outside_bounds():
    envelope = PhysicalEnvelope.from_corners(CORNERS)
    violations = envelope.violations({"X": 70000.0, "Y": 26000.0})
    assert violations == {"X": (70000.0, (0.0, 60000.0))}


def test_violations_ignores_uncalibrated_axis():
    envelope = PhysicalEnvelope.from_corners(CORNERS)
    assert envelope.violations({"A": 999999.0}) == {}


def test_from_corners_requires_at_least_two():
    with pytest.raises(ValueError):
        PhysicalEnvelope.from_corners([{"X": 0.0}])


def test_from_corners_rejects_unknown_axis():
    with pytest.raises(ValueError):
        PhysicalEnvelope.from_corners([{"Q": 0.0}, {"Q": 1.0}])


def test_constructing_a_new_envelope_replaces_the_previous_ones_bounds():
    PhysicalEnvelope.from_corners(CORNERS)
    assert PhysicalAxis.X.has_envelope()

    smaller = PhysicalEnvelope.from_corners([{"Y": 0.0}, {"Y": 1000.0}])
    assert not PhysicalAxis.X.has_envelope()
    assert smaller.axis_range("Y") == (0.0, 1000.0)
