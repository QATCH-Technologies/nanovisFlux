import json

import pytest

from src.core.deck import DeckLocation
from src.core.robot import Robot
from src.tools import Pipette, TouchSensor
from tests.mock_connection import MockConnection

MINIMAL_CONFIG = {
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
        },
        "right": {"type": "touch_sensor", "mount_axis": "A"},
    },
}

MINIMAL_DECK_LAYOUT = {
    "slots": {
        "1": {"x_offset_mm": 0.0, "y_offset_mm": 0.0, "z_offset_mm": 0.0},
        "2": {"x_offset_mm": 132.0, "y_offset_mm": 0.0, "z_offset_mm": 0.0},
    }
}


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "ot2_config.json"
    path.write_text(json.dumps(MINIMAL_CONFIG))
    return path


@pytest.fixture
def deck_layout_path(tmp_path):
    path = tmp_path / "deck_layout.json"
    path.write_text(json.dumps(MINIMAL_DECK_LAYOUT))
    return path


def _make_robot(config_path, deck_layout_path):
    return Robot(
        port="MOCK",
        config_path=config_path,
        deck_layout_path=deck_layout_path,
        connection_override=MockConnection(),
    )


def test_init_tool_matches_legacy_behavior(config_path, deck_layout_path):
    robot = _make_robot(config_path, deck_layout_path)
    assert isinstance(robot.left_tool, Pipette)
    assert isinstance(robot.right_tool, TouchSensor)


def test_get_tool_returns_configured_tools(config_path, deck_layout_path):
    robot = _make_robot(config_path, deck_layout_path)
    assert robot.get_tool("left") is robot.left_tool
    assert robot.get_tool("right") is robot.right_tool


def test_calibration_and_deck_populate(config_path, deck_layout_path):
    robot = _make_robot(config_path, deck_layout_path)
    assert robot.calibration is not None
    assert robot.deck is not None


def test_move_to_location_resolves_expected_steps(config_path, deck_layout_path):
    robot = _make_robot(config_path, deck_layout_path)
    robot.move_to_location(DeckLocation(slot_id="2", x_mm=10.0, y_mm=10.0, z_mm=5.0))
    assert robot.motion.current_position["X"] == pytest.approx(142.0 * 160.0)
    assert robot.motion.current_position["Y"] == pytest.approx(10.0 * 160.0)
    assert robot.motion.current_position["Z"] == pytest.approx(5.0 * 400.0)
