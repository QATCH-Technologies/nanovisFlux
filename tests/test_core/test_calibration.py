"""Mount-offset-aware calibration math: DeckCalibration.deck_to_motor /
motor_to_deck_xy correctly place each mount, not just LEFT, and stay
correct under a rotated deck<->motor affine (the case a flat per-axis-mm
offset shortcut would get wrong)."""
import pytest

from src.core import AxisId, MountSide
from src.geometry import AffineTransform2D, AxisScale, DeckCalibration, DeckPoint
from src.motion.mounts import MOUNT_OFFSET_MM
from src.protocol.commands import MeasureDistance
from src.protocol.responses import parse_distance


#: microsteps per deck-mm for the synthetic rotated transform below --
#: matched to the realistic order of magnitude used elsewhere in this repo
#: (robot.example.yaml's measured X/Y scales are ~150-260 microsteps/mm) so
#: round()-to-integer-microsteps quantization stays well under a hundredth
#: of a mm, not an artifact that swamps the assertions.
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


def test_deck_to_motor_omits_vertical_key_for_rear():
    """REAR has no vertical axis (Mount.vertical is None) -- deck_to_motor
    used to insert a `None: <int>` dict key here, which crashed command
    rendering (`None.letter`). It should now just omit the vertical entry."""
    cal = _rotated_calibration()
    targets = cal.deck_to_motor(DeckPoint(1.0, 2.0, 3.0), MountSide.REAR)
    assert set(targets) == {AxisId.X, AxisId.Y}
    assert None not in targets


def test_measure_distance_render_and_parse_round_trip():
    assert MeasureDistance((AxisId.Z,)).render() == "M412 Z"
    assert MeasureDistance().render() == "M412"

    result = parse_distance(["[RNG:-1,-1,842.3]"])
    assert result.x_mm is None
    assert result.y_mm is None
    assert result.z_mm == pytest.approx(842.3)

    out_of_range = parse_distance(["[RNG:-1,-1,-1]"])
    assert (out_of_range.x_mm, out_of_range.y_mm, out_of_range.z_mm) == (None, None, None)
