"""Interactive XY deck-calibration wizard. Run with no arguments.

Connects to the robot, homes it, then visits three of the four corners of
the gantry's travel envelope in turn (the fourth is HOME itself, and isn't
used as a calibration point): drives there in X/Y, Z stays at home (0) --
jog it down to the calibration mark yourself, along with fine X/Y, using
the same continuous-jog controller interface as live operation (hold to
move, release/center to stop; see control.JogSession). Press 'c'/confirm to
lock in the point and retract Z back to home before driving to the next
corner, or Esc/quit to abort the whole thing.

Once all three are confirmed, it fits the deck<->motor affine transform from
the captured pairs and writes a calibration file in the same format read by
config.loader.build_calibration (see calibration: in robot.example.yaml) --
paste it into a robot config.

This only calibrates XY. Z calibration (tip-agnostic, per mount) is a
separate step -- see DeckCalibration.probe_z_zero / touch_off_z_zero.

Talks to real hardware if --port is given; otherwise runs against the
in-memory FakeTransport so the flow can be exercised without hardware.
--input gamepad drives with a physical game controller instead of the
keyboard (needs pygame and a joystick attached).
"""
from __future__ import annotations
import argparse

from src.core import AxisId, MountSide
from src.transport import FakeTransport, SerialTransport
from src.robot import Robot
from src.geometry import DeckPoint, AffineTransform2D
from src.control import JogController, JogSession, KeyboardInput, GamepadInput

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT}

#: (name, deck x mm, deck y mm) for the three calibration corners, in the
#: same order nominal_motor_corners() drives to (Back-Left, Front-Left,
#: Front-Right). Front-Left is taken as the deck origin here -- edit to
#: your deck's actual measured dimensions/origin, or override with --points.
DEFAULT_POINTS = [
    ("back-left", 0.0, 100.0),
    ("front-left (origin)", 0.0, 0.0),
    ("front-right", 100.0, 0.0),
]

#: Home is the verified-safe, fully-retracted height for the vertical axis.
HOME_Z_MICROSTEPS = 0

#: Keyboard/gamepad maps for the wizard -- movement plus confirm/quit only;
#: no mount_toggle/zero_z/home, which don't make sense mid-calibration.
CAL_KEYMAP = {
    "a": "x-", "d": "x+", "w": "y+", "s": "y-", "q": "z+", "e": "z-",
    "+": "step_up", "-": "step_down", "c": "confirm", "\x1b": "quit",
}
CAL_PAD_MAP = {
    "buttons": {0: "confirm", 4: "step_down", 5: "step_up", 7: "quit"},
    "hat_to_z": True,
    "deadzone": 0.35,
}


def parse_points(raw: list) -> list:
    points = []
    for i, pair in enumerate(raw):
        x, y = (float(v) for v in pair.split(","))
        points.append((f"point {i + 1}", x, y))
    return points


def nominal_motor_corners(robot) -> list:
    """Three of the four corners of the gantry's own XY travel envelope --
    (X endstop, home), (X endstop, Y endstop), (home, Y endstop) -- used as
    the drive-there guess since there's no calibration yet to compute one
    from deck mm. The fourth corner, home itself, is skipped."""
    x_limit = robot.axes[AxisId.X].config.endstop_limit
    y_limit = robot.axes[AxisId.Y].config.endstop_limit
    return [(x_limit, 0), (x_limit, y_limit), (0, y_limit)]


def make_session(jc: JogController) -> tuple:
    """A JogSession for one calibration point, plus the outcome dict its
    confirm/quit bindings write to. Movement is the normal continuous jog
    (press/release); confirm and quit both stop it (end_jog) before ending
    this session's run() loop -- the caller tells them apart via ``state``."""
    session = JogSession(jc)
    state = {"confirmed": False, "aborted": False}

    def confirm():
        jc.end_jog()
        state["confirmed"] = True
        session.running = False

    def abort():
        jc.end_jog()
        state["aborted"] = True
        session.running = False

    session.bind("confirm", confirm)
    session.bind("quit", abort)
    return session, state


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
                        help="mount to jog/retract (X/Y itself is shared by both)")
    parser.add_argument("--input", choices=("keyboard", "gamepad"), default="keyboard",
                        help="continuous-jog input backend to drive with")
    parser.add_argument("--points", nargs=3, metavar="X,Y",
                        help="three deck reference points as 'x,y' mm, in back-left/"
                             "front-left/front-right order; defaults to a 100mm L "
                             "anchored at front-left")
    args = parser.parse_args()

    points = parse_points(args.points) if args.points else DEFAULT_POINTS
    side = _SIDES[args.side]
    vertical = AxisId.Z if side is MountSide.LEFT else AxisId.A

    input_source = (GamepadInput(mapping=CAL_PAD_MAP) if args.input == "gamepad"
                    else KeyboardInput(keymap=CAL_KEYMAP))

    transport = SerialTransport(args.port) if args.port else FakeTransport()
    robot = Robot(transport)
    with robot:
        robot.home()
        deck_limit = robot.axes[vertical].config.endstop_limit
        jc = JogController(robot, side=side)
        corners = nominal_motor_corners(robot)
        deck_pts, motor_pts = [], []
        for (name, x, y), (gx, gy) in zip(points, corners):
            point = DeckPoint(x, y)
            print(f"\n--- {name}: deck ({x}, {y}) ---")
            robot.controller.rapid_move({AxisId.X: gx, AxisId.Y: gy})
            print(f"  drove to corner (motor {gx}, {gy}); Z stays at home ({HOME_Z_MICROSTEPS})")
            print(f"  (for reference, deck level on this axis is roughly {deck_limit} microsteps)")
            print("  jog onto the calibration mark, then confirm ('c' / face button 0)")

            with jc:   # relative for the jog itself; restores G90 on exit
                session, state = make_session(jc)
                input_source.run(session)
            if state["aborted"]:
                raise SystemExit("calibration aborted")

            pos = robot.controller.report_position()
            mx, my = pos[AxisId.X], pos[AxisId.Y]
            print(f"  confirmed: deck ({x}, {y}) -> motor ({mx}, {my}, z={pos[vertical]})")
            deck_pts.append(point)
            motor_pts.append((mx, my))

            robot.controller.rapid_move({vertical: HOME_Z_MICROSTEPS})
            print("  retracted Z to home")

    new_xy = AffineTransform2D.from_point_pairs(
        [(p.x, p.y) for p in deck_pts], motor_pts)
    print("\nfitted affine:", new_xy)

    write_calibration(args.out, deck_pts, motor_pts)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
