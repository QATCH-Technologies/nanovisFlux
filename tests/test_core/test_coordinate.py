import pytest

from src.common.calibration import Calibration
from src.core.coordinate import PhysicalCoordinate, VirtualCoordinate
from src.core.coordinate_system import DeckCalibration

Z_CALIBRATION = Calibration.from_config({"Z": {"steps_per_mm": 400.0, "home_offset_mm": 0.0}})

DECK_CALIBRATION = DeckCalibration.from_config(
    {
        "origin_steps": {"x": 0.0, "y": 0.0},
        "x_reference_steps": {"x": 21320.0},
        "x_reference_mm": 123.0,
        "y_reference_steps": {"y": 14478.0},
        "y_reference_mm": 81.0,
    }
)


def test_virtual_coordinate_to_steps():
    virtual = VirtualCoordinate(x=123.0, y=81.0, z=10.0)
    physical = virtual.to_steps(DECK_CALIBRATION, Z_CALIBRATION)
    assert physical.x == pytest.approx(21320.0)
    assert physical.y == pytest.approx(14478.0)
    assert physical.z == pytest.approx(4000.0)


def test_physical_coordinate_to_mm_is_inverse_of_to_steps():
    virtual = VirtualCoordinate(x=61.5, y=40.5, z=5.0)
    physical = virtual.to_steps(DECK_CALIBRATION, Z_CALIBRATION)
    round_tripped = physical.to_mm(DECK_CALIBRATION, Z_CALIBRATION)
    assert round_tripped.x == pytest.approx(61.5)
    assert round_tripped.y == pytest.approx(40.5)
    assert round_tripped.z == pytest.approx(5.0)


def test_physical_coordinate_as_steps_omits_unset_axes():
    physical = PhysicalCoordinate(x=1.0, y=2.0)
    assert physical.as_steps() == {"X": 1.0, "Y": 2.0}


def test_physical_coordinate_from_steps_round_trips_as_steps():
    steps = {"X": 1.0, "Y": 2.0, "Z": 3.0, "A": 4.0}
    physical = PhysicalCoordinate.from_steps(steps)
    assert physical.as_steps() == steps


def test_physical_coordinate_to_mm_requires_xyz():
    with pytest.raises(ValueError):
        PhysicalCoordinate(x=1.0, y=2.0).to_mm(DECK_CALIBRATION, Z_CALIBRATION)


def test_coordinate_equality():
    assert VirtualCoordinate(x=1.0, y=2.0, z=3.0) == VirtualCoordinate(x=1.0, y=2.0, z=3.0)
    assert PhysicalCoordinate(x=1.0) == PhysicalCoordinate(x=1.0)
    assert PhysicalCoordinate(x=1.0) != PhysicalCoordinate(x=2.0)


def test_coordinate_str():
    assert "X1.000" in str(PhysicalCoordinate(x=1.0))
    assert "X=1.000mm" in str(VirtualCoordinate(x=1.0))
