"""avoid_resonant_feed/feed_in_resonance_band (src/motion/resonance.py): a
requested feed (microsteps/s) gets nudged clear of any configured
resonance_bands_hz (full motor-step Hz) instead of being sent as-is -- see
that module's own docstring for why full-step Hz rather than microsteps/s
is the unit bands are expressed in.

_axis_resonance_warnings (src/config/loader.py) is the complementary static
check: an axis's own steady-state travel_speed/homing_speed shouldn't
itself sit inside its configured band."""
import pytest

from src.config.loader import _axis_resonance_warnings
from src.core import AxisId
from src.motion.axis import AxisConfig
from src.motion.resonance import avoid_resonant_feed, feed_in_resonance_band

_MSTEPS = 32  # MICROSTEPS_PER_STEP, matched explicitly rather than imported so a
              # drift in the real constant would break this test, not hide behind it


def test_feed_in_resonance_band_outside_any_band():
    assert feed_in_resonance_band(1000, [(100, 200)], _MSTEPS) is None


def test_feed_in_resonance_band_inside_a_band():
    # 150 Hz full-step * 32 = 4800 microsteps/s
    assert feed_in_resonance_band(4800, [(100, 200)], _MSTEPS) == (100, 200)


def test_feed_in_resonance_band_at_exact_edges_counts_as_inside():
    assert feed_in_resonance_band(100 * _MSTEPS, [(100, 200)], _MSTEPS) == (100, 200)
    assert feed_in_resonance_band(200 * _MSTEPS, [(100, 200)], _MSTEPS) == (100, 200)


def test_avoid_resonant_feed_no_bands_returns_unchanged():
    assert avoid_resonant_feed(5000, (), microsteps_per_step=_MSTEPS) == 5000


def test_avoid_resonant_feed_outside_bands_returns_unchanged():
    # band 100-200 Hz -> 3200-6400 microsteps/s; 10000 is clear of it
    assert avoid_resonant_feed(10000, [(100, 200)], microsteps_per_step=_MSTEPS) == 10000


def test_avoid_resonant_feed_nudges_to_nearer_edge():
    # band 100-200 Hz -> 3200-6400 microsteps/s; 3300 is much closer to the
    # low edge (3199) than the high edge (6401)
    result = avoid_resonant_feed(3300, [(100, 200)], microsteps_per_step=_MSTEPS)
    assert result == 100 * _MSTEPS - 1
    assert not (100 * _MSTEPS <= result <= 200 * _MSTEPS)


def test_avoid_resonant_feed_nudges_up_when_that_edge_is_closer():
    result = avoid_resonant_feed(6300, [(100, 200)], microsteps_per_step=_MSTEPS)
    assert result == 200 * _MSTEPS + 1


def test_avoid_resonant_feed_respects_ceiling_even_if_farther_edge():
    """The closer edge (above the band) would exceed the ceiling -- must
    fall back to the lower edge instead of exceeding a hard safety limit."""
    ceiling = 200 * _MSTEPS  # exactly the band's own high edge -- above is unreachable
    result = avoid_resonant_feed(6300, [(100, 200)], ceiling=ceiling, microsteps_per_step=_MSTEPS)
    assert result <= ceiling
    assert result == 100 * _MSTEPS - 1


def test_avoid_resonant_feed_respects_floor():
    floor = 100 * _MSTEPS  # exactly the band's own low edge -- below is unreachable
    result = avoid_resonant_feed(3300, [(100, 200)], floor=floor, microsteps_per_step=_MSTEPS)
    assert result >= floor
    assert result == 200 * _MSTEPS + 1


def test_avoid_resonant_feed_clamps_when_band_spans_the_whole_allowed_range():
    """Neither edge is reachable within [floor, ceiling] -- a genuinely
    unavoidable band given the caller's own limits; must return a clamped
    value rather than looping forever or raising."""
    result = avoid_resonant_feed(
        150 * _MSTEPS, [(50, 300)], floor=100 * _MSTEPS, ceiling=250 * _MSTEPS,
        microsteps_per_step=_MSTEPS,
    )
    assert 100 * _MSTEPS <= result <= 250 * _MSTEPS


def test_avoid_resonant_feed_iterates_past_adjacent_bands():
    """Nudging clear of the first band must not land inside a second,
    adjacent one -- the function should keep pushing until genuinely clear."""
    bands = [(100, 150), (150, 200)]
    result = avoid_resonant_feed(4800, bands, microsteps_per_step=_MSTEPS)  # 150 Hz -- inside both
    assert feed_in_resonance_band(result, bands, _MSTEPS) is None


def _axis_config(**overrides) -> AxisConfig:
    base = dict(
        axis=AxisId.Z,
        endstop_limit=160000,
        homing_dir_forward=True,
        invert=True,
        travel_speed=32000,
        homing_speed=16000,
        travel_accel=69000,
        endstop_bounce=1500,
        steps_per_mm=25.0,
        resonance_bands_hz=(),
    )
    base.update(overrides)
    return AxisConfig(**base)


def test_axis_resonance_warnings_empty_when_no_bands_configured():
    assert _axis_resonance_warnings(_axis_config()) == []


def test_axis_resonance_warnings_empty_when_speeds_are_clear():
    cfg = _axis_config(resonance_bands_hz=((10, 20),))  # 320-640 microsteps/s -- clear of 32000/16000
    assert _axis_resonance_warnings(cfg) == []


def test_axis_resonance_warnings_flags_travel_speed_in_band():
    # travel_speed=32000 microsteps/s = 1000 full-step Hz
    cfg = _axis_config(resonance_bands_hz=((900, 1100),))
    warnings = _axis_resonance_warnings(cfg)
    assert len(warnings) == 1
    assert "travel_speed" in warnings[0]
    assert "Z" in warnings[0]


def test_axis_resonance_warnings_flags_both_speeds_independently():
    # travel_speed=32000 -> 1000 Hz; homing_speed=16000 -> 500 Hz
    cfg = _axis_config(resonance_bands_hz=((900, 1100), (400, 600)))
    warnings = _axis_resonance_warnings(cfg)
    assert len(warnings) == 2
    assert any("travel_speed" in w for w in warnings)
    assert any("homing_speed" in w for w in warnings)
