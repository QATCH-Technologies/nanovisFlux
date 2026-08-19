from pathlib import Path

import yaml

#: Anchored to this script's own location, matching calibrate_pipette.py's
#: _DEFAULT_CONFIG -- the standard configs/tools/pipettes/ layout that
#: config/loader.py's build_pipette_tip_calibrations auto-discovers
#: calibrations from (one file per tip, under <pipette name>/calibrations/).
_PIPETTES_DIR = Path(__file__).resolve().parent.parent / "configs" / "tools" / "pipettes"


def main():
    pipette_name = "opentrons_single_channel_gen1_p300"
    tip_name = "Opentrons OT-2 300ul no Filter"

    # The properly calculated (microstep, volume) pairs from your log
    aspirate_pairs = [
        (15000, 0.0),
        (14250, 6.01),
        (12125, 59.12),
        (10000, 112.22),
        (7875, 170.34),
        (5750, 215.43),
        (3625, 270.54),
        (1500, 307.62),
    ]

    # Structuring the data identically to write_yaml in calibrate_pipette.py
    # -- no side: here, a plunger's steps<->volume mapping doesn't depend
    # on which mount the pipette is on (see PlungerCalibration).
    data = {
        "pipette_calibration": {
            "pipette": pipette_name,
            "tip": tip_name,
            "density_mg_per_ul": 0.998,
            "aspirate": [{"microsteps": m, "volume_ul": v} for m, v in aspirate_pairs],
            "dispense": [{"microsteps": m, "volume_ul": v} for m, v in aspirate_pairs],
        }
    }

    out_dir = _PIPETTES_DIR / pipette_name / "calibrations"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{'_'.join(tip_name.split())}.yaml"

    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)

    print(f"Successfully recovered Phase A! Saved to: {out_path}")
    print(
        "This pipette's calibrations are auto-discovered on load (see "
        "config/loader.py's build_pipette_tip_calibrations) -- reconnecting normally "
        "already picks this up. To finish Phase B by hand instead, run: "
        f"--phase dispense --aspirate-from {out_path}"
    )


if __name__ == "__main__":
    main()
