"""Pipette.pick_up_tip / drop_tip: the physical press+touch seating sequence
and the eject stroke. These bypass Robot's higher-level wrappers' own tests
(test_robot/test_pipette_verify.py covers settle-confirmation and
test_tools/test_plunger_calibration.py covers volume<->microstep conversion)
to instead verify the actual G-code sequence pick_up_tip/drop_tip produce:
press count, retract-between-presses (not after the last press), the touch
pattern's exact left/right/center/front/back/center order, and that tip
length only affects positioning once current_tip is actually installed."""

from __future__ import annotations

import re

import pytest

from src.core import AxisId, MountSide
from src.geometry.calibration import DeckCalibration
from src.geometry.coordinates import DeckPoint
from src.geometry.transform import AffineTransform2D
from src.geometry.units import AxisScale
from src.robot import Robot
from src.tools import Pipette, PlungerModel, TipGeometry, TipPickup
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
    # Robot._validate_targets checks robot.axes' own endstop_limit
    # independently of SimulatedTransport's axis_limits above. pick_up_tip's
    # motion computes raw Z targets well past the default 175_000 limit
    # under this test calibration, so it needs widening here too -- see the
    # same comment in test_robot/test_motion.py's _robot().
    robot.axes[AxisId.Z].config.endstop_limit = 800_000
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


def _moves(sent: list) -> list:
    return [ln for ln in sent if ln.startswith(("G0", "G1"))]


def _z_only(lines: list) -> list:
    return [ln for ln in lines if "Z" in ln and "X" not in ln and "Y" not in ln]


def _xy_only(lines: list) -> list:
    return [ln for ln in lines if "X" in ln and "Y" in ln]


def _int_after(line: str, letter: str) -> int:
    return int(re.search(rf"{letter}(-?\d+)", line).group(1))


# -- misc plunger-wiring guards (rest of the lane's pipette.py gaps) ----------


def test_uses_plunger_is_true():
    pipette = Pipette(
        name="p300", plunger=PlungerModel(microsteps_per_ul=50, bottom_microsteps=15000), max_volume_ul=300
    )
    assert pipette.uses_plunger() is True


def test_aspirate_rejects_a_volume_that_would_exceed_capacity():
    robot = _robot_with_pipette()
    pipette = robot.left()
    pipette.current_volume_ul = 290.0

    with pytest.raises(ValueError, match="exceed pipette capacity"):
        pipette.aspirate(20.0)  # 290 + 20 > 300 max_volume_ul

    assert pipette.current_volume_ul == 290.0  # rejected before the tracked volume was touched


def test_move_plunger_requires_attachment():
    pipette = Pipette(
        name="p300", plunger=PlungerModel(microsteps_per_ul=50, bottom_microsteps=15000), max_volume_ul=300
    )

    with pytest.raises(RuntimeError, match="must be mounted"):
        pipette.aspirate(10.0)


def test_move_plunger_requires_a_plunger_axis():
    calibration = DeckCalibration(
        xy=AffineTransform2D(a=100.0, b=0.0, tx=0.0, c=0.0, d=100.0, ty=0.0),
        z_scale=AxisScale(steps_per_mm=100.0),
    )
    robot = Robot(SimulatedTransport(), calibration=calibration)
    pipette = Pipette(
        name="rear_pipette",
        plunger=PlungerModel(microsteps_per_ul=50, bottom_microsteps=15000),
        max_volume_ul=300,
    )
    robot.attach(MountSide.REAR, pipette)  # rear mount has no plunger axis

    with pytest.raises(RuntimeError, match="no plunger axis"):
        pipette.aspirate(10.0)


# -- pick_up_tip --------------------------------------------------------------


def test_pick_up_tip_rejects_when_a_tip_is_already_attached():
    robot = _robot_with_pipette()
    pipette = robot.left()
    pipette.current_tip = TipGeometry(name="old_tip", length_mm=10.0)

    with pytest.raises(RuntimeError, match="already attached"):
        pipette.pick_up_tip(
            DeckPoint(0.0, 0.0), TipGeometry(name="new_tip", length_mm=1.0), TipPickup(press_z_mm=10.0)
        )


def test_pick_up_tip_requires_attachment():
    pipette = Pipette(
        name="p300", plunger=PlungerModel(microsteps_per_ul=50, bottom_microsteps=15000), max_volume_ul=300
    )

    with pytest.raises(RuntimeError, match="must be attached"):
        pipette.pick_up_tip(
            DeckPoint(0.0, 0.0), TipGeometry(name="tip", length_mm=10.0), TipPickup(press_z_mm=10.0)
        )


def test_pick_up_tip_sends_expected_press_and_touch_sequence():
    robot = _robot_with_pipette()
    pipette = robot.left()
    cal = robot.calibration
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    pickup = TipPickup(
        press_z_mm=50.0,
        engage_mm=3.0,
        retract_mm=2.0,
        presses=3,
        feed=500_000,  # fast, so SimulatedTransport's real-time G1 settles quickly
        touch_offset_mm=1.5,
    )
    tip = TipGeometry(name="p300_tip", length_mm=51.7)
    xy = DeckPoint(100.0, 50.0)

    pipette.pick_up_tip(xy, tip, pickup)

    def z_for(deck_z: float, tip_length: float = 0.0) -> int:
        return cal.deck_to_motor(DeckPoint(0, 0, deck_z), MountSide.LEFT, tip_length)[AxisId.Z]

    def xy_for(x: float, y: float) -> tuple:
        t = cal.deck_to_motor(DeckPoint(x, y, 0.0), MountSide.LEFT, 0.0)
        return t[AxisId.X], t[AxisId.Y]

    moves = _moves(sent)
    z_lines = _z_only(moves)
    xy_lines = _xy_only(moves)

    # Initial descent to press_z_mm, then 3 presses with a retract between
    # each pair (2 retracts for 3 presses -- none trailing the last one),
    # then the touch-pattern's own pre-touch retract, then the final
    # raise_z -- now WITH the tip's length applied, since current_tip is
    # set before raise_z is called.
    expected_z = [
        z_for(50.0),
        z_for(47.0),
        z_for(52.0),
        z_for(47.0),
        z_for(52.0),
        z_for(47.0),
        z_for(48.5),  # touch_retract_mm defaults to engage_mm / 2
        z_for(60.0, tip_length=51.7),
    ]
    assert [_int_after(ln, "Z") for ln in z_lines] == expected_z

    d = 1.5
    expected_xy = [
        xy_for(100.0, 50.0),  # initial horizontal crossing to the rack position
        xy_for(100.0 - d, 50.0),  # touch: left
        xy_for(100.0 + d, 50.0),  # touch: right
        xy_for(100.0, 50.0),  # touch: center
        xy_for(100.0, 50.0 - d),  # touch: front
        xy_for(100.0, 50.0 + d),  # touch: back
        xy_for(100.0, 50.0),  # touch: center
    ]
    assert [(_int_after(ln, "X"), _int_after(ln, "Y")) for ln in xy_lines] == expected_xy

    assert pipette.current_tip is tip


def test_pick_up_tip_skips_the_touch_pattern_when_touch_offset_is_zero():
    robot = _robot_with_pipette()
    pipette = robot.left()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    pickup = TipPickup(
        press_z_mm=50.0, engage_mm=3.0, retract_mm=2.0, presses=2, feed=500_000, touch_offset_mm=0
    )
    pipette.pick_up_tip(DeckPoint(100.0, 50.0), TipGeometry(name="p300_tip", length_mm=51.7), pickup)

    xy_lines = _xy_only(_moves(sent))
    assert len(xy_lines) == 1  # only the initial crossing move -- no touch pattern at all


# -- drop_tip -------------------------------------------------------------


def test_drop_tip_requires_an_installed_tip():
    robot = _robot_with_pipette()
    pipette = robot.left()

    with pytest.raises(RuntimeError, match="no tip to drop"):
        pipette.drop_tip()


def test_drop_tip_requires_attachment():
    pipette = Pipette(
        name="p300", plunger=PlungerModel(microsteps_per_ul=50, bottom_microsteps=15000), max_volume_ul=300
    )
    pipette.current_tip = TipGeometry(name="tip", length_mm=10.0)

    with pytest.raises(RuntimeError, match="must be attached"):
        pipette.drop_tip()


def test_drop_tip_requires_a_plunger_axis():
    calibration = DeckCalibration(
        xy=AffineTransform2D(a=100.0, b=0.0, tx=0.0, c=0.0, d=100.0, ty=0.0),
        z_scale=AxisScale(steps_per_mm=100.0),
    )
    robot = Robot(SimulatedTransport(), calibration=calibration)
    pipette = Pipette(
        name="rear_pipette",
        plunger=PlungerModel(microsteps_per_ul=50, bottom_microsteps=15000),
        max_volume_ul=300,
    )
    robot.attach(MountSide.REAR, pipette)  # rear mount has no plunger axis
    pipette.current_tip = TipGeometry(name="tip", length_mm=10.0)

    with pytest.raises(RuntimeError, match="no plunger axis"):
        pipette.drop_tip()


def test_drop_tip_sends_the_eject_stroke_then_resets_the_plunger_and_raises():
    robot = _robot_with_pipette()
    pipette = robot.left()
    pipette.current_tip = TipGeometry(name="p300_tip", length_mm=51.7)
    robot.move_vertical_to(0.0, MountSide.LEFT)  # deep, so raise_z has something to do after

    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    pipette.drop_tip()

    moves = _moves(sent)
    b_lines = [ln for ln in moves if ln.split()[1].startswith("B")]
    assert len(b_lines) == 2
    # First stroke drives the plunger to its endstop limit -- the hardware
    # tip-ejection action -- before current_tip/current_volume are cleared.
    assert _int_after(b_lines[0], "B") == robot.axes[AxisId.B].config.endstop_limit
    # Second stroke returns the (now bare) plunger to its zero-volume
    # position via the ordinary linear plunger model (bottom_microsteps).
    assert _int_after(b_lines[1], "B") == 15000

    assert pipette.current_tip is None
    assert pipette.current_volume_ul == 0.0

    z_lines = _z_only(moves)
    assert len(z_lines) == 1  # raise_z actually moves, since we started deep


def test_drop_tip_does_not_move_when_no_position_is_given():
    robot = _robot_with_pipette()
    pipette = robot.left()
    pipette.current_tip = TipGeometry(name="p300_tip", length_mm=51.7)
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    pipette.drop_tip()

    assert _xy_only(_moves(sent)) == []


def test_drop_tip_moves_to_the_eject_position_when_xy_and_eject_z_are_given():
    robot = _robot_with_pipette()
    pipette = robot.left()
    pipette.current_tip = TipGeometry(name="p300_tip", length_mm=51.7)
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    pipette.drop_tip(xy=DeckPoint(30.0, 40.0), eject_z_mm=20.0)

    assert len(_xy_only(_moves(sent))) == 1
