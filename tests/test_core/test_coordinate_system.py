import pytest

from src.core.coordinate_system import MountOffsets, PhysicalEnvelope

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

MOUNT_OFFSETS = {
    "left": {"X": 32139.0, "Y": 29597.0, "Z": 110902.0, "A": 151268.0},
    "right": {"X": 36877.0, "Y": 29755.0, "Z": 110902.0, "A": 151250.0},
}


def test_from_corners_derives_min_max_bounds():
    envelope = PhysicalEnvelope.from_corners(CORNERS)
    assert envelope.axis_range("X") == (0.0, 60000.0)
    assert envelope.axis_range("Y") == (0.0, 52000.0)
    assert envelope.axis_range("Z") == (0.0, 160000.0)


def test_constant_axis_excluded_from_bounds():
    envelope = PhysicalEnvelope.from_corners(CORNERS)
    assert "A" not in envelope.known_axes()
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


def test_mount_offsets_apply():
    offsets = MountOffsets.from_config(MOUNT_OFFSETS)
    result = offsets.apply("left", {"X": 100.0, "Y": 200.0})
    assert result == {"X": 32239.0, "Y": 29797.0}


def test_mount_offsets_apply_differs_by_mount():
    offsets = MountOffsets.from_config(MOUNT_OFFSETS)
    left = offsets.apply("left", {"X": 0.0})
    right = offsets.apply("right", {"X": 0.0})
    assert left != right


def test_mount_offsets_remove_is_inverse_of_apply():
    offsets = MountOffsets.from_config(MOUNT_OFFSETS)
    original = {"X": 100.0, "Y": 200.0}
    shifted = offsets.apply("left", original)
    assert offsets.remove("left", shifted) == original


def test_mount_offsets_unknown_mount_raises():
    offsets = MountOffsets.from_config(MOUNT_OFFSETS)
    with pytest.raises(KeyError):
        offsets.apply("middle", {"X": 0.0})


def test_mount_offsets_rejects_unknown_axis():
    with pytest.raises(ValueError):
        MountOffsets.from_config({"left": {"Q": 1.0}})
