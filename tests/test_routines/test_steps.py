"""Direct coverage for every Step subclass's describe() and execute(), which
until now were only ever exercised indirectly (through Routine/other tests).

execute() is run against a real Robot(SimulatedTransport(), calibration=...,
deck=...) -- see tests/test_robot/test_safe_motion.py's _robot_with_deck()
for the pattern this borrows -- so each step's effect on real firmware state
(reported motor positions, plunger position, pipette state) is asserted,
alongside describe()'s exact string.

The calibration's xy scale and z_scale are deliberately small (10
microsteps/mm) so every computed target stays comfortably inside the
default axis endstop limits from motion/axis.py without needing to widen
them, unlike test_safe_motion.py's larger cross-deck scenario."""

from __future__ import annotations

import pytest

from src.core import AxisId, MountSide
from src.deck import Deck, Labware, Slot, Well, WellGeometry
from src.geometry.calibration import DeckCalibration
from src.geometry.coordinates import DeckPoint
from src.geometry.transform import AffineTransform2D
from src.geometry.units import AxisScale
from src.robot import Robot
from src.routines import (
    AspirateStep,
    BlowOutStep,
    CommentStep,
    DelayStep,
    DispenseStep,
    DropTipStep,
    HomeStep,
    MoveStep,
    PickUpTipStep,
    SlotLocation,
    Step,
    WellLocation,
)
from src.routines import steps as steps_module
from src.tools import Pipette, PlungerModel, TipGeometry, TipPickup
from src.transport.simulated import SimulatedTransport

# Descending microsteps-vs-volume convention: bottom_microsteps is the
# zero-volume plunger position, and aspirating *subtracts* microsteps (see
# PlungerModel.volume_to_microsteps and configs/tools/pipettes/.../*.yaml).
_BOTTOM_MICROSTEPS = 15000
_USTEPS_PER_UL = 50.0


def _labware(name: str) -> Labware:
    return Labware(
        name=name,
        wells={
            "A1": Well(
                "A1",
                DeckPoint(5.0, 5.0, 10.0),
                WellGeometry(depth_mm=30.0, bottom_clearance_mm=2.0),
            )
        },
    )


def _robot() -> Robot:
    deck = Deck()
    deck.add(Slot(name="1", origin=DeckPoint(0.0, 0.0), size=(100.0, 100.0)))
    calibration = DeckCalibration(
        xy=AffineTransform2D(a=10.0, b=0.0, tx=0.0, c=0.0, d=10.0, ty=0.0),
        z_scale=AxisScale(steps_per_mm=10.0),
        z_zero={MountSide.LEFT: 100_000},
    )
    robot = Robot(SimulatedTransport(), calibration=calibration, deck=deck, travel_z_mm=50.0)
    robot.load_labware(_labware("plate"), "1", key="plate")
    robot.connect()
    robot.home()
    return robot


def _robot_with_pipette() -> tuple[Robot, Pipette]:
    robot = _robot()
    pip = Pipette(
        name="p300",
        plunger=PlungerModel(microsteps_per_ul=_USTEPS_PER_UL, bottom_microsteps=_BOTTOM_MICROSTEPS),
        max_volume_ul=300,
    )
    robot.attach(MountSide.LEFT, pip)
    return robot, pip


# -- Step base ----------------------------------------------------------


def test_step_base_execute_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        Step().execute(robot=None, side=None)


def test_step_base_describe_defaults_to_the_class_name():
    assert Step().describe() == "Step"


# -- HomeStep -------------------------------------------------------------


def test_home_step_execute_with_no_axes_homes_everything():
    robot = Robot(SimulatedTransport())
    robot.connect()
    assert not any(a.homed for a in robot.axes.values())

    HomeStep().execute(robot, MountSide.LEFT)

    assert all(a.homed for a in robot.axes.values())


def test_home_step_execute_with_specific_axes_only_homes_those():
    robot = Robot(SimulatedTransport())
    robot.connect()

    HomeStep(axes=(AxisId.X,)).execute(robot, MountSide.LEFT)

    assert robot.axes[AxisId.X].homed is True
    assert robot.axes[AxisId.Y].homed is False


def test_home_step_describe_all_axes():
    assert HomeStep().describe() == "home all"


def test_home_step_describe_specific_axes():
    assert HomeStep(axes=(AxisId.X, AxisId.Z)).describe() == "home X Z"


# -- MoveStep ---------------------------------------------------------------


def test_move_step_execute_drives_the_mount_to_the_resolved_location():
    robot = _robot()
    where = WellLocation("plate", "A1", ref="top")

    MoveStep(where).execute(robot, MountSide.LEFT)

    point = where.resolve(robot)
    expected = robot.calibration.deck_to_motor(point, MountSide.LEFT, robot.tip_offset(MountSide.LEFT))
    actual = robot.controller.report_position()
    assert actual[AxisId.X] == expected[AxisId.X]
    assert actual[AxisId.Y] == expected[AxisId.Y]
    assert actual[AxisId.Z] == expected[AxisId.Z]


def test_move_step_describe():
    where = WellLocation("plate", "A1", ref="top")
    assert MoveStep(where).describe() == f"move to {where}"


# -- PickUpTipStep ------------------------------------------------------


def test_pick_up_tip_step_execute_installs_the_registered_tip():
    robot, pip = _robot_with_pipette()
    tip = TipGeometry(name="p300_tip", length_mm=51.7)
    robot.tips["p300_tip"] = tip
    where = WellLocation("plate", "A1", ref="top")
    pickup = TipPickup(press_z_mm=15.0, engage_mm=1.0, presses=1, touch_offset_mm=0)
    assert pip.current_tip is None

    PickUpTipStep(where=where, tip="p300_tip", pickup=pickup).execute(robot, MountSide.LEFT)

    assert pip.current_tip == tip


def test_pick_up_tip_step_describe():
    where = WellLocation("rack", "A1", ref="top")
    step = PickUpTipStep(where=where, tip="p300_tip", pickup=TipPickup(press_z_mm=15.0))
    assert step.describe() == f"pick up tip p300_tip at {where}"


# -- DropTipStep ----------------------------------------------------------


def test_drop_tip_step_execute_clears_tip_and_resets_volume():
    robot, pip = _robot_with_pipette()
    robot.tips["p300_tip"] = TipGeometry(name="p300_tip", length_mm=51.7)
    where = WellLocation("plate", "A1", ref="top")
    PickUpTipStep(
        where=where,
        tip="p300_tip",
        pickup=TipPickup(press_z_mm=15.0, engage_mm=1.0, presses=1, touch_offset_mm=0),
    ).execute(robot, MountSide.LEFT)
    assert pip.current_tip is not None  # sanity check on the fixture

    DropTipStep(where=where, eject_z_mm=5.0).execute(robot, MountSide.LEFT)

    assert pip.current_tip is None
    assert pip.current_volume_ul == 0.0


def test_drop_tip_step_describe_without_location():
    assert DropTipStep().describe() == "drop tip"


def test_drop_tip_step_describe_with_location():
    where = SlotLocation("1")
    assert DropTipStep(where=where).describe() == f"drop tip at {where}"


# -- AspirateStep -----------------------------------------------------------


def test_aspirate_step_execute_moves_then_advances_plunger():
    robot, pip = _robot_with_pipette()
    where = WellLocation("plate", "A1", ref="top")

    AspirateStep(volume_ul=50.0, where=where).execute(robot, MountSide.LEFT)

    assert pip.current_volume_ul == 50.0
    assert robot.controller.report_position()[AxisId.B] == _BOTTOM_MICROSTEPS - round(
        50.0 * _USTEPS_PER_UL
    )


def test_aspirate_step_describe():
    where = WellLocation("plate", "A1", ref="top")
    assert AspirateStep(volume_ul=50.0, where=where).describe() == f"aspirate 50.0 uL from {where}"


# -- DispenseStep ---------------------------------------------------------


def test_dispense_step_execute_reduces_tracked_volume():
    robot, pip = _robot_with_pipette()
    where = WellLocation("plate", "A1", ref="top")
    AspirateStep(volume_ul=50.0, where=where).execute(robot, MountSide.LEFT)

    DispenseStep(volume_ul=20.0, where=where).execute(robot, MountSide.LEFT)

    assert pip.current_volume_ul == 30.0
    assert robot.controller.report_position()[AxisId.B] == _BOTTOM_MICROSTEPS - round(
        30.0 * _USTEPS_PER_UL
    )


def test_dispense_step_describe_with_explicit_volume():
    where = WellLocation("plate", "A1", ref="top")
    assert DispenseStep(volume_ul=20.0, where=where).describe() == f"dispense 20.0 uL to {where}"


def test_dispense_step_describe_with_none_means_all():
    where = WellLocation("plate", "A1", ref="top")
    assert DispenseStep(volume_ul=None, where=where).describe() == f"dispense all to {where}"


# -- BlowOutStep ------------------------------------------------------------


def test_blow_out_step_execute_moves_when_a_location_is_given():
    robot, pip = _robot_with_pipette()
    where = WellLocation("plate", "A1", ref="top")
    AspirateStep(volume_ul=30.0, where=where).execute(robot, MountSide.LEFT)

    BlowOutStep(where=where).execute(robot, MountSide.LEFT)

    assert pip.current_volume_ul == 0.0
    assert robot.controller.report_position()[AxisId.B] == _BOTTOM_MICROSTEPS


def test_blow_out_step_execute_without_location_skips_the_move():
    robot, pip = _robot_with_pipette()
    pip.current_volume_ul = 10.0
    before = robot.controller.report_position()
    before_xy = (before[AxisId.X], before[AxisId.Y])

    BlowOutStep().execute(robot, MountSide.LEFT)

    after = robot.controller.report_position()
    assert (after[AxisId.X], after[AxisId.Y]) == before_xy  # no horizontal move issued
    assert pip.current_volume_ul == 0.0  # blow_out() still ran


def test_blow_out_step_describe():
    assert BlowOutStep().describe() == "blow out"


# -- DelayStep --------------------------------------------------------------


def test_delay_step_execute_sleeps_for_the_configured_duration(monkeypatch):
    # Assert on the *call*, not elapsed wall-clock time -- a real sleep()
    # comparison is prone to flaking on slow/loaded CI runners since
    # time.sleep() only guarantees sleeping *at least* the requested
    # duration, not exactly that duration.
    calls = []
    monkeypatch.setattr(steps_module.time, "sleep", lambda seconds: calls.append(seconds))

    DelayStep(seconds=1.5).execute(robot=None, side=None)

    assert calls == [1.5]


def test_delay_step_describe():
    assert DelayStep(seconds=1.5).describe() == "delay 1.5s"


# -- CommentStep ------------------------------------------------------------


def test_comment_step_execute_is_a_no_op():
    assert CommentStep(text="note").execute(robot=None, side=None) is None


def test_comment_step_describe():
    assert CommentStep(text="note").describe() == "# note"
