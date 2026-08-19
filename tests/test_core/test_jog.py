"""JogController feed selection: each axis jogs relative to its OWN
configured travel_speed (not one flat microsteps/s number shared by every
axis -- see control/jog.py's JogSettings docstring for why that was wrong,
particularly for Z/A's much finer microstepping), and any configured
resonance_bands_hz is avoided in the feed actually sent."""
from src.control.jog import JogController, JogSettings
from src.core import AxisId, MountSide
from src.robot import Robot
from src.transport.fake import FakeTransport


def _robot() -> Robot:
    robot = Robot(FakeTransport())
    robot.connect()
    return robot


def _sent_g1_feeds(robot) -> list:
    """Every G1 line sent so far, as (axes_named, feed) pairs."""
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())
    return sent


def _nudge(jog: JogController, axis: AxisId, sign: int) -> None:
    """nudge() waits for the firmware's 'ok' (unlike continuous jog) --
    FakeTransport actually completes the G1 in real time (a nudge's own
    step_microsteps distance is tiny, so this resolves in milliseconds,
    not a real wait); the G1 line itself is captured via on_send() before
    that (brief) wait, same as with continuous jog's fire-and-forget."""
    jog.nudge(axis, sign)


def test_nudge_uses_the_axis_own_travel_speed_as_feed():
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    _nudge(jog, AxisId.Z, +1)

    g1 = next(ln for ln in sent if ln.startswith("G1"))
    assert f"F{int(robot.axes[AxisId.Z].config.travel_speed)}" in g1


def test_nudge_differs_per_axis_matching_their_own_travel_speed():
    """The core bug this fixes: X and Z used to get the exact same flat
    feed regardless of their very different microsteps/mm. Now each
    nudge's feed should match that specific axis's own travel_speed."""
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    _nudge(jog, AxisId.X, +1)
    _nudge(jog, AxisId.Z, +1)

    g1_lines = [ln for ln in sent if ln.startswith("G1")]
    assert len(g1_lines) == 2
    x_feed = int(robot.axes[AxisId.X].config.travel_speed)
    z_feed = int(robot.axes[AxisId.Z].config.travel_speed)
    assert x_feed != z_feed  # sanity: the two axes really do differ
    assert f"F{x_feed}" in g1_lines[0]
    assert f"F{z_feed}" in g1_lines[1]


def test_nudge_scales_with_jog_speed_fraction():
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot, settings=JogSettings(jog_speed_fraction=0.5))

    _nudge(jog, AxisId.Z, +1)

    g1 = next(ln for ln in sent if ln.startswith("G1"))
    expected = int(robot.axes[AxisId.Z].config.travel_speed * 0.5)
    assert f"F{expected}" in g1


def test_continuous_jog_single_axis_uses_that_axis_ceiling_at_full_speed():
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    jog.begin_jog(AxisId.Z, +1, speed=1.0)

    g1 = next(ln for ln in sent if ln.startswith("G1"))
    assert f"F{int(robot.axes[AxisId.Z].config.travel_speed)}" in g1


def test_continuous_jog_multiple_axes_uses_the_slower_ceiling():
    """X and Z held together: firmware applies one shared F to every named
    axis on the line, so the feed must never exceed EITHER axis's own
    ceiling -- the minimum across held axes, not (e.g.) Z's higher one."""
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    jog.begin_jog(AxisId.X, +1, speed=1.0)
    jog.begin_jog(AxisId.Z, +1, speed=1.0)

    g1 = [ln for ln in sent if ln.startswith("G1")][-1]
    x_speed = robot.axes[AxisId.X].config.travel_speed
    z_speed = robot.axes[AxisId.Z].config.travel_speed
    expected = int(min(x_speed, z_speed))
    assert f"F{expected}" in g1
    assert "X" in g1 and "Z" in g1


def test_continuous_jog_speed_fraction_scales_the_feed():
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    jog.begin_jog(AxisId.Z, +1, speed=0.5)

    g1 = next(ln for ln in sent if ln.startswith("G1"))
    expected = int(robot.axes[AxisId.Z].config.travel_speed * 0.5)
    assert f"F{expected}" in g1


def test_nudge_avoids_a_configured_resonance_band():
    """Z's travel_speed itself sits inside a configured resonance band --
    the nudge sent must NOT use that raw value, and must land outside the
    band's microsteps/s range."""
    robot = _robot()
    z_cfg = robot.axes[AxisId.Z].config
    travel_hz_full_step = z_cfg.travel_speed / 32  # MICROSTEPS_PER_STEP
    z_cfg.resonance_bands_hz = ((travel_hz_full_step - 10, travel_hz_full_step + 10),)
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    _nudge(jog, AxisId.Z, +1)

    g1 = next(ln for ln in sent if ln.startswith("G1"))
    i = g1.find("F")
    sent_feed = int(g1[i + 1:])
    band_low_us = (travel_hz_full_step - 10) * 32
    band_high_us = (travel_hz_full_step + 10) * 32
    assert not (band_low_us <= sent_feed <= band_high_us)
    assert sent_feed <= z_cfg.travel_speed  # never exceeds the axis's own ceiling


def test_continuous_jog_avoids_resonance_band_across_held_axes():
    """A band configured on Z must also be avoided in a combined X+Z jog
    line, since one shared F applies to every axis the line names."""
    robot = _robot()
    z_cfg = robot.axes[AxisId.Z].config
    x_speed = robot.axes[AxisId.X].config.travel_speed
    ceiling = min(x_speed, z_cfg.travel_speed)
    ceiling_hz = ceiling / 32
    z_cfg.resonance_bands_hz = ((ceiling_hz - 5, ceiling_hz + 5),)
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    jog.begin_jog(AxisId.X, +1, speed=1.0)
    jog.begin_jog(AxisId.Z, +1, speed=1.0)

    g1 = [ln for ln in sent if ln.startswith("G1")][-1]
    i = g1.find("F")
    sent_feed = int(g1[i + 1:])
    band_low_us = (ceiling_hz - 5) * 32
    band_high_us = (ceiling_hz + 5) * 32
    assert not (band_low_us <= sent_feed <= band_high_us)
