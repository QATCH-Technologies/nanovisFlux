import pytest

from src.interfaces.gamepad_teleop import (
    magnitude_to_speed,
    normalized_magnitude,
    should_reissue,
    trigger_pressed_fraction,
)


def test_normalized_magnitude_inside_deadzone_is_zero():
    assert normalized_magnitude(0.1, deadzone=0.2) == 0.0
    assert normalized_magnitude(-0.1, deadzone=0.2) == 0.0


def test_normalized_magnitude_at_deadzone_boundary_is_zero():
    assert normalized_magnitude(0.2, deadzone=0.2) == 0.0


def test_normalized_magnitude_full_deflection_is_one():
    assert normalized_magnitude(1.0, deadzone=0.2) == pytest.approx(1.0)
    assert normalized_magnitude(-1.0, deadzone=0.2) == pytest.approx(1.0)


def test_normalized_magnitude_scales_linearly_between_deadzone_and_full():
    # Halfway between deadzone (0.2) and full deflection (1.0) -> 0.6
    assert normalized_magnitude(0.6, deadzone=0.2) == pytest.approx(0.5)


def test_magnitude_to_speed_at_zero_is_floor():
    assert magnitude_to_speed(0.0, min_speed=500.0, max_speed=20000.0) == 500.0


def test_magnitude_to_speed_at_one_is_ceiling():
    assert magnitude_to_speed(1.0, min_speed=500.0, max_speed=20000.0) == 20000.0


def test_magnitude_to_speed_scales_linearly():
    assert magnitude_to_speed(0.5, min_speed=500.0, max_speed=20500.0) == pytest.approx(10500.0)


def test_trigger_pressed_fraction_released():
    assert trigger_pressed_fraction(-1.0) == 0.0


def test_trigger_pressed_fraction_fully_pressed():
    assert trigger_pressed_fraction(1.0) == 1.0


def test_trigger_pressed_fraction_midpoint():
    assert trigger_pressed_fraction(0.0) == pytest.approx(0.5)


def test_trigger_pressed_fraction_clamped():
    assert trigger_pressed_fraction(-2.0) == 0.0
    assert trigger_pressed_fraction(2.0) == 1.0


def test_should_reissue_on_direction_change():
    assert should_reissue(1.0, 1000.0, -1.0, 1000.0, threshold_speed=500.0) is True


def test_should_reissue_on_large_speed_change():
    assert should_reissue(1.0, 1000.0, 1.0, 2000.0, threshold_speed=500.0) is True


def test_should_not_reissue_on_small_speed_change():
    assert should_reissue(1.0, 1000.0, 1.0, 1100.0, threshold_speed=500.0) is False


def test_should_not_reissue_when_unchanged():
    assert should_reissue(1.0, 1000.0, 1.0, 1000.0, threshold_speed=500.0) is False
