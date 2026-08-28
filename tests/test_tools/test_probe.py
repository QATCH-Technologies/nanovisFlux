"""TouchProbe: wraps the controller's G38 probe cycle and resolves contact
positions through DeckCalibration. Covers probe_down's attach/calibration/
mount guards and both branches of the firmware's [PRB:...] contact flag,
driven through SimulatedTransport's configurable probe_contact positions
(see transport/simulated.py's _handle for the G38 simulation)."""

from __future__ import annotations

import pytest

from src.core import MountSide
from src.geometry.calibration import DeckCalibration
from src.geometry.coordinates import DeckPoint
from src.geometry.transform import AffineTransform2D
from src.geometry.units import AxisScale
from src.robot import Robot
from src.tools import TouchProbe
from src.transport.simulated import SimulatedTransport


def _calibration() -> DeckCalibration:
    return DeckCalibration(
        xy=AffineTransform2D(a=100.0, b=0.0, tx=0.0, c=0.0, d=100.0, ty=0.0),
        z_scale=AxisScale(steps_per_mm=100.0),
        z_zero={MountSide.LEFT: 800_000},
    )


def _robot_with_probe(probe_contact=None) -> Robot:
    robot = Robot(
        SimulatedTransport(
            axis_limits={"X": 500_000, "Y": 500_000, "Z": 800_000},
            probe_contact=probe_contact,
        ),
        calibration=_calibration(),
    )
    robot.attach(MountSide.LEFT, TouchProbe(name="probe", length_mm=12.5))
    return robot


def test_tip_offset_mm_returns_the_configured_probe_length():
    probe = TouchProbe(length_mm=12.5)
    assert probe.tip_offset_mm() == 12.5


def test_probe_down_requires_attachment():
    with pytest.raises(RuntimeError, match="_robot and/or _mount"):
        TouchProbe().probe_down(10.0)


def test_probe_down_requires_calibration():
    robot = Robot(SimulatedTransport())  # calibration defaults to None
    robot.attach(MountSide.LEFT, TouchProbe())
    probe = robot.left()

    with pytest.raises(RuntimeError, match="calibration is not initialized"):
        probe.probe_down(10.0)


def test_probe_down_requires_a_mount_with_a_vertical_axis():
    # The rear mount has no vertical axis (Mount.vertical is None there).
    robot = Robot(SimulatedTransport(), calibration=_calibration())
    robot.attach(MountSide.REAR, TouchProbe())
    probe = robot.rear()

    with pytest.raises(RuntimeError, match="mount vertical axis is not initialized"):
        probe.probe_down(10.0)


def test_probe_down_returns_the_deck_contact_point_on_success():
    robot = _robot_with_probe()  # default probe_contact = {"Z": 120000, "A": 120000}
    robot.connect()
    robot.home()
    probe = robot.left()

    result = probe.probe_down(100.0)

    # X/Y are read back from the (unmoved, homed-to-0) motor position and
    # converted through the left mount's fixed deck offset; Z is simply the
    # requested target, per probe_down's own contract.
    assert result == DeckPoint(-16.25, 0.0, 100.0)


def test_probe_down_returns_none_when_the_firmware_reports_no_contact():
    robot = _robot_with_probe(probe_contact={"Z": None})
    robot.connect()
    robot.home()
    probe = robot.left()

    assert probe.probe_down(100.0) is None


def test_probe_down_sends_a_toward_or_fail_probe_on_the_mount_vertical_axis():
    robot = _robot_with_probe()
    robot.connect()
    robot.home()
    probe = robot.left()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    probe.probe_down(100.0, feed=250)

    probe_lines = [ln for ln in sent if ln.startswith("G38")]
    assert len(probe_lines) == 1
    assert probe_lines[0].startswith("G38.2 Z")  # TOWARD_OR_FAIL on the left mount's Z axis
    assert "F250" in probe_lines[0]
