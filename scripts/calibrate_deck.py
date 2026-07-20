"""Interactive XY deck-calibration wizard. Run with no arguments.

Connects to the robot, homes it, then visits three corners of the gantry's
travel envelope in turn: drives there (X/Y only -- Z is never commanded on
the way in), hands control to the operator to center the tip on the
physical calibration point with a simple text jog REPL, then retracts Z
before driving to the next corner. Once all three are confirmed, it fits the
deck<->motor affine transform from the captured pairs and writes a
calibration file in the same format read by config.loader.build_calibration
(see calibration: in robot.example.yaml) -- paste it into a robot config.

This only calibrates XY. Z calibration (tip-agnostic, per mount) is a
separate step -- see DeckCalibration.probe_z_zero / touch_off_z_zero.

Talks to real hardware if --port is given; otherwise runs against the
in-memory FakeTransport so the flow can be exercised without hardware.
"""
from __future__ import annotations
import argparse

from src.core import AxisId, MountSide
from src.transport import FakeTransport, SerialTransport
from src.robot import Robot
from src.geometry import DeckPoint, AffineTransform2D
from src.control import JogController

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT}

#: (name, deck x mm, deck y mm) -- an L across the deck, matching the
#: three-point convention build_calibration expects. Edit to your deck's
#: actual measured dimensions, or override with --points.
DEFAULT_POINTS = [
    ("front-left (origin)", 0.0, 0.0),
    ("front-right (X reference)", 100.0, 0.0),
    ("back-left (Y reference)", 0.0, 100.0),
]

#: Microsteps to retract the vertical axis to between points -- clear of
#: anything on the deck, regardless of what the operator jogged it to.
SAFE_UP_MICROSTEPS = 2000

_NUDGE_KEYS = {"w": (AxisId.Y, +1), "s": (AxisId.Y, -1),
               "d": (AxisId.X, +1), "a": (AxisId.X, -1)}


def parse_points(raw: list) -> list:
    points = []
    for i, pair in enumerate(raw):
        x, y = (float(v) for v in pair.split(","))
        points.append((f"point {i + 1}", x, y))
    return points


def nominal_motor_corners(robot) -> list:
    """The three corners of the gantry's own travel envelope -- (home, home),
    (X endstop, home), (home, Y endstop) -- used as the drive-there guess
    since there's no calibration yet to compute one from deck mm."""
    x_limit = robot.axes[AxisId.X].config.endstop_limit
    y_limit = robot.axes[AxisId.Y].config.endstop_limit
    return [(0, 0), (x_limit, 0), (0, y_limit)]


def jog_repl(jc: JogController, label: str) -> None:
    print(f"  centering on: {label}")
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


def write_calibration(path: str, deck_pts: list, motor_pts: list) -> None:
    import yaml  # lazy dependency, matches config.loader

    cfg = {
        "calibration": {
            "points": {
                "deck": [{"x": p.x, "y": p.y} for p in deck_pts],
                "motor": [list(m) for m in motor_pts],
            },
        }
    }
    with open(path, "w") as fh:
        fh.write("# Deck <-> motor XY calibration captured by scripts/calibrate_deck.py\n")
        fh.write("# XY only -- add z_scale/z_zero separately, see\n")
        fh.write("# DeckCalibration.probe_z_zero / touch_off_z_zero.\n")
        yaml.safe_dump(cfg, fh, default_flow_style=False, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="serial port for real hardware (e.g. COM6); omit to use the fake transport")
    parser.add_argument("--out", default="calibration.out.yaml",
                        help="where to write the resulting calibration file")
    parser.add_argument("--side", choices=("left", "right"), default="left",
                        help="mount to jog and retract (X/Y itself is shared by both)")
    parser.add_argument("--points", nargs=3, metavar="X,Y",
                        help="three deck reference points as 'x,y' mm; defaults to an "
                             "L across the deck (0,0) (100,0) (0,100)")
    args = parser.parse_args()

    points = parse_points(args.points) if args.points else DEFAULT_POINTS
    side = _SIDES[args.side]
    vertical = AxisId.Z if side is MountSide.LEFT else AxisId.A

    transport = SerialTransport(args.port) if args.port else FakeTransport()
    robot = Robot(transport)
    with robot:
        robot.home()
        jc = JogController(robot, side=side)
        corners = nominal_motor_corners(robot)
        deck_pts, motor_pts = [], []
        for (name, x, y), (gx, gy) in zip(points, corners):
            point = DeckPoint(x, y)
            print(f"\n--- {name}: deck ({x}, {y}) ---")
            # Drive there in X/Y only -- Z is never commanded on the way in.
            robot.controller.rapid_move({AxisId.X: gx, AxisId.Y: gy})
            print(f"  drove to corner (motor {gx}, {gy})")

            with jc:   # relative for the jog itself; restores G90 on exit
                jog_repl(jc, name)
            pos = robot.controller.report_position()
            mx, my = pos[AxisId.X], pos[AxisId.Y]
            print(f"  confirmed: deck ({x}, {y}) -> motor ({mx}, {my})")
            deck_pts.append(point)
            motor_pts.append((mx, my))

            robot.controller.linear_move({vertical: SAFE_UP_MICROSTEPS})
            print("  retracted Z")

    new_xy = AffineTransform2D.from_point_pairs(
        [(p.x, p.y) for p in deck_pts], motor_pts)
    print("\nfitted affine:", new_xy)

    write_calibration(args.out, deck_pts, motor_pts)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
