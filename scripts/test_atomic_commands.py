"""Interactive atomic-command smoke test.

Connects to the robot and exercises every low-level protocol command one at
a time -- position reporting, homing, small per-axis rapid moves, a linear
move, absolute/relative mode, a probe attempt, the per-axis config setters,
quick stop, disable-limits, and (opt-in, since they're disruptive)
emergency stop and reset -- pausing for confirmation before each so you can
watch the hardware and see exactly what's working and what isn't.

A failed step is caught and reported rather than aborting the run, so one
broken command doesn't stop you from seeing the rest.

Talks to real hardware if --port is given; otherwise runs against the
in-memory FakeTransport so the flow can be exercised without hardware.
"""
from __future__ import annotations
import argparse

from src.core import AxisId
from src.transport import FakeTransport, SerialTransport
from src.robot import Robot
from src.protocol import commands as cmd

NUDGE_MICROSTEPS = 200   # small enough to be safe on any axis, incl. plungers


def step(name: str, fn, *, destructive: bool = False) -> None:
    print(f"\n=== {name} ===")
    if destructive:
        ans = input("  DESTRUCTIVE -- type 'y' to run, anything else skips (q quits) ").strip().lower()
    else:
        ans = input("  press Enter to run (s = skip, q = quit) ").strip().lower()
    if ans == "q":
        raise SystemExit("stopped by user")
    if destructive and ans != "y":
        print("  skipped")
        return
    if not destructive and ans == "s":
        print("  skipped")
        return
    try:
        result = fn()
        print("  OK" + ("" if result is None else f" -> {result!r}"))
    except Exception as exc:
        print(f"  FAILED: {exc!r}")


def fmt_pos(pos: dict) -> dict:
    return {a.letter: v for a, v in pos.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="serial port for real hardware (e.g. COM6); omit to use the fake transport")
    args = parser.parse_args()

    transport = SerialTransport(args.port) if args.port else FakeTransport()
    robot = Robot(transport)
    ctrl = robot.controller

    with robot:
        print("connected; boot banner:", ctrl.banner)

        step("report_position (M114, initial)", lambda: fmt_pos(ctrl.report_position()))
        step("home (G28, all axes)", ctrl.home)
        step("report_position (M114, after home)", lambda: fmt_pos(ctrl.report_position()))

        step("set_relative (G91)", ctrl.set_relative)
        for axis in AxisId:
            step(f"rapid_move (G0) {axis.letter}+{NUDGE_MICROSTEPS}",
                lambda a=axis: ctrl.rapid_move({a: NUDGE_MICROSTEPS}))
            step(f"rapid_move (G0) {axis.letter}-{NUDGE_MICROSTEPS}",
                lambda a=axis: ctrl.rapid_move({a: -NUDGE_MICROSTEPS}))
        step(f"linear_move (G1) X+Y+{NUDGE_MICROSTEPS}, feed 2000",
            lambda: ctrl.linear_move({AxisId.X: NUDGE_MICROSTEPS, AxisId.Y: NUDGE_MICROSTEPS}, feed=2000))
        step(f"linear_move (G1) X-Y-{NUDGE_MICROSTEPS}, feed 2000",
            lambda: ctrl.linear_move({AxisId.X: -NUDGE_MICROSTEPS, AxisId.Y: -NUDGE_MICROSTEPS}, feed=2000))
        step("set_absolute (G90)", ctrl.set_absolute)
        step("report_position (M114, after moves -- should match the initial reading)",
            lambda: fmt_pos(ctrl.report_position()))

        step("probe (G38.2) Z toward, 5000 microsteps, feed 100 -- needs a wired probe, "
             "a no-contact error here just means none is",
            lambda: ctrl.probe(AxisId.Z, 5000, feed=100))

        step("quick_stop (M410)", ctrl.quick_stop)

        for axis, ax in robot.axes.items():
            step(f"set_hard_limits (M201) {axis.letter} -- reapply configured {ax.config.endstop_limit}",
                lambda a=axis, v=ax.config.endstop_limit: ctrl.set_hard_limits({a: v}))

        step("SetAccelerations (M204) -- reapply configured values",
            lambda: ctrl.execute(cmd.SetAccelerations(
                {a: robot.axes[a].config.travel_accel for a in AxisId})))
        step("SetHomingSpeeds (M210) -- reapply configured values",
            lambda: ctrl.execute(cmd.SetHomingSpeeds(
                {a: robot.axes[a].config.homing_speed for a in AxisId})))
        step("SetTravelSpeeds (M220) -- reapply configured values",
            lambda: ctrl.execute(cmd.SetTravelSpeeds(
                {a: robot.axes[a].config.travel_speed for a in AxisId})))
        step("SetHomingRetract (M421) -- reapply configured values",
            lambda: ctrl.execute(cmd.SetHomingRetract(
                {a: robot.axes[a].config.endstop_bounce for a in AxisId})))

        step("DisableLimits (M911) -- relaxes limit clamping",
            lambda: ctrl.execute(cmd.DisableLimits()))

        step("emergency_stop (M112) -- halts the controller; likely needs a Reset afterward",
            ctrl.emergency_stop, destructive=True)
        step("Reset (M30) -- reboots the controller",
            lambda: ctrl.execute(cmd.Reset()), destructive=True)

    print("\ndone.")


if __name__ == "__main__":
    main()
