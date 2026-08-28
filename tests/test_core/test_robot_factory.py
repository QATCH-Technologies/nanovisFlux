"""gui.robot_factory.build_robot: the GUI connect flow's own robot builder,
which mirrors config.loader.load_robot's section-building but takes an
already-resolved cfg dict and a transport the GUI already chose (see that
module's own docstring). It reads pipette calibrations from the same
"_pipette_tip_calibrations" side channel resolve_robot_config populates --
this only checks that side channel actually reaches the Pipette object
here too, not the full auto-discovery mechanics (see
test_split_config_loader.py for those)."""

from pathlib import Path

import yaml

from src.config.loader import resolve_robot_config
from src.core import MountSide
from src.gui.robot_factory import build_robot
from src.transport import SimulatedTransport


def _write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def test_build_robot_picks_up_pipette_tip_calibrations(tmp_path):
    _write_yaml(
        tmp_path / "tools" / "pipette.yaml",
        {"type": "pipette", "name": "p300", "microsteps_per_ul": 50, "max_volume_ul": 300},
    )
    _write_yaml(
        tmp_path / "tools" / "p300" / "calibrations" / "tip_a.yaml",
        {
            "pipette_calibration": {
                "pipette": "p300",
                "tip": "tip A",
                "density_mg_per_ul": 0.998,
                "aspirate": [
                    {"microsteps": 1000, "volume_ul": 0.0},
                    {"microsteps": 0, "volume_ul": 100.0},
                ],
                "dispense": [
                    {"microsteps": 1000, "volume_ul": 0.0},
                    {"microsteps": 0, "volume_ul": 100.0},
                ],
            }
        },
    )
    robot_path = tmp_path / "robot.yaml"
    _write_yaml(
        robot_path,
        {
            "transport": {"type": "simulated"},
            "mounts": {"left": {"name": "p300", "config": "tools/pipette.yaml"}},
        },
    )

    cfg = resolve_robot_config(str(robot_path))
    robot = build_robot(cfg, SimulatedTransport())

    tool = robot.mounts[MountSide.LEFT].tool
    assert set(tool.tip_calibrations) == {"tip A"}
