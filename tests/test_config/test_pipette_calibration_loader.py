"""build_pipette_calibration/load_pipette_calibration: turning
scripts/calibrate_pipette.py's YAML output back into a usable
PlungerCalibration -- see config/loader.py's calibration_sidecar_path-
adjacent pattern (load_calibration/build_calibration) this mirrors."""
import yaml
import pytest

from src.config.loader import build_pipette_calibration, load_pipette_calibration

_CFG = {
    "pipette": "p300",
    "tip": "p300_tip",
    "side": "left",
    "density_mg_per_ul": 0.998,
    # High microsteps -> low volume down to low microsteps -> high volume,
    # matching the real hardware convention (see PlungerModel.
    # volume_to_microsteps and the real calibration data in
    # configs/tools/pipettes/.../calibrations/*.yaml).
    "aspirate": [
        {"microsteps": 2000, "volume_ul": 0.0},
        {"microsteps": 1500, "volume_ul": 48.2},
        {"microsteps": 1000, "volume_ul": 100.0},
    ],
    "dispense": [
        {"microsteps": 2000, "volume_ul": 0.0},
        {"microsteps": 1500, "volume_ul": 51.0},
        {"microsteps": 1000, "volume_ul": 100.0},
    ],
}


def test_build_pipette_calibration_from_dict():
    cal = build_pipette_calibration(_CFG)
    assert cal.microsteps_for_volume(0.0, aspirating=True) == 2000
    assert cal.microsteps_for_volume(100.0, aspirating=True) == 1000
    # aspirate and dispense genuinely differ at the same interior point
    assert (cal.microsteps_for_volume(48.2, aspirating=True)
           != cal.microsteps_for_volume(48.2, aspirating=False))


def test_load_pipette_calibration_from_file(tmp_path):
    path = tmp_path / "cal.yaml"
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"pipette_calibration": _CFG}, fh)

    cal = load_pipette_calibration(str(path))
    assert cal.volume_for_microsteps(1500, aspirating=True) == pytest.approx(48.2)
    assert cal.volume_for_microsteps(1500, aspirating=False) == pytest.approx(51.0)


def test_load_pipette_calibration_standalone_file_without_wrapper_key(tmp_path):
    """Same convention as load_calibration: a standalone file with no
    pipette_calibration: wrapper is read as the section itself."""
    path = tmp_path / "cal.yaml"
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(_CFG, fh)

    cal = load_pipette_calibration(str(path))
    assert cal.microsteps_for_volume(100.0, aspirating=True) == 1000
