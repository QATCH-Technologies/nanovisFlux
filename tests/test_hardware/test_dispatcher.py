import pytest

from src.hardware.commands import AxisCommand, DebugInfoCommand, HomeCommand, ProbeCommand, SimpleCommand
from src.hardware.dispatcher import Dispatcher


def test_build_rapid_move_command():
    cmd = Dispatcher.build_rapid_move_command({"X": 100, "Y": 50})
    assert isinstance(cmd, AxisCommand)
    assert str(cmd) == "G0 X100 Y50"


def test_build_rapid_move_command_requires_positions():
    with pytest.raises(ValueError):
        Dispatcher.build_rapid_move_command({})


def test_build_move_command_with_speed():
    cmd = Dispatcher.build_move_command({"X": 100}, speed=300)
    assert isinstance(cmd, AxisCommand)
    assert str(cmd) == "G1 X100 F300"


def test_build_move_command_without_speed():
    cmd = Dispatcher.build_move_command({"X": 100})
    assert str(cmd) == "G1 X100"


def test_build_move_command_rejects_nonpositive_speed():
    with pytest.raises(ValueError):
        Dispatcher.build_move_command({"X": 100}, speed=0)


def test_normalize_axis_values_matches_legacy_mixed_case_sort_order():
    # Legacy _build_axis_args sorted the ORIGINAL (mixed-case) keys before
    # uppercasing: sorted(["a", "Y"]) == ["Y", "a"] (ASCII 'Y' < 'a').
    cmd = Dispatcher.build_move_command({"a": 5, "Y": 10})
    assert str(cmd) == "G1 Y10 A5"


def test_build_home_command_no_axes():
    cmd = Dispatcher.build_home_command()
    assert isinstance(cmd, HomeCommand)
    assert str(cmd) == "G28"


def test_build_home_command_with_axes_uppercases_and_preserves_order():
    cmd = Dispatcher.build_home_command(["x", "Y"])
    assert str(cmd) == "G28 X Y"


def test_build_home_command_rejects_invalid_axis():
    with pytest.raises(ValueError):
        Dispatcher.build_home_command(["Q"])


def test_build_probe_command():
    cmd = Dispatcher.build_probe_command("z", -20000, 100, "38.2")
    assert isinstance(cmd, ProbeCommand)
    assert str(cmd) == "G38.2 Z-20000 F100"


def test_build_set_hard_limits_command():
    cmd = Dispatcher.build_set_hard_limits_command({"X": 3000, "Y": 3000})
    assert str(cmd) == "M201 X3000 Y3000"


def test_build_set_hard_limits_command_requires_limits():
    with pytest.raises(ValueError):
        Dispatcher.build_set_hard_limits_command({})


def test_build_set_accelerations_command():
    assert str(Dispatcher.build_set_accelerations_command({"X": 1000})) == "M204 X1000"


def test_build_set_homing_speeds_command():
    assert str(Dispatcher.build_set_homing_speeds_command({"X": 500})) == "M210 X500"


def test_build_set_travel_speeds_command():
    assert str(Dispatcher.build_set_travel_speeds_command({"X": 4000})) == "M220 X4000"


def test_build_set_homing_retraction_command():
    assert str(Dispatcher.build_set_homing_retraction_command({"X": 100})) == "M421 X100"


def test_set_absolute_positioning():
    cmd = Dispatcher.set_absolute_positioning()
    assert isinstance(cmd, SimpleCommand)
    assert str(cmd) == "G90"


def test_set_relative_positioning():
    assert str(Dispatcher.set_relative_positioning()) == "G91"


def test_build_position_query():
    assert str(Dispatcher.build_position_query()) == "M114"


def test_build_debug_info_command():
    cmd = Dispatcher.build_debug_info_command("35")
    assert isinstance(cmd, DebugInfoCommand)
    assert str(cmd) == "M411 READ 35"


def test_build_quick_stop():
    assert str(Dispatcher.build_quick_stop()) == "M410"


def test_build_emergency_stop():
    assert str(Dispatcher.build_emergency_stop()) == "M112"


def test_build_reset_controller_command():
    assert str(Dispatcher.build_reset_controller_command()) == "M30"


def test_build_disable_blocking_limits_command():
    assert str(Dispatcher.build_disable_blocking_limits_command()) == "M911"


def test_validate_response_accepts_command_object():
    cmd = Dispatcher.build_position_query()
    assert Dispatcher.validate_response("ok", cmd) == "ok"
