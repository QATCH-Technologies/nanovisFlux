"""PlungerCalibration: piecewise-linear steps<->volume interpolation from
empirically measured points, replacing PlungerModel's single linear factor
for whichever (pipette, tip) combination has been characterized -- see
tools/pipette.py's module-level design notes."""
from unittest.mock import MagicMock

import pytest

from src.core import AxisId, MountSide
from src.motion.mounts import Mount
from src.tools import Pipette, PlungerCalibration, PlungerCalibrationPoint, PlungerModel, TipGeometry


# -- construction / validation -------------------------------------------
def test_requires_at_least_two_points_per_direction():
    with pytest.raises(ValueError):
        PlungerCalibration.from_pairs(aspirate=[(0, 0.0)], dispense=[(0, 0.0), (1000, 50.0)])
    with pytest.raises(ValueError):
        PlungerCalibration.from_pairs(aspirate=[(0, 0.0), (1000, 50.0)], dispense=[(0, 0.0)])


def test_rejects_non_monotonic_points():
    with pytest.raises(ValueError, match="not monotonic"):
        PlungerCalibration.from_pairs(
            aspirate=[(0, 0.0), (1000, 50.0), (500, 60.0)],  # more volume, fewer microsteps
            dispense=[(0, 0.0), (1000, 50.0)],
        )


def test_sorts_out_of_order_input():
    cal = PlungerCalibration.from_pairs(
        aspirate=[(1000, 100.0), (0, 0.0), (2000, 220.0)],
        dispense=[(0, 0.0), (1000, 95.0)],
    )
    assert [p.volume_ul for p in cal.aspirate_points] == [0.0, 100.0, 220.0]


# -- interpolation ----------------------------------------------------------
@pytest.fixture
def cal() -> PlungerCalibration:
    return PlungerCalibration.from_pairs(
        aspirate=[(0, 0.0), (1000, 100.0), (2000, 220.0)],
        dispense=[(0, 0.0), (1000, 95.0), (2000, 200.0)],
    )


def test_exact_match_at_measured_points(cal):
    assert cal.microsteps_for_volume(0.0, aspirating=True) == 0
    assert cal.microsteps_for_volume(100.0, aspirating=True) == 1000
    assert cal.microsteps_for_volume(220.0, aspirating=True) == 2000
    assert cal.volume_for_microsteps(1000, aspirating=True) == pytest.approx(100.0)


def test_interpolates_between_points(cal):
    # Halfway between (0, 0uL) and (1000, 100uL) -> 500 microsteps.
    assert cal.microsteps_for_volume(50.0, aspirating=True) == 500
    # Dispense curve is deliberately different: (0,0uL)->(1000,95uL).
    assert cal.microsteps_for_volume(50.0, aspirating=False) == round(50.0 / 95.0 * 1000)


def test_extrapolates_using_nearest_segment_slope(cal):
    # Last aspirate segment: (1000, 100uL) -> (2000, 220uL), slope 1000/120 usteps/uL.
    expected = round(2000 + (300.0 - 220.0) * (2000 - 1000) / (220.0 - 100.0))
    assert cal.microsteps_for_volume(300.0, aspirating=True) == expected
    # Below the lowest point extrapolates the first segment instead of clamping to 0.
    expected_low = round(0 + (-10.0 - 0.0) * (1000 - 0) / (100.0 - 0.0))
    assert cal.microsteps_for_volume(-10.0, aspirating=True) == expected_low


def test_aspirate_and_dispense_use_different_curves(cal):
    aspirate_target = cal.microsteps_for_volume(50.0, aspirating=True)
    dispense_target = cal.microsteps_for_volume(50.0, aspirating=False)
    assert aspirate_target != dispense_target


# -- Pipette wiring -----------------------------------------------------------
def _pipette_with(plunger, tip_calibrations=None) -> tuple:
    robot = MagicMock()
    pip = Pipette(name="p300", plunger=plunger, max_volume_ul=300, tip_calibrations=tip_calibrations)
    mount = Mount(side=MountSide.LEFT)
    mount.attach(pip)
    pip.on_attach(mount, robot)
    return pip, robot


def _last_target(robot) -> dict:
    return robot.controller.linear_move.call_args[0][0]


def test_pipette_falls_back_to_linear_model_with_no_calibration():
    pip, robot = _pipette_with(PlungerModel(microsteps_per_ul=50.0, bottom_microsteps=1000))
    pip.aspirate(10.0)
    assert _last_target(robot) == {AxisId.B: 1500}  # 1000 + 10*50


def test_pipette_falls_back_when_tip_has_no_calibration_entry():
    tip = TipGeometry(name="unknown_tip", length_mm=50.0)
    pip, robot = _pipette_with(PlungerModel(microsteps_per_ul=50.0, bottom_microsteps=0),
                               tip_calibrations={})
    pip.current_tip = tip
    pip.aspirate(10.0)
    assert _last_target(robot) == {AxisId.B: 500}  # falls back: 0 + 10*50


def test_pipette_uses_calibration_for_current_tip():
    tip = TipGeometry(name="p300_tip", length_mm=51.7)
    cal = PlungerCalibration.from_pairs(
        aspirate=[(0, 0.0), (2000, 100.0)],
        dispense=[(0, 0.0), (1800, 100.0)],  # deliberately different from aspirate
    )
    pip, robot = _pipette_with(PlungerModel(microsteps_per_ul=50.0),
                               tip_calibrations={"p300_tip": cal})
    pip.current_tip = tip

    pip.aspirate(50.0)
    assert _last_target(robot) == {AxisId.B: 1000}  # aspirate curve: 50/100*2000

    pip.dispense(25.0)  # current_volume_ul: 50 -> 25
    assert _last_target(robot) == {AxisId.B: 450}  # DISPENSE curve: 25/100*1800, not aspirate's 500


def test_pipette_blow_out_uses_dispense_direction():
    tip = TipGeometry(name="p300_tip", length_mm=51.7)
    cal = PlungerCalibration.from_pairs(
        aspirate=[(0, 0.0), (2000, 100.0)],
        dispense=[(0, 10.0), (1800, 100.0)],  # dispense curve doesn't pass through (x, 0)
    )
    pip, robot = _pipette_with(PlungerModel(microsteps_per_ul=50.0),
                               tip_calibrations={"p300_tip": cal})
    pip.current_tip = tip
    pip.current_volume_ul = 40.0

    pip.blow_out()
    assert pip.current_volume_ul == 0.0
    assert _last_target(robot) == {AxisId.B: cal.microsteps_for_volume(0.0, aspirating=False)}
