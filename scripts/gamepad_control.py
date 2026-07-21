"""Full-featured gamepad teleop. Run with no arguments (needs pygame and a
gamepad attached).

    Left stick     X/Y jog, continuous -- speed = how far off center
    Right stick    Z jog, continuous -- down = Z+, up = Z- (no inversion
                   needed, that's the stick's own resting convention)
    LT             aspirate -- continuous plunger jog, speed = trigger travel
    RT             dispense -- continuous plunger jog, speed = trigger travel
    D-pad up/down  jog speed step_up/step_down (one step per press)
    Y              toggle mount (left/right)
    A              quick stop
    X              print current position
    LB             pick up tip (press cycle, in place)
    RB             eject tip
    Back/View      home
    Start/Menu     emergency stop, then disconnect

All stick/trigger axes are continuous: return to center (or trigger
release) cuts the move short with a quick stop (M410), same as the
keyboard/gamepad jog backends in control.jog -- this script just adds the
extra actions (aspirate/dispense/pickup/eject/print/disconnect) those don't
have.

Button/axis indices below match the common SDL2/XInput layout (Windows).
If your OS/driver numbers a control differently, this is a reference
implementation -- edit MAP.

Assumptions worth checking against your hardware before relying on this:
- aspirate/dispense direction: PlungerModel.volume_to_microsteps increases
  with volume, so aspirate (drawing in) is taken as the plunger's "+"
  direction and dispense as "-". Flip PLUNGER_ASPIRATE_SIGN below if your
  wiring is the other way.
- pick up tip / eject tip act in place (at the current jogged position,
  in raw microsteps) rather than through Pipette.pick_up_tip/drop_tip,
  which need a deck-calibrated target and a specific TipGeometry that this
  low-level control script has no way to know. Tip-length bookkeeping
  (current_tip) is therefore NOT updated by this script.

Talks to real hardware if --port is given; --config loads a full robot
setup (calibration/deck/tools) instead of a bare connection. Neither is
required for the jog/print/estop actions to work.
"""
from __future__ import annotations
import argparse
import time

from src.core import AxisId, MountSide
from src.transport import FakeTransport, SerialTransport
from src.robot import Robot
from src.config.loader import load_robot
from src.control import JogController

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT}

#: aspirate = "+" (increasing plunger microsteps, per PlungerModel);
#: dispense is always the opposite sign of this.
PLUNGER_ASPIRATE_SIGN = +1

#: In-place tip pickup press cycle, in raw microsteps (mirrors
#: tools.tips.TipPickup's mm defaults -- engage_mm=3, retract_mm=2,
#: presses=2 -- just not deck-calibrated).
PICKUP_ENGAGE_MICROSTEPS = 300
PICKUP_RETRACT_MICROSTEPS = 200
PICKUP_PRESSES = 2
PICKUP_FEED = 2000

MAP = {
    "left_stick": (0, 1),     # axis indices: X, Y
    "right_stick": (2, 3),    # axis indices: X (unused), Z
    "left_trigger": 4,        # axis index -- aspirate
    "right_trigger": 5,       # axis index -- dispense
    "trigger_rest_is_neg1": True,   # normalize -1..1 -> 0..1; set False if yours is already 0..1
    "buttons": {0: "quick_stop", 2: "print_position", 3: "mount_toggle",
                4: "pickup_tip", 5: "eject_tip", 6: "home", 7: "estop"},
    "deadzone": 0.2,
}


def normalize_trigger(raw: float) -> float:
    v = (raw + 1.0) / 2.0 if MAP["trigger_rest_is_neg1"] else raw
    return max(0.0, min(1.0, v))


def fmt_pos(pos: dict) -> dict:
    return {a.letter: v for a, v in pos.items()}


def pickup_tip_in_place(robot, side: MountSide) -> None:
    """Press/retract cycle on the vertical axis at the current XY -- the
    same fixed-depth-per-stroke mechanic as Pipette.pick_up_tip (every
    engage targets the same depth, every between-stroke retract targets the
    same partial-lift height -- not progressively deeper each time), just
    in raw microsteps relative to wherever the operator jogged to, since
    there's no deck calibration here. See the module docstring for why this
    doesn't go through Pipette.pick_up_tip itself."""
    vertical = AxisId.Z if side is MountSide.LEFT else AxisId.A
    ctrl = robot.controller
    ctrl.set_relative()
    depth = 0   # current position, in microsteps below the starting point
    for stroke in range(PICKUP_PRESSES):
        ctrl.linear_move({vertical: PICKUP_ENGAGE_MICROSTEPS - depth}, feed=PICKUP_FEED)
        depth = PICKUP_ENGAGE_MICROSTEPS
        if stroke < PICKUP_PRESSES - 1:
            ctrl.linear_move({vertical: -PICKUP_RETRACT_MICROSTEPS - depth}, feed=PICKUP_FEED)
            depth = -PICKUP_RETRACT_MICROSTEPS
    ctrl.linear_move({vertical: -depth}, feed=PICKUP_FEED)   # back to the starting depth
    print("  pickup cycle done (current_tip bookkeeping not tracked by this script)")


def eject_tip_in_place(robot, side: MountSide) -> None:
    """Drive the plunger to its ejection extreme and back -- the same
    mechanic Pipette.drop_tip uses, minus the xy travel (already jogged
    here) and the TipGeometry-specific bookkeeping."""
    plunger = AxisId.B if side is MountSide.LEFT else AxisId.C
    limit = robot.axes[plunger].config.endstop_limit
    ctrl = robot.controller
    ctrl.set_absolute()
    ctrl.linear_move({plunger: limit})
    ctrl.linear_move({plunger: 0})
    ctrl.set_relative()   # restore the ambient jog mode for the main loop
    pipette = robot.mounts[side].tool
    if pipette is not None and hasattr(pipette, "current_tip"):
        pipette.current_tip = None
        pipette.current_volume_ul = 0.0
    print("  eject done")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="serial port for real hardware (e.g. COM6); omit to use the fake transport")
    parser.add_argument("--config", help="robot config YAML to load (tools/calibration/deck); "
                                        "omit for a bare connection -- not required for jogging")
    parser.add_argument("--side", choices=("left", "right"), default="left",
                        help="mount to start on; Y toggles it during the session")
    parser.add_argument("--poll-hz", type=float, default=30.0)
    args = parser.parse_args()

    import pygame  # lazy import, optional dependency

    if args.config:
        robot = load_robot(args.config)
    else:
        transport = SerialTransport(args.port) if args.port else FakeTransport()
        robot = Robot(transport)

    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        raise RuntimeError("no gamepad detected")
    pad = pygame.joystick.Joystick(0)
    pad.init()
    dead = MAP["deadzone"]

    jc = JogController(robot, side=_SIDES[args.side])
    running = True
    prev_hat = (0, 0)

    with robot:
        print(f"connected; controlling the {jc.side.value} mount")
        print("press home (Back/View) before jogging -- the firmware refuses motion on unhomed axes")

        with jc:   # relative mode for the whole session; restores G90 on exit
            try:
                while running:
                    pygame.event.pump()
                    for event in pygame.event.get():
                        if event.type != pygame.JOYBUTTONDOWN:
                            continue
                        action = MAP["buttons"].get(event.button)
                        if action is None:
                            continue
                        try:
                            if action == "quick_stop":
                                jc.end_jog()
                                print("quick stop")
                            elif action == "print_position":
                                print("position:", fmt_pos(robot.controller.report_position()))
                            elif action == "mount_toggle":
                                jc.end_jog()   # stop everything -- the axes we drive are about to change
                                jc.toggle_mount()
                                print(f"mount -> {jc.side.value}")
                            elif action == "pickup_tip":
                                jc.end_jog()
                                pickup_tip_in_place(robot, jc.side)
                            elif action == "eject_tip":
                                jc.end_jog()
                                eject_tip_in_place(robot, jc.side)
                            elif action == "home":
                                jc.end_jog()
                                robot.home()
                                robot.controller.set_relative()   # home() leaves G90; restore ambient G91
                                print("homed")
                            elif action == "estop":
                                jc.end_jog()
                                robot.emergency_stop()
                                print("EMERGENCY STOP -- disconnecting")
                                running = False
                        except Exception as exc:
                            print(f"  {action} FAILED: {exc!r}")

                    if not running:
                        break

                    lx, ly = pad.get_axis(MAP["left_stick"][0]), pad.get_axis(MAP["left_stick"][1])
                    jc.begin_jog(AxisId.X, +1 if lx > 0 else -1, abs(lx)) if abs(lx) > dead else jc.end_jog(AxisId.X)
                    jc.begin_jog(AxisId.Y, -1 if ly > 0 else +1, abs(ly)) if abs(ly) > dead else jc.end_jog(AxisId.Y)

                    vertical = AxisId.Z if jc.side is MountSide.LEFT else AxisId.A
                    rz = pad.get_axis(MAP["right_stick"][1])
                    jc.begin_jog(vertical, +1 if rz > 0 else -1, abs(rz)) if abs(rz) > dead else jc.end_jog(vertical)

                    plunger = AxisId.B if jc.side is MountSide.LEFT else AxisId.C
                    lt = normalize_trigger(pad.get_axis(MAP["left_trigger"]))
                    rt = normalize_trigger(pad.get_axis(MAP["right_trigger"]))
                    if lt > dead:
                        jc.begin_jog(plunger, PLUNGER_ASPIRATE_SIGN, lt)
                    elif rt > dead:
                        jc.begin_jog(plunger, -PLUNGER_ASPIRATE_SIGN, rt)
                    else:
                        jc.end_jog(plunger)

                    if pad.get_numhats():
                        hat = pad.get_hat(0)
                        if hat[1] > 0 and prev_hat[1] <= 0:
                            print(f"jog speed -> {jc.cycle_scale(+1)}")
                        elif hat[1] < 0 and prev_hat[1] >= 0:
                            print(f"jog speed -> {jc.cycle_scale(-1)}")
                        prev_hat = hat

                    time.sleep(1.0 / args.poll_hz)
            except KeyboardInterrupt:
                print("\nstopped by user")

    pygame.quit()
    print("disconnected.")


if __name__ == "__main__":
    main()
