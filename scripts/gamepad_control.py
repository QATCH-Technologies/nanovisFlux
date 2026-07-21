"""Full-featured gamepad teleop, structured like a reference gamepad_teleop.py
this was adapted from (event-driven pygame handling, adjustable speed
ceiling, reissue-threshold to avoid flooding the link, volume bookkeeping
via position deltas) -- wired to this project's actual Robot/JogController/
Pipette APIs, which don't match that reference's (robot.motion.*, a
core.robot.Robot, a src.utils logger) since it's from a different codebase.
Run with no arguments (needs pygame and a gamepad attached).

    Left stick      X/Y jog, continuous -- speed proportional to deflection
    Right stick     Z jog (up/down only), continuous -- down = Z+, up = Z-
    LT              aspirate -- continuous plunger jog, speed = trigger travel
    RT              dispense -- continuous plunger jog, speed = trigger travel
    D-pad up/down   speed ceiling +/- speed_increment
    D-pad left/right  speed_increment itself +/- 1000 steps/s
    Y               toggle mount (left/right)
    A               quick stop
    X               print current position
    LB              pick up tip (press cycle, in place)
    RB              eject tip
    Back/View       home
    Start/Menu      emergency stop, then disconnect
    B               intentionally unbound

All stick/trigger axes are continuous: return to center (or trigger
release) cuts the move short with a quick stop (M410). Stick/trigger
handling is event-driven (JOYAXISMOTION), reissuing a jog only when
direction changes or speed changes by more than reissue_threshold_fraction
-- not every poll tick -- to avoid flooding the serial link on stick noise.

Axis indices below (AXIS_*) match the layout the reference's own comments
describe as confirmed on their hardware: both sticks fully (LX, LY, RX, RY)
before the two triggers (LT, RT) -- NOT the more common SDL_GameController
order (LX, LY, LT, RX, RY, RT). This has not been independently verified on
this project's hardware; run with --debug-axes and watch the printed
"axis <n> = <value>" lines while working each control to confirm/correct
the indices below if inputs don't line up.

Deliberate deviation from the reference: it maps right-stick-down to
direction -1 for the active mount axis. This script instead maps down to
Z+ (up to Z-), per this project's own convention -- DeckCalibration's
"home is up, so descending increases microsteps" -- and per an explicit
earlier instruction for this exact control. See _handle_axis_event.

Other assumptions worth checking against your hardware:
- aspirate/dispense direction: PlungerModel.volume_to_microsteps increases
  with volume, so aspirate (drawing in) is taken as the plunger's "+"
  direction and dispense as "-". Flip PLUNGER_ASPIRATE_SIGN below if your
  wiring is the other way.
- pick up tip / eject tip act in place (at the current jogged position, in
  raw microsteps) rather than through Pipette.pick_up_tip/drop_tip, which
  need a deck-calibrated target and a specific TipGeometry this low-level
  control script has no way to know. current_tip is cleared on eject (the
  one piece of state we can update unambiguously) but never set on pickup.

Talks to real hardware if --port is given; --config loads a full robot
setup (calibration/deck/tools) instead of a bare connection. Neither is
required for the jog/print/estop actions to work; aspirate/dispense volume
bookkeeping only has a tool to update if one is attached (via --config).
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

# Both sticks fully (X, Y) before the triggers -- see the module docstring.
AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
AXIS_RIGHT_STICK_X = 2   # intentionally unhandled -- left/right on the right stick does nothing
AXIS_RIGHT_STICK_Y = 3
AXIS_LEFT_TRIGGER = 4
AXIS_RIGHT_TRIGGER = 5

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

MAX_JOG_FEED = 100_000    # steps/s ceiling the D-pad can push the speed ceiling to
MIN_JOG_FEED = 500        # steps/s floor the D-pad can pull the speed ceiling down to
MIN_SPEED_INCREMENT = 1_000


def normalized_magnitude(raw_value: float, deadzone: float) -> float:
    """Maps a raw stick axis value to [0, 1], zero inside the deadzone."""
    if abs(raw_value) < deadzone:
        return 0.0
    return max(0.0, min(1.0, (abs(raw_value) - deadzone) / (1.0 - deadzone)))


def magnitude_to_speed(normalized: float, min_speed: float, max_speed: float) -> float:
    """Maps a normalized [0, 1] magnitude to a speed fraction between a floor and a ceiling."""
    return min_speed + normalized * (max_speed - min_speed)


def trigger_pressed_fraction(raw_value: float) -> float:
    """SDL2 commonly reports triggers as -1.0 (released) .. 1.0 (fully pressed)."""
    return max(0.0, min(1.0, (raw_value + 1.0) / 2.0))


def should_reissue(prev_direction: float, prev_speed: float, new_direction: float,
                   new_speed: float, threshold: float) -> bool:
    """Whether a continuous jog command should be re-sent: direction changed, or
    speed changed by at least threshold (avoids flooding the link on stick jitter)."""
    return prev_direction != new_direction or abs(new_speed - prev_speed) >= threshold


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
    ctrl.set_relative()   # restore the ambient jog mode for the caller's session
    pipette = robot.mounts[side].tool
    if pipette is not None and hasattr(pipette, "current_tip"):
        pipette.current_tip = None
        pipette.current_volume_ul = 0.0
    print("  eject done")


class GamepadTeleop:
    def __init__(self, robot, side: MountSide = MountSide.LEFT, poll_hz: float = 50.0,
                debug_axes: bool = False):
        import pygame
        self._pygame = pygame

        self.robot = robot
        self.jc = JogController(robot, side=side)
        self.poll_dt = 1.0 / poll_hz
        self.debug_axes = debug_axes
        self.running = True

        self.jc.settings.jog_feed = 20_000     # current speed ceiling, steps/s
        self.speed_increment = 1_000           # D-pad up/down step; D-pad left/right adjusts this
        self.min_speed_fraction = 0.05         # floor fraction so a light touch still moves
        self.reissue_threshold_fraction = 0.05

        self.deadzone = 0.2
        self.trigger_deadzone = 0.12           # triggers commonly report a nonzero resting baseline

        self.axis_states: dict = {}            # AxisId -> (direction, speed_fraction)
        self._left_trigger_speed = 0.0
        self._right_trigger_speed = 0.0
        self.fluidics_state: tuple = (0, 0.0)
        self.active_pipette_jog = None         # (tool, axis, start_position) while a trigger is held
        self._prev_hat = (0, 0)

        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise RuntimeError("no gamepad detected")
        self.pad = pygame.joystick.Joystick(0)
        self.pad.init()

        self._print_legend()

    def _print_legend(self) -> None:
        print("=" * 60)
        print(f" GAMEPAD TELEOP CONTROLS - {self.pad.get_name().upper()}")
        print(" [X/Y Gantry]    Left stick (proportional speed)")
        print(" [Active Z]      Right stick, up/down (proportional speed, down = Z+)")
        print(" [Fluidic]       LT (aspirate), RT (dispense) -- proportional")
        print(" [Mount Switch]  Y")
        print(" [Tip]           LB (pick up), RB (eject)")
        print("-" * 60)
        print(" [Speed]         D-pad up/down (+/- speed_increment)")
        print(" [Step size]     D-pad left/right (+/- speed_increment itself)")
        print(" [Actions]       X (print position), Back/View (home)")
        print(" [Stops]         A (quick stop), Start/Menu (emergency stop + disconnect)")
        print(" [Unused]        B")
        print(f" mount: {self.jc.side.value} | speed ceiling: {self.jc.settings.jog_feed} steps/s | "
             f"step: {self.speed_increment}")
        print("=" * 60 + "\n")

    def _vertical_axis(self) -> AxisId:
        return AxisId.Z if self.jc.side is MountSide.LEFT else AxisId.A

    def _plunger_axis(self) -> AxisId:
        return AxisId.B if self.jc.side is MountSide.LEFT else AxisId.C

    def _current_pipette(self):
        return self.robot.mounts[self.jc.side].tool

    # -- stopping ------------------------------------------------------
    def _stop_all_motion(self) -> None:
        self.jc.end_jog()
        self._sync_pipette_jog_volume()
        self.axis_states = {}
        self._left_trigger_speed = 0.0
        self._right_trigger_speed = 0.0
        self.fluidics_state = (0, 0.0)

    def _stop_fluidics_jog(self) -> None:
        if self.fluidics_state[0] != 0:
            self.jc.end_jog(self._plunger_axis())
            self._sync_pipette_jog_volume()
        self.fluidics_state = (0, 0.0)

    # -- stick/trigger continuous jog -----------------------------------
    def _handle_axis_motion(self, axis: AxisId, raw_value: float,
                            positive_dir: int, negative_dir: int) -> None:
        """Translates one analog stick axis into a proportional continuous jog."""
        normalized = normalized_magnitude(raw_value, self.deadzone)
        if normalized == 0.0:
            prev_direction, _ = self.axis_states.get(axis, (0, 0.0))
            if prev_direction != 0:
                self.jc.end_jog(axis)
            self.axis_states[axis] = (0, 0.0)
            return

        speed = magnitude_to_speed(normalized, self.min_speed_fraction, 1.0)
        direction = positive_dir if raw_value > 0 else negative_dir
        prev_direction, prev_speed = self.axis_states.get(axis, (0, 0.0))
        if should_reissue(prev_direction, prev_speed, direction, speed, self.reissue_threshold_fraction):
            self.jc.begin_jog(axis, direction, speed)
            self.axis_states[axis] = (direction, speed)

    def _handle_trigger_motion(self, is_left: bool, raw_value: float) -> None:
        fraction = trigger_pressed_fraction(raw_value)
        if fraction < self.trigger_deadzone:
            speed = 0.0
        else:
            normalized = (fraction - self.trigger_deadzone) / (1.0 - self.trigger_deadzone)
            speed = magnitude_to_speed(normalized, self.min_speed_fraction, 1.0)

        if is_left:
            self._left_trigger_speed = speed
        else:
            self._right_trigger_speed = speed
        self._update_fluidics_jog()

    def _update_fluidics_jog(self) -> None:
        lt, rt = self._left_trigger_speed, self._right_trigger_speed
        if (lt > 0) == (rt > 0):
            # both pressed (ambiguous) or neither -- refuse to act rather than guess
            self._stop_fluidics_jog()
            return

        direction, speed = (PLUNGER_ASPIRATE_SIGN, lt) if lt > 0 else (-PLUNGER_ASPIRATE_SIGN, rt)
        axis = self._plunger_axis()
        prev_direction, prev_speed = self.fluidics_state
        if should_reissue(prev_direction, prev_speed, direction, speed, self.reissue_threshold_fraction):
            if prev_direction == 0:
                start_position = self.robot.controller.report_position().get(axis)
                self.active_pipette_jog = (self._current_pipette(), axis, start_position)
            self.jc.begin_jog(axis, direction, speed)
            self.fluidics_state = (direction, speed)

    def _sync_pipette_jog_volume(self) -> None:
        """Reconciles Pipette.current_volume_ul after a continuous trigger
        hold stops, from how far the plunger actually moved -- the raw jog
        itself never touches current_volume_ul."""
        if self.active_pipette_jog is None:
            return
        tool, axis, start_position = self.active_pipette_jog
        self.active_pipette_jog = None

        plunger = getattr(tool, "plunger", None) if tool is not None else None
        if plunger is None or start_position is None or not plunger.microsteps_per_ul:
            return
        end_position = self.robot.controller.report_position().get(axis)
        if end_position is None:
            return
        delta_volume = (end_position - start_position) / plunger.microsteps_per_ul
        tool.current_volume_ul = max(0.0, min(tool.max_volume_ul, tool.current_volume_ul + delta_volume))

    # -- tip actions -----------------------------------------------------
    def _pick_up_tip(self) -> None:
        self._stop_all_motion()
        pickup_tip_in_place(self.robot, self.jc.side)

    def _eject_tip(self) -> None:
        self._stop_all_motion()
        eject_tip_in_place(self.robot, self.jc.side)

    # -- event dispatch ----------------------------------------------
    def _handle_button(self, button: int) -> None:
        if button == 7:      # Start/Menu
            self._stop_all_motion()
            self.robot.emergency_stop()
            self.running = False
            print("EMERGENCY STOP -- disconnecting")
        elif button == 0:    # A
            self._stop_all_motion()
            print("quick stop")
        elif button == 2:    # X
            print("position:", fmt_pos(self.robot.controller.report_position()))
        elif button == 3:    # Y
            self._stop_all_motion()   # the axes we drive are about to change
            self.jc.toggle_mount()
            print(f"mount -> {self.jc.side.value}")
        elif button == 4:    # LB
            self._pick_up_tip()
        elif button == 5:    # RB
            self._eject_tip()
        elif button == 6:    # Back/View
            self._stop_all_motion()
            self.robot.home()
            self.robot.controller.set_relative()   # home() leaves G90; restore ambient G91
            print("homed")
        # button 1 (B) intentionally unbound

    def _handle_hat(self, value: tuple) -> None:
        x, y = value
        if y == 1:
            self.jc.settings.jog_feed = min(MAX_JOG_FEED, self.jc.settings.jog_feed + self.speed_increment)
            print(f"speed ceiling -> {self.jc.settings.jog_feed} steps/s")
        elif y == -1:
            self.jc.settings.jog_feed = max(MIN_JOG_FEED, self.jc.settings.jog_feed - self.speed_increment)
            print(f"speed ceiling -> {self.jc.settings.jog_feed} steps/s")
        if x == 1:
            self.speed_increment += 1_000
            print(f"step size -> {self.speed_increment}")
        elif x == -1:
            self.speed_increment = max(MIN_SPEED_INCREMENT, self.speed_increment - 1_000)
            print(f"step size -> {self.speed_increment}")

    def _handle_axis_event(self, axis_index: int, value: float) -> None:
        if self.debug_axes:
            print(f"axis {axis_index} = {value:.3f}")

        if axis_index == AXIS_LEFT_STICK_X:
            self._handle_axis_motion(AxisId.X, value, positive_dir=-1, negative_dir=+1)
        elif axis_index == AXIS_LEFT_STICK_Y:
            self._handle_axis_motion(AxisId.Y, value, positive_dir=+1, negative_dir=-1)
        elif axis_index == AXIS_RIGHT_STICK_Y:
            # down = Z+ (this project's own "descending increases microsteps"
            # convention) -- deliberately not mirroring the reference here,
            # see the module docstring.
            self._handle_axis_motion(self._vertical_axis(), value, positive_dir=+1, negative_dir=-1)
        elif axis_index == AXIS_LEFT_TRIGGER:
            self._handle_trigger_motion(is_left=True, raw_value=value)
        elif axis_index == AXIS_RIGHT_TRIGGER:
            self._handle_trigger_motion(is_left=False, raw_value=value)
        # AXIS_RIGHT_STICK_X intentionally unhandled

    def _process_events(self) -> None:
        pygame = self._pygame
        for event in pygame.event.get():
            try:
                if event.type == pygame.JOYBUTTONDOWN:
                    self._handle_button(event.button)
                elif event.type == pygame.JOYHATMOTION:
                    self._handle_hat(event.value)
                elif event.type == pygame.JOYAXISMOTION:
                    self._handle_axis_event(event.axis, event.value)
            except Exception as exc:
                print(f"teleop error: {exc!r}")

    def start(self) -> None:
        pygame = self._pygame
        with self.robot:
            print(f"connected; controlling the {self.jc.side.value} mount")
            print("press home (Back/View) before jogging -- the firmware refuses motion on unhomed axes")
            with self.jc:   # relative mode for the whole session; restores G90 on exit
                try:
                    while self.running:
                        self._process_events()
                        time.sleep(self.poll_dt)
                except KeyboardInterrupt:
                    self._stop_all_motion()
                    print("\nstopped by user")
        pygame.quit()
        print("disconnected.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="serial port for real hardware (e.g. COM6); omit to use the fake transport")
    parser.add_argument("--config", help="robot config YAML to load (tools/calibration/deck); "
                                        "omit for a bare connection -- not required for jogging")
    parser.add_argument("--side", choices=("left", "right"), default="left",
                        help="mount to start on; Y toggles it during the session")
    parser.add_argument("--poll-hz", type=float, default=50.0)
    parser.add_argument("--debug-axes", action="store_true",
                        help="print every raw axis value -- use this to find your controller's "
                             "real axis indices if inputs don't match AXIS_* above")
    args = parser.parse_args()

    if args.config:
        robot = load_robot(args.config)
    else:
        transport = SerialTransport(args.port) if args.port else FakeTransport()
        robot = Robot(transport)

    teleop = GamepadTeleop(robot, side=_SIDES[args.side], poll_hz=args.poll_hz,
                          debug_axes=args.debug_axes)
    teleop.start()


if __name__ == "__main__":
    main()
