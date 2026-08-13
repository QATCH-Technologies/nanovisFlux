"""resolve_robot_config: a robot config's axes/calibration/deck/tips/
labware/mounts sections can each be given inline (the original, single-file
convention -- see src/config/robot.example.yaml) or as a path to that
section's own YAML (the split-file convention -- see configs/robot.yaml),
resolved relative to the referencing file's own directory. load_robot and
the GUI's connect flow both go through this, so both conventions must
produce the same Robot."""
from pathlib import Path

import yaml

from src.config.loader import load_robot, resolve_robot_config
from src.core import AxisId, MountSide
from src.tools import Pipette, UltrasonicSensor


def _write_yaml(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


_CALIBRATION = {
    "points": {
        "deck": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 0, "y": 10}],
        "motor": [[0, 0], [100, 0], [0, 100]],
    },
    "z_scale": {"steps_per_mm": 25.0},
}

_DECK = {
    "slots": [{"name": "1", "x": 0, "y": 0, "size": [127.85, 85.9]}],
}


def _build_split_configs(root: Path) -> Path:
    """A minimal but complete split-file layout: one axes/calibration/deck
    file, one referenced tip, one referenced labware definition (no slot of
    its own -- assigned by robot.yaml), and one referenced mount -- enough
    to exercise every reference kind resolve_robot_config supports."""
    _write_yaml(root / "axes.yaml", {"X": {"steps_per_mm": 4.57}})
    _write_yaml(root / "calibration.yaml", {"calibration": _CALIBRATION})
    _write_yaml(root / "deck.yaml", {"deck": _DECK})
    _write_yaml(root / "tools" / "tips" / "p300_tip.yaml",
                {"name": "p300_tip", "length_mm": 51.7, "max_volume_ul": 300})
    _write_yaml(root / "labware" / "source.yaml", {
        "name": "source",
        "wells": {"A1": {"x": 1.0, "y": 2.0, "z": 3.0}},
    })
    _write_yaml(root / "tools" / "pipette_p300.yaml",
                {"type": "pipette", "name": "p300", "microsteps_per_ul": 50, "max_volume_ul": 300})

    robot_path = root / "robot.yaml"
    _write_yaml(robot_path, {
        "transport": {"type": "fake"},
        "travel_z_mm": 120,
        "timeout": 30,
        "axes": "axes.yaml",
        "calibration": "calibration.yaml",
        "deck": "deck.yaml",
        "tips": ["tools/tips/p300_tip.yaml"],
        "labware": [{"slot": "1", "config": "labware/source.yaml"}],
        "mounts": {"left": "tools/pipette_p300.yaml"},
    })
    return robot_path


def test_resolve_robot_config_follows_all_reference_kinds(tmp_path):
    robot_path = _build_split_configs(tmp_path)

    cfg = resolve_robot_config(str(robot_path))

    assert cfg["axes"] == {"X": {"steps_per_mm": 4.57}}
    assert cfg["calibration"] == _CALIBRATION
    assert cfg["deck"] == _DECK
    assert cfg["tips"] == [{"name": "p300_tip", "length_mm": 51.7, "max_volume_ul": 300}]
    assert cfg["labware"] == [{"name": "source", "wells": {"A1": {"x": 1.0, "y": 2.0, "z": 3.0}}, "slot": "1"}]
    assert cfg["mounts"] == {"left": {"type": "pipette", "name": "p300",
                                       "microsteps_per_ul": 50, "max_volume_ul": 300}}
    # sections never given as a reference pass straight through untouched
    assert cfg["transport"] == {"type": "fake"}
    assert cfg["travel_z_mm"] == 120


def test_load_robot_from_split_config_builds_expected_robot(tmp_path):
    robot_path = _build_split_configs(tmp_path)

    robot = load_robot(str(robot_path))

    assert robot.axes[AxisId.X].config.steps_per_mm == 4.57
    assert robot.travel_z_mm == 120
    assert "p300_tip" in robot.tips
    assert robot.tips["p300_tip"].length_mm == 51.7
    assert "source" in robot.labware
    assert robot.labware["source"].slot.name == "1"
    tool = robot.mounts[MountSide.LEFT].tool
    assert isinstance(tool, Pipette)
    assert tool.name == "p300"
    assert tool.max_volume_ul == 300


def test_resolve_robot_config_leaves_inline_sections_untouched(tmp_path):
    """A section given inline (the original single-file convention) must
    pass through resolve_robot_config unchanged -- no reference to follow."""
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(robot_path, {
        "transport": {"type": "fake"},
        "axes": {"X": {"steps_per_mm": 9.0}},
        "calibration": _CALIBRATION,
        "deck": _DECK,
        "tips": [{"name": "cal_probe", "length_mm": 63.0}],
        "labware": [{"name": "source", "slot": "1", "wells": {"A1": {"x": 0, "y": 0, "z": 0}}}],
        "mounts": {"rear": {"type": "ultrasonic", "offset_mm": {"x": 0, "y": 50, "z": 130}}},
    })

    cfg = resolve_robot_config(str(robot_path))

    assert cfg["axes"] == {"X": {"steps_per_mm": 9.0}}
    assert cfg["tips"] == [{"name": "cal_probe", "length_mm": 63.0}]
    assert cfg["labware"] == [{"name": "source", "slot": "1", "wells": {"A1": {"x": 0, "y": 0, "z": 0}}}]
    assert cfg["mounts"]["rear"]["type"] == "ultrasonic"

    robot = load_robot(str(robot_path))
    assert isinstance(robot.mounts[MountSide.REAR].tool, UltrasonicSensor)


def test_resolve_robot_config_supports_mixed_inline_and_referenced_sections(tmp_path):
    """axes/calibration referenced by file, deck given inline -- the two
    conventions must be freely mixable within one robot.yaml."""
    _write_yaml(tmp_path / "axes.yaml", {"Y": {"steps_per_mm": 5.16}})
    _write_yaml(tmp_path / "calibration.yaml", _CALIBRATION)  # no wrapper key this time

    robot_path = tmp_path / "robot.yaml"
    _write_yaml(robot_path, {
        "transport": {"type": "fake"},
        "axes": "axes.yaml",
        "calibration": "calibration.yaml",
        "deck": _DECK,
    })

    cfg = resolve_robot_config(str(robot_path))
    assert cfg["axes"] == {"Y": {"steps_per_mm": 5.16}}
    assert cfg["calibration"] == _CALIBRATION
    assert cfg["deck"] == _DECK


def test_real_configs_robot_yaml_loads(tmp_path):
    """The actual /configs/robot.yaml shipped in the repo loads end-to-end
    and produces a robot with the labware/tips/mounts it declares."""
    repo_root = Path(__file__).resolve().parents[2]
    robot = load_robot(str(repo_root / "configs" / "robot.yaml"))

    assert robot.travel_z_mm == 120
    assert set(robot.tips) == {"p300_tip", "p20_tip", "cal_probe"}
    assert set(robot.labware) == {"tiprack1", "source", "dest", "aspirate_plate", "dispense_plate"}
    assert robot.labware["tiprack1"].slot.name == "10"
    assert robot.labware["source"].slot.name == "1"
    assert robot.labware["dest"].slot.name == "6"
    assert robot.labware["aspirate_plate"].slot.name == "7"
    assert robot.labware["dispense_plate"].slot.name == "8"
    left_tool = robot.mounts[MountSide.LEFT].tool
    assert isinstance(left_tool, Pipette) and left_tool.name == "p300"
    rear_tool = robot.mounts[MountSide.REAR].tool
    assert isinstance(rear_tool, UltrasonicSensor)


def test_real_configs_robot_yaml_matches_single_file_example():
    """The split /configs/robot.yaml and the monolithic
    src/config/robot.example.yaml describe the same physical machine --
    they should resolve to equivalent robots wherever their content
    actually overlaps (the example's transport port/travel_z_mm/timeout
    were carried over unchanged when splitting)."""
    repo_root = Path(__file__).resolve().parents[2]
    split = load_robot(str(repo_root / "configs" / "robot.yaml"))
    example = load_robot(str(repo_root / "src" / "config" / "robot.example.yaml"))

    assert split.travel_z_mm == example.travel_z_mm
    for axis in AxisId:
        assert (split.axes[axis].config.steps_per_mm
                == example.axes[axis].config.steps_per_mm)
    assert set(split.tips) == set(example.tips)
    for name, tip in split.tips.items():
        assert tip.length_mm == example.tips[name].length_mm
    assert set(split.labware) == set(example.labware)
    for name, lw in split.labware.items():
        assert lw.slot.name == example.labware[name].slot.name
