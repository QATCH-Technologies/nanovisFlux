from __future__ import annotations

import pytest

from src.core import AxisId, MountSide
from src.geometry.calibration import DeckCalibration
from src.geometry.coordinates import DeckPoint
from src.geometry.transform import AffineTransform2D
from src.geometry.units import AxisScale
from src.robot import Robot
from src.transport.simulated import SimulatedTransport


def _robot() -> Robot:
    calibration = DeckCalibration(
        xy=AffineTransform2D(a=100.0, b=0.0, tx=0.0, c=0.0, d=100.0, ty=0.0),
        z_scale=AxisScale(steps_per_mm=100.0),
        z_zero={MountSide.LEFT: 200_000},
    )
    # z_zero=200_000 (home, deck_z=0) sits above the real default Z
    # endstop_limit (175_000 -- see motion.axis.default_axis_configs) --
    # harmless before Robot's move_* methods verified their own moves, but
    # now that verify=True is the default (see robot.py), SimulatedTransport
    # would otherwise clamp every commanded target at 175_000 and
    # _await_settled would poll forever for a raw position this
    # calibration can legitimately ask for but the simulated hardware's default
    # ceiling can't reach. Widened here to match this test's own numbers,
    # not a real safety limit. Robot._validate_targets checks the same
    # range on robot.axes directly, independent of the simulated transport,
    # so it needs widening here too -- otherwise every move in this file
    # would raise ValueError before SimulatedTransport is ever reached.
    robot = Robot(SimulatedTransport(axis_limits={"Z": 300_000}), calibration=calibration)
    robot.axes[AxisId.Z].config.endstop_limit = 300_000
    return robot


def test_move_to_sends_xy_before_z() -> None:
    """robot.move_to (the "direct" path used by MoveStep when its `safe`
    checkbox is unchecked) must not bundle X/Y and Z into one multi-axis
    command whose execution order isn't guaranteed -- it should traverse
    X/Y first, then move Z, as two separate commands. Regression test for
    a reported routine bug: a mounted tip's Z dropped before X/Y crossed,
    risking a collision with labware on the deck."""
    robot = _robot()
    robot.connect()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.move_to(DeckPoint(10.0, 20.0, 5.0), MountSide.LEFT)

    move_lines = [ln for ln in sent if ln.startswith(("G0", "G1"))]
    assert len(move_lines) == 2, f"expected 2 separate move commands, got {move_lines}"
    xy_line, z_line = move_lines
    assert "X" in xy_line and "Y" in xy_line and "Z" not in xy_line
    assert "Z" in z_line and "X" not in z_line and "Y" not in z_line


def test_raise_z_sends_no_move_when_already_above_clearance() -> None:
    """Regression test: raise_z used to move to clearance unconditionally,
    so a mount that happened to already be higher (e.g. fresh off homing)
    got pulled DOWN to exactly clearance right where it was -- before any
    X/Y crossing -- risking a collision with whatever's at the CURRENT
    X/Y position. It must now be a no-op once already at/above clearance.

    robot's default travel_z_mm is 60.0mm; with this calibration
    (z_zero=200_000, steps_per_mm=100 -> 3200 microsteps/mm), home (raw
    Z=0) works out to deck_z = 200_000/3200 = 62.5mm -- already above the
    60mm clearance target."""
    robot = _robot()
    robot.connect()
    robot.home()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.raise_z(MountSide.LEFT)

    move_lines = [ln for ln in sent if ln.startswith(("G0", "G1")) and "Z" in ln]
    assert move_lines == [], f"expected no Z move, got {move_lines}"


def test_raise_z_still_raises_when_below_clearance() -> None:
    """The normal case -- e.g. right after an aspirate, deep in a well --
    must still actually raise."""
    robot = _robot()
    robot.connect()
    robot.home()
    robot.move_vertical_to(0.0, MountSide.LEFT)  # deep below the 60mm clearance
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.raise_z(MountSide.LEFT)

    move_lines = [ln for ln in sent if ln.startswith(("G0", "G1")) and "Z" in ln]
    assert len(move_lines) == 1


def test_raise_z_falls_back_to_unconditional_move_when_not_homed() -> None:
    """No trustworthy current position (axis never homed, M114 reports -1)
    -- must fall back to the original behavior rather than silently
    skipping a move that might genuinely be needed."""
    robot = _robot()
    robot.connect()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.raise_z(MountSide.LEFT)

    move_lines = [ln for ln in sent if ln.startswith(("G0", "G1")) and "Z" in ln]
    assert len(move_lines) == 1


def test_safe_move_to_does_not_drop_z_before_crossing_xy() -> None:
    """The concrete regression this fix targets: starting from a height
    already above clearance (see test_raise_z_sends_no_move_when_already_
    above_clearance), safe_move_to's X/Y crossing must be the first move
    sent -- no Z move beforehand at all, let alone one that drops it."""
    robot = _robot()
    robot.connect()
    robot.home()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.safe_move_to(DeckPoint(10.0, 20.0, 0.0), MountSide.LEFT)

    move_lines = [ln for ln in sent if ln.startswith(("G0", "G1"))]
    assert move_lines, "expected at least one move"
    assert "Z" not in move_lines[0], f"first move must not touch Z, got {move_lines[0]}"
    assert "X" in move_lines[0] and "Y" in move_lines[0]


# -- move_horizontal_to -------------------------------------------------------


def test_move_horizontal_to_requires_calibration() -> None:
    robot = Robot(SimulatedTransport())

    with pytest.raises(RuntimeError, match="not calibrated"):
        robot.move_horizontal_to(1.0, 2.0, MountSide.LEFT)


def test_move_horizontal_to_moves_xy_without_touching_the_vertical_axis() -> None:
    robot = _robot()
    robot.connect()
    robot.home()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.move_horizontal_to(10.0, 20.0, MountSide.LEFT)

    move_lines = [ln for ln in sent if ln.startswith(("G0", "G1"))]
    assert len(move_lines) == 1
    assert "X" in move_lines[0] and "Y" in move_lines[0] and "Z" not in move_lines[0]


def test_move_horizontal_to_verifies_by_default() -> None:
    robot = _robot()
    robot.connect()
    robot.home()
    calls = []
    robot._await_settled = lambda *a, **k: calls.append((a, k))

    robot.move_horizontal_to(10.0, 20.0, MountSide.LEFT)

    assert calls, "expected _await_settled to be called by default"


def test_move_horizontal_to_verify_false_skips_confirmation() -> None:
    robot = _robot()
    robot.connect()
    robot.home()
    calls = []
    robot._await_settled = lambda *a, **k: calls.append((a, k))

    robot.move_horizontal_to(10.0, 20.0, MountSide.LEFT, verify=False)

    assert not calls, "verify=False must skip settling confirmation entirely"


def test_move_horizontal_to_raises_when_target_is_outside_the_axis_travel_range() -> None:
    """This calibration's xy transform (a=100, scale factor) blows the X
    target well past the default X endstop_limit (62500 -- see
    motion.axis.default_axis_configs) for a deck coordinate this large,
    which _validate_targets must catch before anything is sent."""
    robot = _robot()
    robot.connect()

    with pytest.raises(ValueError, match="outside its travel range"):
        robot.move_horizontal_to(1000.0, 0.0, MountSide.LEFT)


def test_move_horizontal_to_with_feed_sends_a_linear_move() -> None:
    robot = _robot()
    robot.connect()
    robot.home()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.move_horizontal_to(10.0, 20.0, MountSide.LEFT, feed=600)

    move_lines = [ln for ln in sent if ln.startswith(("G0", "G1"))]
    assert len(move_lines) == 1
    assert move_lines[0].startswith("G1"), "an explicit feed must use G1, not the G0 rapid default"
    assert "F600" in move_lines[0]


# -- explicit feed on move_to / move_vertical_to -------------------------------


def test_move_to_with_feed_sends_linear_moves_for_both_legs() -> None:
    """A small Z travel (home is 62.5mm here -- see _robot()'s z_zero
    comment) and a high feed keep SimulatedTransport's wall-clock-timed G1
    interpolation (see its own module docstring) fast and deterministic;
    the point is confirming G1+F is used for both legs, not exercising
    real-time motion."""
    robot = _robot()
    robot.connect()
    robot.home()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.move_to(DeckPoint(10.0, 20.0, 62.0), MountSide.LEFT, feed=50_000)

    move_lines = [ln for ln in sent if ln.startswith("G1")]
    assert len(move_lines) == 2, f"expected both the XY leg and Z leg as G1, got {sent}"
    assert all("F50000" in ln for ln in move_lines)


def test_move_vertical_to_with_feed_sends_a_linear_move() -> None:
    robot = _robot()
    robot.connect()
    robot.home()
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.move_vertical_to(62.0, MountSide.LEFT, feed=50_000)  # small travel from the 62.5mm home

    move_lines = [ln for ln in sent if ln.startswith(("G0", "G1"))]
    assert len(move_lines) == 1
    assert move_lines[0].startswith("G1")
    assert "F50000" in move_lines[0]


def test_move_vertical_to_raises_for_a_mount_with_no_vertical_axis() -> None:
    """REAR has no vertical axis (DeckCalibration.vertical_axis returns None
    for it). deck_to_motor's returned target dict therefore has no matching
    key for `[axis]` to index with, so this currently surfaces as a
    KeyError. Documents the actual current behavior as a regression guard --
    not an endorsement that KeyError is the ideal error for this case."""
    robot = _robot()
    robot.connect()

    with pytest.raises(KeyError):
        robot.move_vertical_to(10.0, MountSide.REAR)
