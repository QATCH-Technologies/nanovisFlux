import json

import pytest

from src.common.robot import Robot
from src.protocol import Instruction, Protocol, ProtocolRunner
from tests.mock_connection import MockConnection

CONFIG = {
    "connection": {"default_port": "COM6", "baudrate": 115200},
    "gantry": {"safe_z_height": 100, "default_travel_speed": 4000.0},
    "calibration": {
        "X": {"steps_per_mm": 160.0, "home_offset_mm": 0.0},
        "Y": {"steps_per_mm": 160.0, "home_offset_mm": 0.0},
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

DECK_LAYOUT = {
    "slots": {
        "1": {"x_offset_mm": 0.0, "y_offset_mm": 0.0, "z_offset_mm": 0.0},
        "2": {"x_offset_mm": 132.0, "y_offset_mm": 0.0, "z_offset_mm": 0.0},
    }
}


@pytest.fixture
def robot(tmp_path):
    config_path = tmp_path / "ot2_config.json"
    config_path.write_text(json.dumps(CONFIG))
    deck_layout_path = tmp_path / "deck_layout.json"
    deck_layout_path.write_text(json.dumps(DECK_LAYOUT))
    return Robot(
        port="MOCK",
        config_path=config_path,
        deck_layout_path=deck_layout_path,
        connection_override=MockConnection(),
    )


def _transfer_protocol() -> Protocol:
    return Protocol(
        name="transfer_100ul_slot1_to_slot2",
        instructions=[
            Instruction(
                name="aspirate from slot 1",
                tool_side="left",
                action="aspirate",
                location={"slot_id": "1", "x_mm": 10.0, "y_mm": 10.0, "z_mm": 5.0},
                params={"volume": 100.0, "speed": 300.0},
            ),
            Instruction(
                name="dispense at slot 2",
                tool_side="left",
                action="dispense",
                location={"slot_id": "2", "x_mm": 10.0, "y_mm": 10.0, "z_mm": 5.0},
                params={"volume": 100.0, "speed": 300.0},
            ),
        ],
    )


def test_run_transfer_protocol(robot):
    runner = ProtocolRunner(robot)
    runner.run(_transfer_protocol())

    tool = robot.get_tool("left")
    assert tool.current_volume == pytest.approx(0.0)
    assert robot.motion.current_position["X"] == pytest.approx(142.0 * 160.0)
    assert robot.motion.current_position["Y"] == pytest.approx(10.0 * 160.0)
    assert robot.motion.current_position["Z"] == pytest.approx(5.0 * 400.0)


def test_unknown_action_raises(robot):
    runner = ProtocolRunner(robot)
    bad_instruction = Instruction(tool_side="left", action="not_a_real_action")
    with pytest.raises(AttributeError):
        runner.run_instruction(bad_instruction)


def test_load_example_protocol_file():
    protocol = Protocol.load("config/protocols/example_transfer.json")
    assert protocol.name == "transfer_100ul_slot1_to_slot2"
    assert len(protocol.instructions) == 2
