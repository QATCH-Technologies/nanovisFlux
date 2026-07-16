import json

import pytest

from src.common.robot import Robot
from src.core.deck import DeckLocation
from src.tools import Pipette, TouchSensor
from tests.mock_connection import MockConnection

MINIMAL_CONFIG = {
    "connection": {"default_port": "COM6", "baudrate": 115200},
    "gantry": {"safe_z_height": 100, "default_travel_speed": 4000.0},
    "calibration": {
        "Z": {"steps_per_mm": 400.0, "home_offset_mm": 0.0},
    },
    "deck_calibration": {
        "origin_steps": {"x": 0.0, "y": 0.0},
        "x_reference_steps": {"x": 160.0},
        "x_reference_mm": 1.0,
        "y_reference_steps": {"y": 160.0},
        "y_reference_mm": 1.0,
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
    assert robot.deck_calibration is not None


def test_move_to_location_resolves_expected_steps(config_path, deck_layout_path):
    robot = _make_robot(config_path, deck_layout_path)
    robot.move_to_location(DeckLocation(slot_id="2", x_mm=10.0, y_mm=10.0, z_mm=5.0))
    assert robot.motion.current_position["X"] == pytest.approx(142.0 * 160.0)
    assert robot.motion.current_position["Y"] == pytest.approx(10.0 * 160.0)
    assert robot.motion.current_position["Z"] == pytest.approx(5.0 * 400.0)


CONFIG_WITH_COORDINATE_SYSTEM = {
    **MINIMAL_CONFIG,
    "physical_envelope": [
        {"X": 0.0, "Y": 0.0, "Z": 0.0},
        {"X": 60000.0, "Y": 52000.0, "Z": 160000.0},
    ],
    "mount_offsets": {
        "left": {"X": 100.0, "Y": 200.0, "Z": 300.0},
        "right": {"X": 400.0, "Y": 500.0, "A": 600.0},
    },
}


@pytest.fixture
def coordinate_config_path(tmp_path):
    path = tmp_path / "ot2_config_coords.json"
    path.write_text(json.dumps(CONFIG_WITH_COORDINATE_SYSTEM))
    return path


def test_physical_envelope_and_mount_offsets_populate(coordinate_config_path, deck_layout_path):
    robot = _make_robot(coordinate_config_path, deck_layout_path)
    assert robot.physical_envelope is not None
    assert robot.mount_offsets is not None


def test_move_to_location_applies_mount_offset_for_right_mount(
    coordinate_config_path, deck_layout_path
):
    robot = _make_robot(coordinate_config_path, deck_layout_path)
    robot.move_to_location(DeckLocation(slot_id="1", x_mm=0.0, y_mm=0.0, z_mm=0.0), mount="right")
    # Z target is reframed onto the right mount's own vertical axis (A), offset applied.
    assert robot.motion.current_position["A"] == pytest.approx(600.0)
    assert robot.motion.current_position["X"] == pytest.approx(400.0)
    assert robot.motion.current_position["Y"] == pytest.approx(500.0)
    # Z itself was never part of this command -- still sitting at its homed value.
    assert robot.motion.current_position["Z"] == pytest.approx(0.0)


def test_move_to_location_applies_mount_offset_for_left_mount(
    coordinate_config_path, deck_layout_path
):
    robot = _make_robot(coordinate_config_path, deck_layout_path)
    robot.move_to_location(DeckLocation(slot_id="1", x_mm=0.0, y_mm=0.0, z_mm=0.0), mount="left")
    assert robot.motion.current_position["X"] == pytest.approx(100.0)
    assert robot.motion.current_position["Y"] == pytest.approx(200.0)
    assert robot.motion.current_position["Z"] == pytest.approx(300.0)


def test_move_to_location_raises_outside_physical_envelope(
    coordinate_config_path, deck_layout_path
):
    robot = _make_robot(coordinate_config_path, deck_layout_path)
    with pytest.raises(RuntimeError):
        # Z steps = 500 * 400 = 200000, beyond the calibrated 0-160000 envelope.
        robot.move_to_location(DeckLocation(slot_id="1", x_mm=0.0, y_mm=0.0, z_mm=500.0))


def test_move_to_location_raises_without_deck_calibration(tmp_path, deck_layout_path):
    config = {k: v for k, v in MINIMAL_CONFIG.items() if k != "deck_calibration"}
    path = tmp_path / "ot2_config_no_deck_cal.json"
    path.write_text(json.dumps(config))
    robot = _make_robot(path, deck_layout_path)
    assert robot.deck_calibration is None
    with pytest.raises(RuntimeError):
        robot.move_to_location(DeckLocation(slot_id="1"))
