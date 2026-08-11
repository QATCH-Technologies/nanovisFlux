"""Calibration persistence: a calibration saved from the GUI (see
gui/calibration_dialog.py's "Save calibration..." button) lives in a
sidecar file next to whatever config was used to connect, and
config.loader.load_robot picks it up automatically -- so recalibrating once
means never redoing it on a later connect with that same config."""
import yaml

from src.config.loader import calibration_sidecar_path, load_calibration_override, load_robot


def _write_yaml(path, data) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def test_calibration_sidecar_path_naming():
    assert str(calibration_sidecar_path("robot.yaml")) == "robot.calibration.yaml"
    assert str(calibration_sidecar_path("robot.example.yaml")) == "robot.example.calibration.yaml"
    assert str(calibration_sidecar_path("/a/b/robot.yml")).replace("\\", "/") == "/a/b/robot.calibration.yml"


def test_load_calibration_override_none_without_sidecar(tmp_path):
    config_path = tmp_path / "robot.yaml"
    _write_yaml(config_path, {"deck": {}})
    assert load_calibration_override(str(config_path)) is None


def test_load_calibration_override_reads_sidecar(tmp_path):
    config_path = tmp_path / "robot.yaml"
    sidecar_data = {
        "points": {"deck": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 0, "y": 10}],
                  "motor": [[0, 0], [200, 0], [0, 200]]},
        "z_scale": {"steps_per_mm": 25.0},
    }
    _write_yaml(calibration_sidecar_path(str(config_path)), {"calibration": sidecar_data})
    assert load_calibration_override(str(config_path)) == sidecar_data


def test_load_robot_prefers_sidecar_calibration_over_config(tmp_path):
    config_path = tmp_path / "robot.yaml"
    _write_yaml(config_path, {
        "transport": {"type": "fake"},
        "calibration": {
            "points": {"deck": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 0, "y": 10}],
                      "motor": [[0, 0], [100, 0], [0, 100]]},   # scale 10
            "z_scale": {"steps_per_mm": 25.0},
        },
    })
    _write_yaml(calibration_sidecar_path(str(config_path)), {
        "calibration": {
            "points": {"deck": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 0, "y": 10}],
                      "motor": [[0, 0], [200, 0], [0, 200]]},   # scale 20 -- the persisted recalibration
            "z_scale": {"steps_per_mm": 25.0},
        },
    })

    robot = load_robot(str(config_path))

    mx, my = robot.calibration.xy.apply(5.0, 5.0)
    assert (mx, my) == (100.0, 100.0)   # scale-20 sidecar, not scale-10 config


def test_load_robot_without_sidecar_uses_config_calibration(tmp_path):
    config_path = tmp_path / "robot.yaml"
    _write_yaml(config_path, {
        "transport": {"type": "fake"},
        "calibration": {
            "points": {"deck": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 0, "y": 10}],
                      "motor": [[0, 0], [100, 0], [0, 100]]},
            "z_scale": {"steps_per_mm": 25.0},
        },
    })

    robot = load_robot(str(config_path))

    mx, my = robot.calibration.xy.apply(5.0, 5.0)
    assert (mx, my) == (50.0, 50.0)
