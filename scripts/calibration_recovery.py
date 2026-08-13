import yaml


def main():
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
    data = {
        "pipette_calibration": {
            "pipette": "opentrons_single_channel_gen1_p300",
            "tip": "Opentrons OT-2 300ul no Filter",
            "side": "left",
            "density_mg_per_ul": 0.998,
            "aspirate": [{"microsteps": m, "volume_ul": v} for m, v in aspirate_pairs],
            "dispense": [{"microsteps": m, "volume_ul": v} for m, v in aspirate_pairs],
        }
    }

    out_path = "pipette_calibration_left_Opentrons OT-2 300ul no Filter.yaml"

    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)

    print(f"Successfully recovered Phase A! Saved to: {out_path}")
    print("You can now run your main script with: --phase dispense --aspirate-from " + out_path)


if __name__ == "__main__":
    main()
