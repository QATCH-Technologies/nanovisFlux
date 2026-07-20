"""Interactive XY deck-calibration wizard.

Visits three deck reference points in turn. For each one it rapid-moves to
the *approximate* motor position (X/Y only -- Z is never commanded, so
whatever height the gantry is already at is left alone), then hands control
to the operator to jog onto the exact point with a simple text REPL. Once
all three are confirmed, it fits the deck<->motor affine transform from the
captured pairs and writes a calibration file in the same format read by
``config.loader.build_calibration`` (see calibration: in robot.example.yaml)
-- paste it into a robot config, or point --config at it directly next time
to use it as the seed.

This only calibrates XY. Z calibration (tip-agnostic, per mount) is a
separate step -- see DeckCalibration.probe_z_zero / touch_off_z_zero -- and
any z_scale/z_zero already present in the seed config is carried through
unchanged.

Runs against the in-memory FakeTransport by default so the flow can be
exercised without hardware attached; pass --port to drive real hardware.
"""
from __future__ import annotations
import argparse

from src.core import AxisId, MountSide
from src.config.loader import load_robot
from src.geometry import DeckPoint, AffineTransform2D
from src.control import JogController

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT}

#: (name, deck x mm, deck y mm) -- an L across the deck, matching the
#: three-point convention build_calibration expects. Override with --points.
DEFAULT_POINTS = [
    ("front-left (origin)", 0.0, 0.0),
    ("front-right (X reference)", 100.0, 0.0),
    ("back-left (Y reference)", 0.0, 100.0),
]

_NUDGE_KEYS = {"w": (AxisId.Y, +1), "s": (AxisId.Y, -1),
               "d": (AxisId.X, +1), "a": (AxisId.X, -1)}


def parse_points(raw: list) -> list:
    points = []
    for i, pair in enumerate(raw):
        x, y = (float(v) for v in pair.split(","))
        points.append((f"point {i + 1}", x, y))
    return points


def jog_repl(jc: JogController, label: str) -> None:
    print(f"  jogging onto: {label}")
    print("  w/a/s/d = Y+/X-/Y-/X+   +/- = bigger/smaller step   c = confirm   q = abort")
    while True:
        cmd = input("  jog> ").strip().lower()
        if cmd in _NUDGE_KEYS:
            axis, sign = _NUDGE_KEYS[cmd]
            jc.nudge(axis, sign)
        elif cmd == "+":
            print(f"  step scale -> {jc.cycle_scale(+1)}")
        elif cmd == "-":
            print(f"  step scale -> {jc.cycle_scale(-1)}")
        elif cmd == "c":
            return
        elif cmd == "q":
            raise SystemExit("calibration aborted")
        else:
            print("  ? unrecognized -- use w/a/s/d, +/-, c, or q")


def write_calibration(path: str, deck_pts: list, motor_pts: list, seed) -> None:
    import yaml  # lazy dependency, matches config.loader

    cfg = {
        "calibration": {
            "points": {
                "deck": [{"x": p.x, "y": p.y} for p in deck_pts],
                "motor": [list(m) for m in motor_pts],
            },
        }
    }
    if seed is not None:
        cfg["calibration"]["z_scale"] = {"steps_per_mm": seed.z_scale.steps_per_mm}
        if seed.z_zero:
            cfg["calibration"]["z_zero"] = {
                side.value: int(v) for side, v in seed.z_zero.items()}

    with open(path, "w") as fh:
        fh.write("# Deck <-> motor XY calibration captured by scripts/calibrate_deck.py\n")
        fh.write("# z_scale/z_zero (if present) are carried over from the seed config --\n")
        fh.write("# calibrate Z separately, see DeckCalibration.probe_z_zero/touch_off_z_zero.\n")
        yaml.safe_dump(cfg, fh, default_flow_style=False, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True,
                        help="robot config YAML to load (transport, axes, deck, and an "
                             "optional seed calibration used to guess each approximate corner)")
    parser.add_argument("--out", default="calibration.out.yaml",
                        help="where to write the resulting calibration file")
    parser.add_argument("--side", choices=("left", "right"), default="left",
                        help="mount to jog with (X/Y only -- doesn't affect the result)")
    parser.add_argument("--points", nargs=3, metavar="X,Y",
                        help="three deck reference points as 'x,y' mm; defaults to an "
                             "L across the deck (0,0) (100,0) (0,100)")
    args = parser.parse_args()

    points = parse_points(args.points) if args.points else DEFAULT_POINTS

    robot = load_robot(args.config)
    seed = robot.calibration
    with robot:
        robot.home()
        jc = JogController(robot, side=_SIDES[args.side])
        deck_pts, motor_pts = [], []
        for name, x, y in points:
            point = DeckPoint(x, y)
            print(f"\n--- {name}: deck ({x}, {y}) ---")
            # Approach move must be absolute -- robot.home() leaves the
            # controller in G90, and jc's own session (entered just below)
            # restores G90 on exit, so this is always correct here.
            if seed is not None:
                mx, my = seed.xy.apply(x, y)
                robot.controller.rapid_move({AxisId.X: round(mx), AxisId.Y: round(my)})
                print(f"  moved to approximate motor position ({round(mx)}, {round(my)})")
            else:
                print("  no seed calibration in --config -- jog manually from here")

            with jc:   # relative for the jog itself; restores G90 on exit
                jog_repl(jc, name)
            pos = robot.controller.report_position()
            mx, my = pos[AxisId.X], pos[AxisId.Y]
            print(f"  confirmed: deck ({x}, {y}) -> motor ({mx}, {my})")
            deck_pts.append(point)
            motor_pts.append((mx, my))

    new_xy = AffineTransform2D.from_point_pairs(
        [(p.x, p.y) for p in deck_pts], motor_pts)
    print("\nfitted affine:", new_xy)

    write_calibration(args.out, deck_pts, motor_pts, seed)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
