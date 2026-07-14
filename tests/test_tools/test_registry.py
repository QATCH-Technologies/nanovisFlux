import pytest

from src.tools import Pipette, TouchSensor, create_tool, register_tool
from src.tools.base import Tool


def test_create_tool_pipette():
    tool_data = {
        "plunger_axis": "B",
        "max_volume": 300.0,
        "steps_per_ul": 100,
        "blowout_distance": 100,
    }
    tool = create_tool("pipette", tool_data, motion=object())
    assert isinstance(tool, Pipette)
    assert tool.axis == "B"
    assert tool.max_volume == 300.0


def test_create_tool_touch_sensor():
    tool_data = {"mount_axis": "A"}
    tool = create_tool("touch_sensor", tool_data, motion=object())
    assert isinstance(tool, TouchSensor)
    assert tool.mount_axis == "A"


def test_create_tool_unknown_type_raises():
    with pytest.raises(ValueError):
        create_tool("bogus", {}, motion=object())


def test_third_tool_extensibility_via_registry():
    @register_tool("__test_fake_tool__")
    class FakeTool(Tool):
        @classmethod
        def from_config(cls, tool_data: dict, motion) -> "FakeTool":
            return cls(mount_axis=tool_data.get("mount_axis", "X"), motion=motion)

    tool = create_tool("__test_fake_tool__", {"mount_axis": "y"}, motion=object())
    assert isinstance(tool, FakeTool)
    assert tool.mount_axis == "Y"
