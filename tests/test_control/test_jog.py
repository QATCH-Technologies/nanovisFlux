"""JogController feed selection: each axis jogs relative to its OWN
configured travel_speed (not one flat microsteps/s number shared by every
axis -- see control/jog.py's JogSettings docstring for why that was wrong,
particularly for Z/A's much finer microstepping), and any configured
resonance_bands_hz is avoided in the feed actually sent.

Also covers the continuous-jog lifecycle (begin_jog/end_jog, the
is_jogging flag, and the context-manager relative/absolute mode switch),
mount selection, the active-mount-relative Z/plunger convenience wrappers,
and capture_z_zero's delegation to DeckCalibration.touch_off_z_zero."""
from unittest.mock import MagicMock

from src.control.jog import JogController, JogSettings
from src.core import AxisId, MountSide
from src.robot import Robot
from src.transport.simulated import SimulatedTransport


def _robot() -> Robot:
    robot = Robot(SimulatedTransport())
    robot.connect()
    return robot


def _sent_g1_feeds(robot) -> list:
    """Every G1 line sent so far, as (axes_named, feed) pairs."""
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())
    return sent


def _nudge(jog: JogController, axis: AxisId, sign: int) -> None:
    """nudge() waits for the firmware's 'ok' (unlike continuous jog) --
    SimulatedTransport actually completes the G1 in real time (a nudge's own
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


# -- continuous-jog lifecycle ------------------------------------------------

def test_is_jogging_reflects_active_continuous_moves():
    robot = _robot()
    jog = JogController(robot)

    assert jog.is_jogging is False

    jog.begin_jog(AxisId.Z, +1, speed=1.0)
    assert jog.is_jogging is True

    jog.end_jog()
    assert jog.is_jogging is False


def test_context_manager_enters_relative_mode_and_restores_absolute_on_exit():
    robot = _robot()
    sent = _sent_g1_feeds(robot)

    with JogController(robot) as jog:
        assert sent[-1] == "G91"
        jog.begin_jog(AxisId.Z, +1, speed=1.0)
        assert jog.is_jogging

    assert jog.is_jogging is False
    # exiting must stop the active jog (quick-stop) before restoring absolute mode
    assert sent.index("G91") < sent.index("M410") < sent.index("G90")


def test_begin_jog_with_near_zero_speed_stops_the_axis_instead_of_starting():
    robot = _robot()
    jog = JogController(robot)
    jog.begin_jog(AxisId.Z, +1, speed=1.0)
    assert jog.is_jogging

    jog.begin_jog(AxisId.Z, +1, speed=0.0)

    assert jog.is_jogging is False


def test_begin_jog_repeated_with_near_identical_speed_does_not_resend():
    """High-frequency input polling shouldn't reissue an identical motion
    command every time it observes the same held input."""
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    jog.begin_jog(AxisId.Z, +1, speed=1.0)
    g1_count_after_first = len([ln for ln in sent if ln.startswith("G1")])

    jog.begin_jog(AxisId.Z, +1, speed=0.99)  # within abs_tol=0.02 of the active 1.0

    assert len([ln for ln in sent if ln.startswith("G1")]) == g1_count_after_first


def test_end_jog_with_specific_axis_stops_only_that_axis():
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    jog.begin_jog(AxisId.X, +1, speed=1.0)
    jog.begin_jog(AxisId.Z, +1, speed=1.0)

    jog.end_jog(AxisId.X)

    assert jog.is_jogging  # Z is still active
    last_g1 = [ln for ln in sent if ln.startswith("G1")][-1]
    assert "Z" in last_g1 and "X" not in last_g1


def test_end_jog_with_no_active_axes_resyncs_position_without_a_move():
    """Stopping the last active axis must not reissue a G1 -- it should quick
    stop and then resynchronize software position, since the previous
    continuous move's own acknowledgement was never read."""
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot)

    jog.begin_jog(AxisId.Z, +1, speed=1.0)
    jog.end_jog()

    assert jog.is_jogging is False
    assert sent[-2] == "M410"  # quick stop
    assert sent[-1] == "M114"  # resync position -- no new G1 issued


# -- scale, mount selection ---------------------------------------------------

def test_scale_and_jog_speed_default_to_the_middle_index():
    robot = _robot()
    jog = JogController(robot)
    assert jog.scale == jog.settings.step_scales[1] == 1.0
    assert jog.jog_speed == jog.settings.jog_speed_scales[1] == 0.4


def test_cycle_scale_advances_and_wraps_around():
    robot = _robot()
    jog = JogController(robot)  # starts at index 1 -> step_scales (0.25, 1.0, 4.0)

    assert jog.cycle_scale(1) == 4.0  # 1 -> 2
    assert jog.cycle_scale(1) == 0.25  # 2 -> wraps to 0
    assert jog.cycle_scale(-1) == 4.0  # 0 -> wraps to 2


def test_select_mount_sets_the_active_side():
    robot = _robot()
    jog = JogController(robot)

    jog.select_mount(MountSide.RIGHT)

    assert jog.side is MountSide.RIGHT


def test_toggle_mount_switches_between_left_and_right():
    robot = _robot()
    jog = JogController(robot, side=MountSide.LEFT)

    jog.toggle_mount()
    assert jog.side is MountSide.RIGHT

    jog.toggle_mount()
    assert jog.side is MountSide.LEFT


# -- active-mount-relative Z/plunger convenience wrappers ---------------------

def test_jog_z_uses_the_active_mounts_vertical_axis():
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot, side=MountSide.LEFT)

    jog.jog_z(+1)
    g1 = [ln for ln in sent if ln.startswith("G1")][-1]
    assert "Z" in g1 and "A" not in g1

    jog.side = MountSide.RIGHT
    jog.jog_z(+1)
    g1 = [ln for ln in sent if ln.startswith("G1")][-1]
    assert "A" in g1


def test_jog_plunger_uses_the_active_mounts_plunger_axis():
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot, side=MountSide.LEFT)

    jog.jog_plunger(+1)
    g1 = [ln for ln in sent if ln.startswith("G1")][-1]
    assert "B" in g1

    jog.side = MountSide.RIGHT
    jog.jog_plunger(+1)
    g1 = [ln for ln in sent if ln.startswith("G1")][-1]
    assert "C" in g1


def test_begin_and_end_jog_z_follow_the_active_mount():
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot, side=MountSide.RIGHT)

    jog.begin_jog_z(+1, speed=1.0)
    assert jog.is_jogging
    g1 = [ln for ln in sent if ln.startswith("G1")][-1]
    assert "A" in g1

    jog.end_jog_z()
    assert jog.is_jogging is False


def test_begin_and_end_jog_plunger_follow_the_active_mount():
    robot = _robot()
    sent = _sent_g1_feeds(robot)
    jog = JogController(robot, side=MountSide.RIGHT)

    jog.begin_jog_plunger(+1, speed=1.0)
    assert jog.is_jogging
    g1 = [ln for ln in sent if ln.startswith("G1")][-1]
    assert "C" in g1

    jog.end_jog_plunger()
    assert jog.is_jogging is False


# -- capture_z_zero ------------------------------------------------------------

def test_capture_z_zero_delegates_to_calibration_touch_off_with_active_side():
    """Isolated wiring test: capture_z_zero is a thin pass-through to
    DeckCalibration.touch_off_z_zero -- the calibration math itself belongs
    to (and is covered by) the geometry/calibration tests."""
    robot = _robot()
    robot.calibration = MagicMock()
    jog = JogController(robot, side=MountSide.RIGHT)

    result = jog.capture_z_zero(tip_length_mm=12.5, commit=False)

    robot.calibration.touch_off_z_zero.assert_called_once_with(
        robot, MountSide.RIGHT, 12.5, False
    )
    assert result is robot.calibration.touch_off_z_zero.return_value


def test_capture_z_zero_uses_default_tip_length_and_commit():
    robot = _robot()
    robot.calibration = MagicMock()
    jog = JogController(robot, side=MountSide.LEFT)

    jog.capture_z_zero()

    robot.calibration.touch_off_z_zero.assert_called_once_with(
        robot, MountSide.LEFT, None, True
    )
