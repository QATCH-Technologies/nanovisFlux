import pytest

from src.hardware.commands import (
    AxisCommand,
    Command,
    DebugInfoCommand,
    HomeCommand,
    ProbeCommand,
    SimpleCommand,
)


def test_simple_command_renders_bare_code():
    assert SimpleCommand("G90").to_gcode() == "G90"
    assert str(SimpleCommand("M112")) == "M112"


def test_axis_command_renders_without_feed_rate():
    cmd = AxisCommand(code="G0", axis_values={"X": 100, "Y": 50})
    assert cmd.to_gcode() == "G0 X100 Y50"


def test_axis_command_renders_with_feed_rate():
    cmd = AxisCommand(code="G1", axis_values={"X": 100}, feed_rate=300)
    assert cmd.to_gcode() == "G1 X100 F300"


def test_axis_command_preserves_insertion_order_no_resort():
    # AxisCommand must NOT re-sort -- normalization/sorting is Dispatcher's job.
    cmd = AxisCommand(code="G1", axis_values={"Y": 10, "A": 5})
    assert cmd.to_gcode() == "G1 Y10 A5"


def test_axis_command_rejects_empty_values():
    with pytest.raises(ValueError):
        AxisCommand(code="G1", axis_values={})


def test_axis_command_rejects_invalid_axis():
    with pytest.raises(ValueError):
        AxisCommand(code="G1", axis_values={"Q": 1})


def test_axis_command_rejects_nonpositive_feed_rate():
    with pytest.raises(ValueError):
        AxisCommand(code="G1", axis_values={"X": 1}, feed_rate=0)


def test_axis_command_defensive_copy():
    values = {"X": 1}
    cmd = AxisCommand(code="G1", axis_values=values)
    values["X"] = 999
    assert cmd.axis_values == {"X": 1}


def test_home_command_no_axes():
    assert HomeCommand().to_gcode() == "G28"


def test_home_command_with_axes_preserves_order():
    assert HomeCommand(axes=("X", "Y")).to_gcode() == "G28 X Y"


def test_home_command_rejects_invalid_axis():
    with pytest.raises(ValueError):
        HomeCommand(axes=("Q",))


def test_probe_command_renders():
    cmd = ProbeCommand(axis="Z", target=-20000, speed=100, probe_type="38.2")
    assert cmd.to_gcode() == "G38.2 Z-20000 F100"


def test_probe_command_rejects_invalid_probe_type():
    with pytest.raises(ValueError):
        ProbeCommand(axis="Z", target=1, speed=1, probe_type="38.9")


def test_probe_command_rejects_invalid_axis():
    with pytest.raises(ValueError):
        ProbeCommand(axis="Q", target=1, speed=1)


def test_debug_info_command_renders():
    assert DebugInfoCommand(pin="35").to_gcode() == "M411 READ 35"


def test_commands_are_frozen():
    cmd = SimpleCommand("G90")
    with pytest.raises(Exception):
        cmd.code = "G91"


def test_all_commands_are_instances_of_command():
    assert isinstance(SimpleCommand("G90"), Command)
    assert isinstance(AxisCommand(code="G0", axis_values={"X": 1}), Command)
    assert isinstance(HomeCommand(), Command)
    assert isinstance(ProbeCommand(axis="X", target=1, speed=1), Command)
    assert isinstance(DebugInfoCommand(pin="1"), Command)
