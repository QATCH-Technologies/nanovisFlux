import json

import pytest
from pynput.keyboard import KeyCode

from src.core.robot import Robot
from src.interfaces.keyboard_teleop import KeyboardTeleop
from tests.mock_connection import MockConnection

CONFIG = {
    "connection": {"default_port": "COM6", "baudrate": 115200},
    "gantry": {"safe_z_height": 100, "default_travel_speed": 4000.0},
    "calibration": {
        "X": {"steps_per_mm": 160.0, "home_offset_mm": 0.0},
        "Y": {"steps_per_mm": 160.0, "home_offset_mm": 0.0},
        "Z": {"steps_per_mm": 400.0, "home_offset_mm": 0.0},
    },
    "mounts": {
        "left": {
            "type": "pipette",
            "mount_axis": "Z",
            "plunger_axis": "B",
            "max_volume": 300.0,
            "steps_per_ul": 100,
            "blowout_distance": 100,
            "plunger_max_steps": 20000,
        },
        "right": {"type": "touch_sensor", "mount_axis": "A"},
    },
}

DECK_LAYOUT = {
    "slots": {
        "1": {"x_offset_mm": 0.0, "y_offset_mm": 0.0, "z_offset_mm": 0.0},
    }
}


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "ot2_config.json"
    path.write_text(json.dumps(CONFIG))
    return path


@pytest.fixture
def deck_layout_path(tmp_path):
    path = tmp_path / "deck_layout.json"
    path.write_text(json.dumps(DECK_LAYOUT))
    return path


def make_teleop(config_path, deck_layout_path) -> KeyboardTeleop:
    robot = Robot(
        port="MOCK",
        config_path=config_path,
        deck_layout_path=deck_layout_path,
        connection_override=MockConnection(),
    )
    return KeyboardTeleop(robot)


def test_pick_up_tip_key_invokes_tool(config_path, deck_layout_path):
    teleop = make_teleop(config_path, deck_layout_path)
    calls = []
    teleop.robot.get_tool("left").pick_up_tip = lambda *a, **k: calls.append("pick_up_tip")

    teleop.on_press(KeyCode.from_char("t"))

    assert calls == ["pick_up_tip"]


def test_drop_tip_key_invokes_tool(config_path, deck_layout_path):
    teleop = make_teleop(config_path, deck_layout_path)
    calls = []
    teleop.robot.get_tool("left").drop_tip = lambda *a, **k: calls.append("drop_tip")

    teleop.on_press(KeyCode.from_char("g"))

    assert calls == ["drop_tip"]


def test_tip_key_warns_without_raising_when_tool_lacks_method(config_path, deck_layout_path):
    teleop = make_teleop(config_path, deck_layout_path)
    teleop.active_mount = "right"  # TouchSensor has no pick_up_tip/drop_tip

    teleop.on_press(KeyCode.from_char("t"))
    teleop.on_press(KeyCode.from_char("g"))


def test_tip_key_stops_jog_before_invoking_tool(config_path, deck_layout_path):
    teleop = make_teleop(config_path, deck_layout_path)
    calls = []
    teleop.robot.motion.stop_continuous_jog = lambda: calls.append("stop")
    teleop.robot.get_tool("left").pick_up_tip = lambda *a, **k: calls.append("pick_up_tip")

    teleop.on_press(KeyCode.from_char("t"))

    assert calls == ["stop", "pick_up_tip"]


def test_tip_keys_are_single_press_not_continuous(config_path, deck_layout_path):
    teleop = make_teleop(config_path, deck_layout_path)
    calls = []
    teleop.robot.get_tool("left").pick_up_tip = lambda *a, **k: calls.append("pick_up_tip")

    teleop.on_press(KeyCode.from_char("t"))
    teleop.on_release(KeyCode.from_char("t"))

    # on_release must not stop/re-trigger anything for t/g (not in the continuous-key set)
    assert calls == ["pick_up_tip"]
