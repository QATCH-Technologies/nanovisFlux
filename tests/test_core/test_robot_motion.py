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
