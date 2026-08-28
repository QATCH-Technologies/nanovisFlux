"""resolve_robot_config: a robot config's axes/calibration/deck/tips/
labware/mounts sections can each be given inline (the original, single-file
convention -- see test_resolve_robot_config_leaves_inline_sections_untouched
below) or as a reference to that section's own YAML (the split-file
convention -- see configs/robot.yaml), resolved relative to the referencing
file's own directory. load_robot and the GUI's connect flow both go through
this, so both conventions must produce the same Robot.

tips/labware/mounts references can additionally declare the `name:` they
expect the referenced file to carry -- checked against the file's own
(_check_name_matches), so a robot.yaml reference and the file it points at
can't silently drift apart. labware entries can also carry `instance:`,
the key Robot.load_labware registers the placement under -- needed when
one reusable definition (one `name:`) is placed on more than one slot, so
the two placements don't collide in robot.labware."""

from pathlib import Path

import pytest
import yaml

from src.config.loader import load_robot, resolve_robot_config
from src.core import AxisId, MountSide
from src.tools import Pipette, TouchProbe, UltrasonicSensor


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
    file, one referenced tip (with a declared name), one referenced labware
    definition (no slot of its own -- assigned by robot.yaml), and one
    referenced mount (with a declared name) -- enough to exercise every
    reference kind resolve_robot_config supports."""
    _write_yaml(root / "axes.yaml", {"X": {"steps_per_mm": 4.57}})
    _write_yaml(root / "calibration.yaml", {"calibration": _CALIBRATION})
    _write_yaml(root / "deck.yaml", {"deck": _DECK})
    _write_yaml(
        root / "tools" / "tips" / "p300_tip.yaml",
        {"name": "p300_tip", "length_mm": 51.7, "max_volume_ul": 300},
    )
    _write_yaml(
        root / "labware" / "source.yaml",
        {
            "name": "wellplate",
            "wells": {"A1": {"x": 1.0, "y": 2.0, "z": 3.0}},
        },
    )
    _write_yaml(
        root / "tools" / "pipette_opentrons_single_channel_gen1_p300.yaml",
        {"type": "pipette", "name": "p300", "microsteps_per_ul": 50, "max_volume_ul": 300},
    )

    robot_path = root / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "travel_z_mm": 120,
            "timeout": 30,
            "axes": "axes.yaml",
            "calibration": "calibration.yaml",
            "deck": "deck.yaml",
            "tips": [{"name": "p300_tip", "config": "tools/tips/p300_tip.yaml"}],
            "labware": [
                {
                    "slot": "1",
                    "instance": "source",
                    "name": "wellplate",
                    "config": "labware/source.yaml",
                }
            ],
            "mounts": {
                "left": {
                    "name": "p300",
                    "config": "tools/pipette_opentrons_single_channel_gen1_p300.yaml",
                }
            },
        },
    )
    return robot_path


def test_resolve_robot_config_follows_all_reference_kinds(tmp_path):
    robot_path = _build_split_configs(tmp_path)

    cfg = resolve_robot_config(str(robot_path))

    assert cfg["axes"] == {"X": {"steps_per_mm": 4.57}}
    assert cfg["calibration"] == _CALIBRATION
    assert cfg["deck"] == _DECK
    assert cfg["tips"] == [{"name": "p300_tip", "length_mm": 51.7, "max_volume_ul": 300}]
    assert cfg["labware"] == [
        {
            "name": "wellplate",
            "wells": {"A1": {"x": 1.0, "y": 2.0, "z": 3.0}},
            "slot": "1",
            "instance": "source",
        }
    ]
    assert cfg["mounts"] == {
        "left": {"type": "pipette", "name": "p300", "microsteps_per_ul": 50, "max_volume_ul": 300}
    }
    # sections never given as a reference pass straight through untouched
    assert cfg["transport"] == {"type": "simulated"}
    assert cfg["travel_z_mm"] == 120


def test_load_robot_from_split_config_builds_expected_robot(tmp_path):
    robot_path = _build_split_configs(tmp_path)

    robot = load_robot(str(robot_path))

    assert robot.axes[AxisId.X].config.steps_per_mm == 4.57
    assert robot.travel_z_mm == 120
    assert "p300_tip" in robot.tips
    assert robot.tips["p300_tip"].length_mm == 51.7
    # addressed by its declared instance, not the shared definition name
    assert "source" in robot.labware
    assert robot.labware["source"].slot.name == "1"
    assert robot.labware["source"].name == "wellplate"
    tool = robot.mounts[MountSide.LEFT].tool
    assert isinstance(tool, Pipette)
    assert tool.name == "p300"
    # no calibrations/p300/ directory next to the pipette file -> falls
    # back to the linear PlungerModel, same as before this ever existed
    assert tool.tip_calibrations == {}


# -- per-tip calibrations, auto-discovered from calibrations/<pipette name>/ -


def _write_pipette_calibration(path: Path, *, pipette: str, tip: str) -> None:
    """A minimal but valid pipette_calibration: file, in the shape
    scripts/calibrate_pipette.py writes -- no side: (see this module's own
    docstring: mount side doesn't affect a plunger's steps<->volume
    mapping, so calibrations/ is never split by side the way mounts: is)."""
    _write_yaml(
        path,
        {
            "pipette_calibration": {
                "pipette": pipette,
                "tip": tip,
                "density_mg_per_ul": 0.998,
                "aspirate": [{"microsteps": 1000, "volume_ul": 0.0}, {"microsteps": 0, "volume_ul": 100.0}],
                "dispense": [{"microsteps": 1000, "volume_ul": 0.0}, {"microsteps": 0, "volume_ul": 100.0}],
            }
        },
    )


def test_load_robot_auto_discovers_pipette_tip_calibrations(tmp_path):
    """Every *.yaml under <pipette file's own dir>/<pipette name>/
    calibrations/ becomes one Pipette.tip_calibrations entry, keyed by
    that file's own tip: -- no explicit listing needed in the pipette's
    own tool file or in robot.yaml."""
    robot_path = _build_split_configs(tmp_path)
    calib_dir = tmp_path / "tools" / "p300" / "calibrations"
    _write_pipette_calibration(calib_dir / "tip_a.yaml", pipette="p300", tip="tip A")
    _write_pipette_calibration(calib_dir / "tip_b.yaml", pipette="p300", tip="tip B")

    robot = load_robot(str(robot_path))

    tool = robot.mounts[MountSide.LEFT].tool
    assert set(tool.tip_calibrations) == {"tip A", "tip B"}
    assert tool.tip_calibrations["tip A"].microsteps_for_volume(100.0, aspirating=True) == 0


def test_pipette_tip_calibrations_are_side_agnostic(tmp_path):
    """The same <pipette name>/calibrations/ directory applies wherever
    this pipette is mounted -- calibrating on one side and later moving
    the pipette to the other mount doesn't lose its calibrations."""
    _write_yaml(
        tmp_path / "tools" / "pipette.yaml",
        {"type": "pipette", "name": "p300", "microsteps_per_ul": 50, "max_volume_ul": 300},
    )
    _write_pipette_calibration(
        tmp_path / "tools" / "p300" / "calibrations" / "tip_a.yaml", pipette="p300", tip="tip A"
    )
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "mounts": {
                "left": {"name": "p300", "config": "tools/pipette.yaml"},
                "right": {"name": "p300", "config": "tools/pipette.yaml"},
            },
        },
    )

    robot = load_robot(str(robot_path))

    assert set(robot.mounts[MountSide.LEFT].tool.tip_calibrations) == {"tip A"}
    assert set(robot.mounts[MountSide.RIGHT].tool.tip_calibrations) == {"tip A"}


def test_pipette_calibration_file_pipette_name_mismatch_raises(tmp_path):
    """A calibration file's declared pipette: must agree with the
    <pipette name>/calibrations/ directory it's found under -- catches a
    copy-pasted or misplaced file instead of silently attaching someone
    else's measurements."""
    robot_path = _build_split_configs(tmp_path)
    _write_pipette_calibration(
        tmp_path / "tools" / "p300" / "calibrations" / "tip_a.yaml",
        pipette="some_other_pipette",
        tip="tip A",
    )

    with pytest.raises(ValueError, match="some_other_pipette"):
        load_robot(str(robot_path))


def test_brand_field_plumbed_through_to_labware_tips_and_tools(tmp_path):
    """brand: (vendor/manufacturer) travels alongside name: through every
    labware/tip/tool builder onto the runtime object, the same way name:
    does -- Labware, TipGeometry, Pipette, UltrasonicSensor, TouchProbe all
    expose it. Omitting brand: defaults to "" (unknown/custom), same as an
    inline config with no brand at all."""
    _write_yaml(
        tmp_path / "labware" / "plate.yaml",
        {
            "name": "branded_plate",
            "brand": "Corning",
            "wells": {"A1": {"x": 0, "y": 0, "z": 0}},
        },
    )
    _write_yaml(
        tmp_path / "deck.yaml",
        {"deck": {"slots": [{"name": "1", "x": 0, "y": 0, "size": [10, 10]}]}},
    )
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "deck": "deck.yaml",
            "tips": [{"name": "branded_tip", "brand": "Opentrons", "length_mm": 50.0}],
            "labware": [{"slot": "1", "name": "branded_plate", "config": "labware/plate.yaml"}],
            "mounts": {
                "left": {
                    "type": "pipette",
                    "name": "p1000",
                    "brand": "Gilson",
                    "microsteps_per_ul": 50,
                    "max_volume_ul": 1000,
                },
                "right": {
                    "type": "touch_probe",
                    "name": "probe",
                    "brand": "in-house",
                    "length_mm": 10.0,
                },
                "rear": {"type": "ultrasonic", "name": "sensor"},  # no brand: at all
            },
        },
    )

    robot = load_robot(str(robot_path))

    assert robot.labware["branded_plate"].brand == "Corning"
    assert robot.tips["branded_tip"].brand == "Opentrons"
    assert robot.mounts[MountSide.LEFT].tool.brand == "Gilson"
    assert robot.mounts[MountSide.RIGHT].tool.brand == "in-house"
    assert robot.mounts[MountSide.REAR].tool.brand == ""  # omitted -- defaults, doesn't error


def test_pipette_channels_defaults_to_one_and_is_configurable(tmp_path):
    """channels: (how many tips/wells one plunger stroke handles) defaults
    to 1 -- single-channel -- when omitted, same convention as brand:, and
    is otherwise read straight through to the Pipette object."""
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "mounts": {
                "left": {
                    "type": "pipette",
                    "name": "p300",
                    "microsteps_per_ul": 50,
                    "max_volume_ul": 300,
                },
                "right": {
                    "type": "pipette",
                    "name": "p300-multi",
                    "channels": 8,
                    "microsteps_per_ul": 50,
                    "max_volume_ul": 300,
                },
            },
        },
    )

    robot = load_robot(str(robot_path))

    assert robot.mounts[MountSide.LEFT].tool.channels == 1
    assert robot.mounts[MountSide.RIGHT].tool.channels == 8


def test_resolve_robot_config_leaves_inline_sections_untouched(tmp_path):
    """A section given inline (the original single-file convention) must
    pass through resolve_robot_config unchanged -- no reference to follow."""
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "axes": {"X": {"steps_per_mm": 9.0}},
            "calibration": _CALIBRATION,
            "deck": _DECK,
            "tips": [{"name": "3d_touch_probe", "length_mm": 63.0}],
            "labware": [{"name": "source", "slot": "1", "wells": {"A1": {"x": 0, "y": 0, "z": 0}}}],
            "mounts": {"rear": {"type": "ultrasonic", "max_range_mm": 4000}},
        },
    )

    cfg = resolve_robot_config(str(robot_path))

    assert cfg["axes"] == {"X": {"steps_per_mm": 9.0}}
    assert cfg["tips"] == [{"name": "3d_touch_probe", "length_mm": 63.0}]
    assert cfg["labware"] == [
        {"name": "source", "slot": "1", "wells": {"A1": {"x": 0, "y": 0, "z": 0}}}
    ]
    assert cfg["mounts"]["rear"]["type"] == "ultrasonic"

    robot = load_robot(str(robot_path))
    assert isinstance(robot.mounts[MountSide.REAR].tool, UltrasonicSensor)


def test_resolve_robot_config_supports_mixed_inline_and_referenced_sections(tmp_path):
    """axes/calibration referenced by file, deck given inline -- the two
    conventions must be freely mixable within one robot.yaml."""
    _write_yaml(tmp_path / "axes.yaml", {"Y": {"steps_per_mm": 5.16}})
    _write_yaml(tmp_path / "calibration.yaml", _CALIBRATION)  # no wrapper key this time

    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "axes": "axes.yaml",
            "calibration": "calibration.yaml",
            "deck": _DECK,
        },
    )

    cfg = resolve_robot_config(str(robot_path))
    assert cfg["axes"] == {"Y": {"steps_per_mm": 5.16}}
    assert cfg["calibration"] == _CALIBRATION
    assert cfg["deck"] == _DECK


# -- name consistency: object / config-reference / file must agree ----------


def test_resolve_robot_config_raises_on_labware_name_mismatch(tmp_path):
    _write_yaml(
        tmp_path / "labware" / "plate.yaml",
        {"name": "real_name", "wells": {"A1": {"x": 0, "y": 0, "z": 0}}},
    )
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "labware": [{"slot": "1", "name": "wrong_name", "config": "labware/plate.yaml"}],
        },
    )
    with pytest.raises(ValueError, match="wrong_name"):
        resolve_robot_config(str(robot_path))


def test_resolve_robot_config_raises_on_tip_name_mismatch(tmp_path):
    _write_yaml(tmp_path / "tools" / "tips" / "tip.yaml", {"name": "real_tip", "length_mm": 50.0})
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "tips": [{"name": "wrong_tip", "config": "tools/tips/tip.yaml"}],
        },
    )
    with pytest.raises(ValueError, match="wrong_tip"):
        resolve_robot_config(str(robot_path))


def test_resolve_robot_config_raises_on_mount_name_mismatch(tmp_path):
    _write_yaml(
        tmp_path / "tools" / "tool.yaml",
        {"type": "pipette", "name": "real_pipette", "microsteps_per_ul": 50, "max_volume_ul": 300},
    )
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "mounts": {"left": {"name": "wrong_pipette", "config": "tools/tool.yaml"}},
        },
    )
    with pytest.raises(ValueError, match="wrong_pipette"):
        resolve_robot_config(str(robot_path))


# -- one reusable definition, placed on more than one slot -------------------


def test_shared_labware_definition_addressed_by_distinct_instance_keys(tmp_path):
    """The same reusable labware definition (one `name:`) placed on two
    slots must land under two distinct robot.labware keys (its declared
    `instance:` per placement) -- not silently overwrite each other, which
    is what a bare Robot.labware[labware.name] keying would do."""
    _write_yaml(
        tmp_path / "labware" / "plate.yaml",
        {
            "name": "shared_plate",
            "wells": {"A1": {"x": 1.0, "y": 2.0, "z": 3.0}},
        },
    )
    _write_yaml(
        tmp_path / "deck.yaml",
        {
            "deck": {
                "slots": [
                    {"name": "1", "x": 0, "y": 0, "size": [10, 10]},
                    {"name": "2", "x": 20, "y": 0, "size": [10, 10]},
                ]
            }
        },
    )
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "deck": "deck.yaml",
            "labware": [
                {
                    "slot": "1",
                    "instance": "source",
                    "name": "shared_plate",
                    "config": "labware/plate.yaml",
                },
                {
                    "slot": "2",
                    "instance": "dest",
                    "name": "shared_plate",
                    "config": "labware/plate.yaml",
                },
            ],
        },
    )

    robot = load_robot(str(robot_path))

    assert set(robot.labware) == {"source", "dest"}
    assert robot.labware["source"].slot.name == "1"
    assert robot.labware["dest"].slot.name == "2"
    # both placements still carry the shared physical identity
    assert robot.labware["source"].name == "shared_plate"
    assert robot.labware["dest"].name == "shared_plate"


def test_labware_instance_defaults_to_definition_name_when_omitted(tmp_path):
    """A single placement doesn't need `instance:` -- it falls back to the
    definition's own `name:`, matching the pre-instance behavior."""
    _write_yaml(
        tmp_path / "labware" / "plate.yaml",
        {
            "name": "only_plate",
            "wells": {"A1": {"x": 0, "y": 0, "z": 0}},
        },
    )
    _write_yaml(
        tmp_path / "deck.yaml",
        {"deck": {"slots": [{"name": "1", "x": 0, "y": 0, "size": [10, 10]}]}},
    )
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "deck": "deck.yaml",
            "labware": [{"slot": "1", "name": "only_plate", "config": "labware/plate.yaml"}],
        },
    )

    robot = load_robot(str(robot_path))
    assert set(robot.labware) == {"only_plate"}


# -- the real /configs tree ---------------------------------------------------


def test_real_configs_robot_yaml_loads(tmp_path):
    """The actual /configs/robot.yaml shipped in the repo loads end-to-end
    and produces a robot with the labware/tips/mounts it declares, each
    placement addressable by its own instance key."""
    repo_root = Path(__file__).resolve().parents[2]
    robot = load_robot(str(repo_root / "configs" / "robot.yaml"))

    assert robot.travel_z_mm == 120
    # 3d_touch_probe is a mounted touch probe now, not a pipette tip
    assert set(robot.tips) == {"opentrons_p300_ot2_tip", "geb_p20_tip"}
    assert set(robot.labware) == {"tiprack1", "source", "dest", "aspirate_plate", "dispense_plate"}
    assert robot.labware["tiprack1"].slot.name == "10"
    assert robot.labware["source"].slot.name == "1"
    assert robot.labware["dest"].slot.name == "3"
    assert robot.labware["aspirate_plate"].slot.name == "7"
    assert robot.labware["dispense_plate"].slot.name == "8"
    # aspirate/dispense share one reusable definition; source (a 96-well
    # plate) and dest (a distinct 24-well plate) are each their own
    assert robot.labware["source"].name == "biorad_96_microplate"
    assert robot.labware["dest"].name == "qatch_nanoflux_24_well_plate"
    assert (
        robot.labware["aspirate_plate"].name
        == robot.labware["dispense_plate"].name
        == "opentrons_ot2_tip_rack_lid"
    )
    # brand: a known vendor part carries its real brand; unknowns carry the
    # TODO_brand placeholder, same convention as an unresolved name
    assert robot.labware["tiprack1"].name == "opentrons_300ul_ot2_tip_rack"
    assert robot.labware["tiprack1"].brand == "Opentrons"
    assert robot.labware["source"].brand == "Bio-Rad"
    left_tool = robot.mounts[MountSide.LEFT].tool
    assert isinstance(left_tool, Pipette) and left_tool.name == "opentrons_single_channel_gen1_p300"
    assert left_tool.channels == 1
    right_tool = robot.mounts[MountSide.RIGHT].tool
    assert isinstance(right_tool, TouchProbe)
    assert right_tool.name == "3d_touch_probe"
    assert right_tool.length_mm == 63.0
    assert right_tool.brand == "UNKNOWN"
    rear_tool = robot.mounts[MountSide.REAR].tool
    assert isinstance(rear_tool, UltrasonicSensor)
    assert rear_tool.name == "tk50_ultrasonic_sensor"


