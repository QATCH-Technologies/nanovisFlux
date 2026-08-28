"""Mount-offset-aware calibration math: DeckCalibration.deck_to_motor /
motor_to_deck_xy correctly place each mount, not just LEFT, and stay
correct under a rotated deck<->motor affine (the case a flat per-axis-mm
offset shortcut would get wrong).

Also covers the two hardware-touching Z-calibration entry points,
DeckCalibration.probe_z_zero (automated G38 probe-and-commit) and
touch_off_z_zero (manual jog-and-commit), exercised against a real
Robot(SimulatedTransport(), ...) rather than a mock controller, plus
DeckCalibration.from_points's construction behavior."""
from types import SimpleNamespace

import pytest

from src.core import AxisId, MountSide
from src.geometry import AffineTransform2D, AxisScale, DeckCalibration, DeckPoint
from src.motion.mounts import MOUNT_OFFSET_MM
from src.protocol.commands import MeasureDistance
from src.protocol.errors import ProbeError
from src.protocol.responses import parse_distance
from src.robot import Robot
from src.transport.simulated import SimulatedTransport


#: microsteps per deck-mm for the synthetic rotated transform below --
#: matched to the realistic order of magnitude used elsewhere in this repo
#: (configs/calibration.yaml's measured X/Y scales are ~150-260
#: microsteps/mm) so round()-to-integer-microsteps quantization stays well
#: under a hundredth of a mm, not an artifact that swamps the assertions.
_SCALE = 200.0


def _rotated_calibration() -> DeckCalibration:
    """A pure 90-degree-rotation-plus-scale transform: deck (x, y) -> motor
    (-SCALE*y, SCALE*x). No translation, so the math stays easy to check by
    hand, but a rotation is still present -- LEFT/RIGHT's deck-X offset
    should show up as a motor-Y difference here, not motor-X, which is
    exactly what a naive "convert the offset via the X axis's own
    steps_per_mm" shortcut would get wrong.
    """
    xy = AffineTransform2D(a=0.0, b=-_SCALE, tx=0.0, c=_SCALE, d=0.0, ty=0.0)
    return DeckCalibration(xy=xy, z_scale=AxisScale(steps_per_mm=25.0),
                           z_zero={MountSide.LEFT: 100000, MountSide.RIGHT: 100000})


def test_left_right_offset_survives_rotation():
    cal = _rotated_calibration()
    point = DeckPoint(50.0, 20.0, 0.0)

    left_mx, left_my = cal._reference_xy(point, MountSide.LEFT)
    right_mx, right_my = cal._reference_xy(point, MountSide.RIGHT)

    # Same deck point, two different mounts -> two different motor targets
    # (the bug: today both silently land at the same, LEFT-only, spot).
    lox, loy = MOUNT_OFFSET_MM[MountSide.LEFT]
    rox, roy = MOUNT_OFFSET_MM[MountSide.RIGHT]
    assert (lox, loy) != (rox, roy)
    assert (left_mx, left_my) != (right_mx, right_my)

    # The LEFT/RIGHT deck-X spacing (32.5mm) is entirely along deck-X, but
    # this calibration rotates deck-X into motor-Y (my = SCALE*x) -- so the
    # difference must show up in motor Y, scaled by the transform, not in
    # motor X (which only depends on deck-y here and is untouched by the
    # mount offset in this rotation). _reference_xy subtracts the offset
    # before applying the transform, so LEFT (offset -16.25) ends up
    # applying x - (-16.25) = x + 16.25, i.e. *larger* than RIGHT's
    # x - 16.25 -- hence (rox - lox), not (lox - rox).
    assert left_mx == pytest.approx(right_mx)
    assert (left_my - right_my) == pytest.approx((rox - lox) * _SCALE)


def test_deck_to_motor_round_trips_through_motor_to_deck_xy():
    cal = _rotated_calibration()
    point = DeckPoint(12.0, -34.0, 0.0)
    for side in (MountSide.LEFT, MountSide.RIGHT, MountSide.REAR):
        targets = cal.deck_to_motor(point, side)
        back_x, back_y = cal.motor_to_deck_xy(targets[AxisId.X], targets[AxisId.Y], side)
        # abs=0.01: deck_to_motor rounds to whole microsteps, so a fraction
        # of a microstep of quantization (well under 0.01mm at this scale)
        # is expected and not itself a bug.
        assert back_x == pytest.approx(point.x, abs=0.01)
        assert back_y == pytest.approx(point.y, abs=0.01)


def test_deck_to_motor_round_trips_through_motor_to_deck_z():
    cal = _rotated_calibration()
    point = DeckPoint(0.0, 0.0, 45.0)
    for side in (MountSide.LEFT, MountSide.RIGHT):
        for tip_length in (0.0, 12.5):
            targets = cal.deck_to_motor(point, side, tip_length)
            vertical = cal.vertical_axis(side)
            back_z = cal.motor_to_deck_z(targets[vertical], side, tip_length)
            assert back_z == pytest.approx(point.z, abs=0.01)


def test_motor_to_deck_z_none_for_rear_mount():
    """REAR has no vertical axis -- nothing to invert against."""
    cal = _rotated_calibration()
    assert cal.motor_to_deck_z(12345, MountSide.REAR) is None


def test_motor_to_deck_z_none_without_z_zero_for_that_side():
    """A side with no z_zero calibrated yet has no reference to invert
    against -- distinct from "REAR has no vertical axis at all"."""
    cal = DeckCalibration(xy=_rotated_calibration().xy, z_scale=AxisScale(steps_per_mm=25.0))
    assert cal.vertical_axis(MountSide.LEFT) is not None  # sanity: LEFT does have a vertical axis
    assert cal.motor_to_deck_z(12345, MountSide.LEFT) is None


def test_deck_to_motor_omits_vertical_key_for_rear():
    """REAR has no vertical axis (Mount.vertical is None) -- deck_to_motor
    used to insert a `None: <int>` dict key here, which crashed command
    rendering (`None.letter`). It should now just omit the vertical entry."""
    cal = _rotated_calibration()
    targets = cal.deck_to_motor(DeckPoint(1.0, 2.0, 3.0), MountSide.REAR)
    assert set(targets) == {AxisId.X, AxisId.Y}
    assert None not in targets


def test_deck_calibration_from_points_accepts_more_than_three():
    """DeckCalibration.from_points wires straight into
    AffineTransform2D.from_point_pairs (now N>=3), so calibrating from every
    checked mark in the dialog -- not just exactly 3 -- should just work."""
    deck_pts = [DeckPoint(0.0, 0.0), DeckPoint(10.0, 0.0),
               DeckPoint(0.0, 10.0), DeckPoint(10.0, 10.0)]
    motor_xy = [(0.0, 0.0), (_SCALE * 10.0, 0.0), (0.0, _SCALE * 10.0), (_SCALE * 10.0, _SCALE * 10.0)]
    cal = DeckCalibration.from_points(deck_pts, motor_xy, z_scale=AxisScale(steps_per_mm=25.0))
    mx, my = cal.xy.apply(5.0, 5.0)
    assert mx == pytest.approx(_SCALE * 5.0)
    assert my == pytest.approx(_SCALE * 5.0)


def test_measure_distance_render_and_parse_round_trip():
    assert MeasureDistance((AxisId.Z,)).render() == "M412 Z"
    assert MeasureDistance().render() == "M412"

    result = parse_distance(["[RNG:-1,-1,842.3]"])
    assert result.x_mm is None
    assert result.y_mm is None
    assert result.z_mm == pytest.approx(842.3)

    out_of_range = parse_distance(["[RNG:-1,-1,-1]"])
    assert (out_of_range.x_mm, out_of_range.y_mm, out_of_range.z_mm) == (None, None, None)


def test_motor_to_deck_xy_without_side_returns_gantry_reference():
    """side=None is the "just invert the transform, no mount offset"
    path -- distinct from the side-aware branch exercised above."""
    cal = _rotated_calibration()
    mx, my = cal.xy.apply(12.0, -7.0)

    rx, ry = cal.motor_to_deck_xy(mx, my)

    assert rx == pytest.approx(12.0)
    assert ry == pytest.approx(-7.0)


def test_deck_calibration_from_points_defaults_to_independent_z_zero_dicts():
    """z_zero uses field(default_factory=dict); from_points's own
    `z_zero or {}` must not accidentally let two independently constructed
    calibrations end up sharing one mutable dict instance."""
    deck_pts = [DeckPoint(0.0, 0.0), DeckPoint(10.0, 0.0), DeckPoint(0.0, 10.0)]
    motor_xy = [(0.0, 0.0), (_SCALE * 10.0, 0.0), (0.0, _SCALE * 10.0)]
    cal_a = DeckCalibration.from_points(deck_pts, motor_xy, z_scale=AxisScale(steps_per_mm=25.0))
    cal_b = DeckCalibration.from_points(deck_pts, motor_xy, z_scale=AxisScale(steps_per_mm=25.0))

    cal_a.z_zero[MountSide.LEFT] = 12345

    assert MountSide.LEFT not in cal_b.z_zero


# -- probe_z_zero / touch_off_z_zero (hardware-touching Z calibration) ------
#
# Both methods lazily import protocol types and drive a real Robot's
# controller directly (rapid_move / probe / report_position) rather than
# going through Robot.move_vertical_to, so they're exercised here against a
# real Robot(SimulatedTransport(), ...) instead of a mock.


def _hardware_calibration() -> DeckCalibration:
    """Same rotated XY transform as _rotated_calibration, but with an empty
    z_zero -- the tests below establish z_zero themselves and need to
    observe it go from absent to populated."""
    return DeckCalibration(xy=_rotated_calibration().xy, z_scale=AxisScale(steps_per_mm=25.0))


def _robot_for_hardware_tests(**transport_kwargs) -> Robot:
    robot = Robot(SimulatedTransport(**transport_kwargs), calibration=_hardware_calibration())
    robot.connect()
    robot.home()
    return robot


def test_probe_z_zero_commits_contact_and_retracts():
    robot = _robot_for_hardware_tests()
    cal = robot.calibration
    target = DeckPoint(0.0, 0.0, 0.0)

    result = cal.probe_z_zero(robot, MountSide.LEFT, target, tip_length_mm=5.0)

    # SimulatedTransport's default probe_contact for "Z" is 120000
    # microsteps, comfortably inside the default max_descent (Z's
    # endstop_limit, 175000), so contact is made there.
    assert result.contact_microsteps == 120000
    expected_z_zero = 120000 + cal.z_scale.to_microsteps(5.0)
    assert result.z_zero_microsteps == expected_z_zero
    assert result.tip_length_mm == 5.0
    assert result.xy == target
    assert result.side is MountSide.LEFT

    # committed onto the calibration object by default
    assert cal.z_zero[MountSide.LEFT] == expected_z_zero

    # retracted back to the safe_up_microsteps default (2000) after contact
    assert robot.controller.report_position()[AxisId.Z] == 2000


def test_probe_z_zero_commit_false_leaves_calibration_untouched():
    robot = _robot_for_hardware_tests()
    cal = robot.calibration

    cal.probe_z_zero(robot, MountSide.LEFT, DeckPoint(0.0, 0.0, 0.0), commit=False)

    assert MountSide.LEFT not in cal.z_zero


def test_probe_z_zero_positions_xy_and_uses_custom_probe_parameters():
    """End-to-end check of the actual G-code sent: the mount is raised to
    the custom safe_up height, positioned over the mount-offset-corrected
    XY target, probed with the custom feed/max_descent, then retracted back
    to the same safe_up height."""
    robot = _robot_for_hardware_tests()
    cal = robot.calibration
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    cal.probe_z_zero(
        robot,
        MountSide.LEFT,
        DeckPoint(0.0, 0.0, 0.0),
        feed=42,
        safe_up_microsteps=9000,
        max_descent_microsteps=150000,
    )

    # _reference_xy(DeckPoint(0, 0, 0), LEFT) subtracts LEFT's (-16.25, 0.0)
    # mount offset before applying the rotated transform (deck-x -> motor-y):
    # apply(0 - (-16.25), 0 - 0) = (0, 200 * 16.25) = (0, 3250).
    assert "G0 X0 Y3250" in sent
    assert "G38.2 Z150000 F42" in sent
    assert sent.count("G0 Z9000") == 2  # safe-up approach leg, then retract leg


def test_probe_z_zero_raises_probe_error_without_contact():
    """probe_contact=None for "Z" simulates a probe that never trips --
    the descent completes without contact, matching a real miscalibrated
    or missing reference surface."""
    robot = _robot_for_hardware_tests(probe_contact={"Z": None})
    cal = robot.calibration

    with pytest.raises(ProbeError, match="left"):
        cal.probe_z_zero(robot, MountSide.LEFT, DeckPoint(0.0, 0.0, 0.0))

    assert MountSide.LEFT not in cal.z_zero  # a failed probe must not commit


def test_probe_z_zero_uses_right_mounts_vertical_axis():
    """RIGHT's vertical axis is A, not Z -- probe_z_zero must read/retract
    the axis that actually corresponds to the requested mount."""
    robot = _robot_for_hardware_tests()
    cal = robot.calibration

    result = cal.probe_z_zero(robot, MountSide.RIGHT, DeckPoint(0.0, 0.0, 0.0))

    assert result.side is MountSide.RIGHT
    assert robot.controller.report_position()[AxisId.A] == 2000  # retracted
    assert MountSide.RIGHT in cal.z_zero
    assert MountSide.LEFT not in cal.z_zero


def test_touch_off_z_zero_reads_current_position_with_explicit_tip_length():
    robot = _robot_for_hardware_tests()
    cal = robot.calibration
    robot.controller.rapid_move({AxisId.Z: 50000})  # operator jogged here manually

    result = cal.touch_off_z_zero(robot, MountSide.LEFT, tip_length_mm=3.0)

    assert result.contact_microsteps == 50000
    expected_z_zero = 50000 + cal.z_scale.to_microsteps(3.0)
    assert result.z_zero_microsteps == expected_z_zero
    assert result.tip_length_mm == 3.0
    assert result.xy is None  # manual touch-off has no associated XY, unlike a probe
    assert cal.z_zero[MountSide.LEFT] == expected_z_zero


def test_touch_off_z_zero_uses_attached_tools_tip_offset_when_omitted():
    robot = _robot_for_hardware_tests()
    cal = robot.calibration
    robot.controller.rapid_move({AxisId.Z: 60000})
    robot.mounts[MountSide.LEFT].tool = SimpleNamespace(tip_offset_mm=lambda: 7.5)

    result = cal.touch_off_z_zero(robot, MountSide.LEFT)  # tip_length_mm omitted

    assert result.tip_length_mm == pytest.approx(7.5)
    expected_z_zero = 60000 + cal.z_scale.to_microsteps(7.5)
    assert result.z_zero_microsteps == expected_z_zero
    assert cal.z_zero[MountSide.LEFT] == expected_z_zero


def test_touch_off_z_zero_commit_false_leaves_calibration_untouched():
    robot = _robot_for_hardware_tests()
    cal = robot.calibration
    robot.controller.rapid_move({AxisId.Z: 40000})

    result = cal.touch_off_z_zero(robot, MountSide.LEFT, tip_length_mm=0.0, commit=False)

    assert result.contact_microsteps == 40000
    assert MountSide.LEFT not in cal.z_zero


def test_touch_off_z_zero_uses_right_mounts_vertical_axis():
    """Mirrors test_probe_z_zero_uses_right_mounts_vertical_axis: touch-off
    must also read the mount-appropriate axis (A for RIGHT), not always Z."""
    robot = _robot_for_hardware_tests()
    cal = robot.calibration
    robot.controller.rapid_move({AxisId.A: 33000, AxisId.Z: 999})

    result = cal.touch_off_z_zero(robot, MountSide.RIGHT, tip_length_mm=0.0)

    assert result.contact_microsteps == 33000
    assert cal.z_zero[MountSide.RIGHT] == 33000
    assert MountSide.LEFT not in cal.z_zero
