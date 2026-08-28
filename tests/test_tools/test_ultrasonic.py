"""UltrasonicSensor: fixed-position M412 range queries. The controller slot
queried is selected from the sensor's attached MountSide (_MOUNT_RANGE_SLOT);
SimulatedTransport only ever simulates a real echo on the Z slot (the
physically-wired rear sensor -- see transport/simulated.py's M412 handling),
so X/Y-slot reads (left/right mounts) are exercised as the "always
unavailable" branch rather than needing a second simulated sensor."""

from __future__ import annotations

import pytest

from src.core import AxisId, MountSide
from src.protocol.responses import DistanceResult
from src.robot import Robot
from src.tools import UltrasonicSensor
from src.transport.simulated import SimulatedTransport


def _robot_with_sensor(side: MountSide, ultrasonic_mm: float | None = None) -> Robot:
    robot = Robot(SimulatedTransport(ultrasonic_mm=ultrasonic_mm))
    robot.attach(side, UltrasonicSensor(name="rangefinder"))
    robot.connect()
    return robot


def test_slot_defaults_to_rear_z_when_detached():
    assert UltrasonicSensor()._slot() == AxisId.Z


@pytest.mark.parametrize(
    "side, axis",
    [(MountSide.LEFT, AxisId.X), (MountSide.RIGHT, AxisId.Y), (MountSide.REAR, AxisId.Z)],
)
def test_slot_follows_the_attached_mount_side(side, axis):
    robot = Robot(SimulatedTransport())
    robot.attach(side, UltrasonicSensor())

    assert robot.mounts[side].tool._slot() == axis


def test_read_raises_when_not_attached_to_a_robot():
    with pytest.raises(AttributeError, match="not attached to a robot"):
        UltrasonicSensor().read()


def test_read_queries_the_slot_for_the_attached_mount():
    robot = _robot_with_sensor(MountSide.REAR, ultrasonic_mm=45.5)
    sensor = robot.rear()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    result = sensor.read()

    assert any(ln.startswith("M412") and "Z" in ln for ln in sent)
    assert isinstance(result, DistanceResult)
    assert result.z_mm == pytest.approx(45.5)
    assert result.x_mm is None and result.y_mm is None


def test_read_distance_mm_returns_the_measured_value_for_the_rear_mount():
    robot = _robot_with_sensor(MountSide.REAR, ultrasonic_mm=45.5)
    sensor = robot.rear()

    assert sensor.read_distance_mm() == pytest.approx(45.5)


def test_read_distance_mm_is_none_for_a_slot_the_hardware_never_populates():
    # Left/right mounts reserve the X/Y sensor slots for hardware that isn't
    # physically installed; even with a valid rear echo configured,
    # read_distance_mm for a left-mounted sensor must report "unavailable"
    # rather than coincidentally returning the rear reading.
    robot = _robot_with_sensor(MountSide.LEFT, ultrasonic_mm=45.5)
    sensor = robot.left()

    assert sensor.read_distance_mm() is None


def test_read_distance_mm_is_none_when_no_echo_is_configured():
    robot = _robot_with_sensor(MountSide.REAR, ultrasonic_mm=None)
    sensor = robot.rear()

    assert sensor.read_distance_mm() is None


def test_max_range_mm_defaults_and_is_configurable():
    assert UltrasonicSensor().max_range_mm == 4000.0
    assert UltrasonicSensor(max_range_mm=1200.0).max_range_mm == 1200.0
