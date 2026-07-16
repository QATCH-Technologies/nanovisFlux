import pytest

from src.core.coordinate_system import DeckCalibration, MountOffsets, PhysicalEnvelope

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


DECK_CALIBRATION_CONFIG = {
    "origin_steps": {"x": 0.0, "y": 0.0},
    "x_reference_steps": {"x": 21320.0},
    "x_reference_mm": 123.0,
    "y_reference_steps": {"y": 14478.0},
    "y_reference_mm": 81.0,
}


def test_deck_calibration_scales_from_origin():
    deck_cal = DeckCalibration.from_config(DECK_CALIBRATION_CONFIG)
    steps = deck_cal.mm_to_steps(0.0, 0.0)
    assert steps["X"] == pytest.approx(0.0)
    assert steps["Y"] == pytest.approx(0.0)


def test_deck_calibration_matches_reference_points():
    deck_cal = DeckCalibration.from_config(DECK_CALIBRATION_CONFIG)
    assert deck_cal.mm_to_steps(123.0, 0.0)["X"] == pytest.approx(21320.0)
    assert deck_cal.mm_to_steps(0.0, 81.0)["Y"] == pytest.approx(14478.0)


def test_deck_calibration_no_home_offset_field():
    # DeckCalibration has no home_offset_mm concept -- the origin reading is
    # the absolute answer, nothing further is added.
    deck_cal = DeckCalibration.from_config(DECK_CALIBRATION_CONFIG)
    assert not hasattr(deck_cal, "home_offset_mm")


def test_deck_calibration_interpolates_linearly():
    deck_cal = DeckCalibration.from_config(DECK_CALIBRATION_CONFIG)
    steps = deck_cal.mm_to_steps(61.5, 40.5)
    assert steps["X"] == pytest.approx(21320.0 / 2)
    assert steps["Y"] == pytest.approx(14478.0 / 2)


def test_deck_calibration_captures_skew_when_reference_has_cross_axis_component():
    # If the X-reference point also shifted a bit in Y (deck not perfectly
    # aligned with the gantry), that skew should carry into every deck-X move.
    skewed_config = {
        "origin_steps": {"x": 0.0, "y": 0.0},
        "x_reference_steps": {"x": 21320.0, "y": 100.0},
        "x_reference_mm": 123.0,
        "y_reference_steps": {"y": 14478.0},
        "y_reference_mm": 81.0,
    }
    deck_cal = DeckCalibration.from_config(skewed_config)
    steps = deck_cal.mm_to_steps(123.0, 0.0)
    assert steps["Y"] == pytest.approx(100.0)


def test_deck_calibration_nonzero_origin():
    config = {
        "origin_steps": {"x": 500.0, "y": 250.0},
        "x_reference_steps": {"x": 21820.0, "y": 250.0},
        "x_reference_mm": 123.0,
        "y_reference_steps": {"x": 500.0, "y": 14728.0},
        "y_reference_mm": 81.0,
    }
    deck_cal = DeckCalibration.from_config(config)
    steps = deck_cal.mm_to_steps(0.0, 0.0)
    assert steps == {"X": 500.0, "Y": 250.0}


def test_deck_calibration_rejects_zero_mm_reference():
    with pytest.raises(ValueError):
        DeckCalibration.from_three_points(
            origin_steps={"X": 0.0, "Y": 0.0},
            x_reference_steps={"X": 100.0},
            x_reference_mm=0.0,
            y_reference_steps={"Y": 100.0},
            y_reference_mm=81.0,
        )


def test_deck_calibration_rejects_unknown_axis():
    with pytest.raises(ValueError):
        DeckCalibration.from_config(
            {
                "origin_steps": {"q": 0.0},
                "x_reference_steps": {"x": 100.0},
                "x_reference_mm": 10.0,
                "y_reference_steps": {"y": 100.0},
                "y_reference_mm": 10.0,
            }
        )
