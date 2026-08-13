from __future__ import annotations

from src.core import AxisId, MountSide
from src.geometry.calibration import DeckCalibration
from src.geometry.coordinates import DeckPoint
from src.geometry.transform import AffineTransform2D
from src.geometry.units import AxisScale
from src.robot import Robot
from src.transport.fake import FakeTransport


def _robot() -> Robot:
    calibration = DeckCalibration(
        xy=AffineTransform2D(a=100.0, b=0.0, tx=0.0, c=0.0, d=100.0, ty=0.0),
        z_scale=AxisScale(steps_per_mm=100.0),
        z_zero={MountSide.LEFT: 200_000},
    )
    return Robot(FakeTransport(), calibration=calibration)


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
