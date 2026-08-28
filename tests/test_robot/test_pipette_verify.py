"""Pipette plunger moves (aspirate/dispense/blow_out, and the eject stroke
in drop_tip) go straight to Controller.linear_move, bypassing every
Robot.move_* wrapper -- so they need their own explicit settle
confirmation rather than silently missing out on the same "a G-code 'ok'
doesn't mean physically arrived" fix those wrappers now apply by default
(see Robot._await_settled's own docstring)."""

from __future__ import annotations

from src.core import MountSide
from src.geometry.calibration import DeckCalibration
from src.geometry.transform import AffineTransform2D
from src.geometry.units import AxisScale
from src.robot import Robot
from src.tools import Pipette, PlungerModel
from src.transport.simulated import SimulatedTransport


def _robot_with_pipette() -> Robot:
    calibration = DeckCalibration(
        xy=AffineTransform2D(a=100.0, b=0.0, tx=0.0, c=0.0, d=100.0, ty=0.0),
        z_scale=AxisScale(steps_per_mm=100.0),
        z_zero={MountSide.LEFT: 800_000},
    )
    robot = Robot(
        SimulatedTransport(axis_limits={"X": 500_000, "Y": 500_000, "Z": 800_000, "B": 800_000}),
        calibration=calibration,
    )
    robot.connect()
    robot.home()
    robot.attach(
        MountSide.LEFT,
        Pipette(
            name="p300",
            plunger=PlungerModel(microsteps_per_ul=50, bottom_microsteps=15000),
            max_volume_ul=300,
        ),
    )
    return robot


def test_aspirate_verifies_the_plunger_move():
    robot = _robot_with_pipette()
    pipette = robot.left()
    calls = []
    robot._await_settled = lambda *a, **k: calls.append((a, k))

    pipette.aspirate(50.0)

    assert calls, "expected the plunger move to be settle-confirmed"


def test_dispense_verifies_the_plunger_move():
    robot = _robot_with_pipette()
    pipette = robot.left()
    pipette.aspirate(50.0)
    calls = []
    robot._await_settled = lambda *a, **k: calls.append((a, k))

    pipette.dispense(50.0)

    assert calls, "expected the plunger move to be settle-confirmed"


def test_drop_tip_eject_stroke_verifies():
    from src.tools import TipGeometry

    robot = _robot_with_pipette()
    pipette = robot.left()
    pipette.current_tip = TipGeometry(name="tip", length_mm=50.0)  # skip pick_up_tip's own motion
    calls = []
    robot._await_settled = lambda *a, **k: calls.append((a, k))

    pipette.drop_tip()

    assert calls, "expected the eject stroke to be settle-confirmed"
