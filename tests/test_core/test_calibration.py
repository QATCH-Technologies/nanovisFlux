import pytest

from src.core.calibration import Calibration, derive_axis_calibration

CONFIG = {
    "X": {"steps_per_mm": 160.0, "home_offset_mm": 0.0},
    "Y": {"steps_per_mm": 160.0, "home_offset_mm": 5.0},
    "Z": {"steps_per_mm": 400.0, "home_offset_mm": 0.0},
}


def test_mm_to_steps():
    cal = Calibration.from_config(CONFIG)
    assert cal.mm_to_steps({"X": 10.0}) == {"X": 1600}


def test_mm_to_steps_applies_home_offset():
    cal = Calibration.from_config(CONFIG)
    assert cal.mm_to_steps({"Y": 10.0}) == {"Y": round((10.0 + 5.0) * 160.0)}


def test_steps_to_mm_round_trip():
    cal = Calibration.from_config(CONFIG)
    original = {"X": 12.5, "Z": 3.0}
    steps = cal.mm_to_steps(original)
    back = cal.steps_to_mm(steps)
    for axis, mm in original.items():
        assert back[axis] == pytest.approx(mm, abs=1e-3)


def test_delta_mm_to_steps_ignores_home_offset():
    cal = Calibration.from_config(CONFIG)
    assert cal.delta_mm_to_steps({"Y": 10.0}) == {"Y": 1600}


def test_unknown_axis_raises():
    cal = Calibration.from_config(CONFIG)
    with pytest.raises(KeyError):
        cal.mm_to_steps({"Q": 1.0})


def test_unknown_axis_in_config_rejected():
    with pytest.raises(ValueError):
        Calibration.from_config({"Q": {"steps_per_mm": 1.0}})


def test_derive_axis_calibration_steps_per_mm():
    cal = derive_axis_calibration(reference_mm=0.0, reference_steps=0.0, target_mm=100.0, target_steps=16000.0)
    assert cal.steps_per_mm == pytest.approx(160.0)
    assert cal.home_offset_mm == pytest.approx(0.0)


def test_derive_axis_calibration_with_nonzero_offset():
    cal = derive_axis_calibration(
        reference_mm=10.0, reference_steps=1600.0, target_mm=110.0, target_steps=17600.0
    )
    assert cal.steps_per_mm == pytest.approx(160.0)
    # round-trips: (mm + home_offset) * steps_per_mm == steps at both reference points
    assert (10.0 + cal.home_offset_mm) * cal.steps_per_mm == pytest.approx(1600.0)
    assert (110.0 + cal.home_offset_mm) * cal.steps_per_mm == pytest.approx(17600.0)


def test_derive_axis_calibration_usable_directly_in_calibration():
    cal_schema = derive_axis_calibration(0.0, 0.0, 100.0, 16000.0)
    cal = Calibration({"X": cal_schema})
    assert cal.mm_to_steps({"X": 50.0}) == {"X": 8000}


def test_derive_axis_calibration_rejects_zero_mm_delta():
    with pytest.raises(ValueError):
        derive_axis_calibration(reference_mm=5.0, reference_steps=0.0, target_mm=5.0, target_steps=100.0)
