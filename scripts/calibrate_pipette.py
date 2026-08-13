"""Two-phase empirical calibration of a pipette's plunger: builds a
PlungerCalibration (src/tools/pipette.py) for one (pipette, tip)
combination by aspirating known step amounts, dispensing onto a scale, and
recording the measured volume -- replacing PlungerModel's single linear
microsteps_per_ul factor with a piecewise-linear curve for each direction.

Aspirate and dispense are measured SEPARATELY (not a simple aspirate-then-
dispense-then-weigh round trip), because a round trip can't tell you which
direction's error you're looking at:

  Phase A (aspirate curve): the dispense side is always an identical, full
  purge back to the same "empty" reference (bottom_microsteps); only the
  ASPIRATE stroke length varies across trials. Since the dispense portion
  is the same repeatable action every time, its own error is constant
  across trials -- so the *differences* in measured volume between trials
  isolate the aspirate curve's shape.

  Phase B (dispense curve): the aspirate side is always the same fixed
  stroke (so aspirate error is held constant); the DISPENSE TARGET varies
  instead, via partial dispenses within one continuous run -- the same
  vessel returns to the same fixed spot between steps, and the operator
  reports the CUMULATIVE mass dispensed so far at each step (never re-tare
  mid-run). Phase B needs Phase A's fitted curve to know how much volume
  that fixed aspirate stroke actually represents (remaining = total -
  cumulative), so Phase A must run first (or be supplied via
  --aspirate-from a prior result) before Phase B can run.

GANTRY MOTION goes through the same deck-calibrated, well-addressed
routine machinery as the rest of the app (src.routines.WellLocation +
Robot.safe_move_to/raise_z/move_vertical_to) -- --aspirate-slot/
--dispense-slot name which deck slots hold the source and destination
labware (7 and 8 by default), and --aspirate-well/--dispense-well pick a
well on each (A1 by default). This needs the config's deck to actually be
calibrated (a real `calibration:` section) and to have labware loaded on
both slots -- see src/config/robot.example.yaml's `labware:` section for
the shape. Every move is safe by construction (Robot.safe_move_to always
raises to the mount's travel_z_mm clearance height before crossing, and
only descends once already over the target XY -- the same primitive the
GUI's manual "Go To" and every routine step already use, not a bespoke
raw-coordinate implementation with its own edge cases to re-discover).

The ONE thing that stays in raw motor microsteps is the plunger (B on the
left mount, C on the right) -- that conversion is literally what this
script is calibrating, so it is deliberately never routed through
Pipette.aspirate/dispense (which would use the PlungerModel/
PlungerCalibration being measured to decide the very microsteps this
script needs to control directly and precisely).

This codebase has no integrated scale, so mass is entered interactively
after each weighing. Pass --simulate to generate synthetic readings
instead (deliberately different, mildly nonlinear "true" curves for
aspirate vs. dispense) -- lets the whole two-phase flow, the YAML output,
and PlungerCalibration's interpolation be exercised end-to-end without a
human at the keyboard or any real hardware.

SAFETY: --plunger-max-microsteps is a hard ceiling on the plunger (B on
the left mount, C on the right) -- moving the plunger past this position
detaches the tip instead of dispensing. Every planned target (all Phase A
absolute aspirate positions, all Phase B targets) is checked against it
before any motion happens at all, and every individual raw plunger move
also re-checks it immediately before sending the command (see
move_plunger) as a second, independent guard.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from loguru import logger

from src.config.loader import load_config, load_robot
from src.core import AxisId, MountSide
from src.routines import WellLocation
from src.tools import PlungerCalibration, TipGeometry

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT}

#: Anchored to this script's own location (matching gui/connection_bar.py's
#: _DEFAULT_CONFIG), not the process's current working directory -- a bare
#: relative string here would resolve against wherever the script happened
#: to be invoked FROM, silently picking up a same-relative-path file in a
#: different checkout/worktree instead of failing loudly, if one exists.
_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "configs" / "robot.yaml"

#: Deliberately different, mildly nonlinear "true" curves for --simulate's
#: synthetic readings (some efficiency loss at larger strokes, matching
#: typical seal-friction behavior) -- different constants for aspirate vs.
#: dispense so a --simulate run visibly proves the two curves come out
#: independent, not just copies of each other.
_ASPIRATE_TRUTH = {"microsteps_per_ul": 50.0, "nonlinearity": 0.00006}
_DISPENSE_TRUTH = {"microsteps_per_ul": 48.0, "nonlinearity": 0.00004}


def _synthetic_volume_ul(microsteps_from_bottom: float, truth: dict) -> float:
    linear = microsteps_from_bottom / truth["microsteps_per_ul"]
    return max(0.0, linear * (1.0 - truth["nonlinearity"] * microsteps_from_bottom))


def _synthetic_mass_mg(stroke: float, density: float, *, aspirating: bool) -> float:
    truth = _ASPIRATE_TRUTH if aspirating else _DISPENSE_TRUTH
    return _synthetic_volume_ul(stroke, truth) * density


def _synthetic_cumulative_mass_mg(
    bottom: int, fixed_position: int, target: int, density: float
) -> float:
    total = _synthetic_volume_ul(fixed_position - bottom, _DISPENSE_TRUTH)
    remaining = _synthetic_volume_ul(target - bottom, _DISPENSE_TRUTH)
    return max(0.0, total - remaining) * density


def read_mass_mg(prompt: str, simulate_fn=None) -> float:
    """The single seam between this script and an operator/scale: prompts
    for a mass reading (mg) and keeps asking until it parses as a number.
    --simulate swaps this for a deterministic synthetic value instead."""
    if simulate_fn is not None:
        value = simulate_fn()
        logger.info(f"{prompt}{value:.2f}  (simulated)")
        return value
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            logger.warning("enter a number (mg)")


def move_plunger(
    robot, axis: AxisId, target: int, plunger_max: int, feed: int | None = None, *, verify: bool = True
) -> None:
    """The one place that ever commands the plunger axis -- re-checks
    `plunger_max` immediately before sending, as a second, independent
    guard alongside the upfront plan-wide check in main() (see SAFETY in
    the module docstring): going past it detaches the tip.

    verify: poll-confirm the plunger actually reached `target` before
    returning (see Robot._await_settled's own docstring for why "ok"
    alone isn't trusted) -- on by default here since a cut-short aspirate/
    dispense stroke would silently corrupt the whole calibration."""
    if target > plunger_max:
        raise RuntimeError(
            f"refusing to move the plunger to {target} microsteps -- exceeds the "
            f"--plunger-max-microsteps safety ceiling ({plunger_max}); this would detach the tip"
        )
    robot.controller.linear_move({axis: target}, feed=feed)
    if verify:
        robot._await_settled({axis: target})


def _labware_on_slot(robot, slot_name: str):
    """The Labware placed on deck slot `slot_name` -- lets --aspirate-slot/
    --dispense-slot name a slot the way the operator thinks about the deck,
    rather than needing to know that slot's labware's config `name:`."""
    for lw in robot.labware.values():
        if lw.slot is not None and lw.slot.name == slot_name:
            return lw
    raise SystemExit(
        f"no labware loaded on slot {slot_name!r} -- add a labware: entry with "
        f'slot: "{slot_name}" to the config (see src/config/robot.example.yaml)'
    )


def _log_at(robot, side: MountSide, label: str, loc: WellLocation) -> None:
    """Logs which labware/well and resolved deck-mm point a move targeted,
    the RAW MOTOR target that deck-mm point computes to, and the ACTUAL
    measured raw position (M114) after the move -- three separate numbers
    on purpose: deck-mm alone can't tell you whether a calibration/tip-
    length miscalculation put the raw target somewhere wrong, or whether
    the move itself didn't reach a correctly-computed target."""
    pt = loc.resolve(robot)
    cal = robot.calibration
    vertical = cal.vertical_axis(side)
    computed = cal.deck_to_motor(pt, side, robot.tip_offset(side))
    actual = robot.controller.report_position()
    logger.info(
        f"  at {label}: {loc.labware}:{loc.well} -> ({pt.x:.1f}, {pt.y:.1f}, {pt.z:.1f}) mm  |  "
        f"computed raw X={computed.get(AxisId.X)} Y={computed.get(AxisId.Y)} "
        f"{vertical.letter if vertical else '?'}={computed.get(vertical)}  |  "
        f"actual raw X={actual.get(AxisId.X)} Y={actual.get(AxisId.Y)} "
        f"{vertical.letter if vertical else '?'}={actual.get(vertical)}"
    )


def run_phase_a(
    robot,
    side: MountSide,
    plunger_axis: AxisId,
    plunger_max: int,
    bottom: int,
    strokes: list,
    aspirate_loc: WellLocation,
    dispense_loc: WellLocation,
    replicates: int,
    density: float,
    feed: int | None,
    dwell_s: float,
    *,
    simulate: bool,
) -> list:
    """See module docstring. Returns [(bottom + stroke, volume_ul), ...].

    dwell_s: how long to hold still, plunger already at its target, at the
    bottom of each aspirate/dispense stroke -- the stepper reaching its
    commanded position isn't the same as the liquid actually finishing
    moving (surface tension/viscosity lag behind the plunger), so raising
    away immediately can leave a stroke short of what it should have
    drawn or expelled."""
    pairs = []
    for stroke in strokes:
        measurements = []
        for rep in range(1, replicates + 1):
            logger.info(
                f"[Phase A] stroke {stroke} usteps (position {bottom + stroke}), "
                f"replicate {rep}/{replicates}"
            )
            move_plunger(robot, plunger_axis, bottom, plunger_max, feed)  # 1. empty
            robot.safe_move_to(aspirate_loc.resolve(robot), side, feed=feed, verify=True)  # 2. to source
            _log_at(robot, side, "source (aspirate)", aspirate_loc)
            move_plunger(robot, plunger_axis, bottom + stroke, plunger_max, feed)  # 3. aspirate
            time.sleep(dwell_s)  # hold at the bottom, submerged, so the aspirate actually draws up
            robot.safe_move_to(dispense_loc.resolve(robot), side, feed=feed, verify=True)  # 4. to scale
            _log_at(robot, side, "scale (dispense)", dispense_loc)
            move_plunger(robot, plunger_axis, bottom, plunger_max, feed)  # 5. full purge
            time.sleep(dwell_s)  # hold before lifting so the dispensed droplet fully releases
            robot.raise_z(side, verify=True)  # 6. lift clear (travel_z_mm)
            logger.info(
                "lifted clear -- remove the vessel, weigh it, and empty/replace it before continuing."
            )
            simulate_fn = (
                (lambda s=stroke: _synthetic_mass_mg(s, density, aspirating=True))
                if simulate
                else None
            )
            mass_mg = read_mass_mg("  mass dispensed (mg): ", simulate_fn)
            measurements.append(mass_mg / density)
        volume_ul = sum(measurements) / len(measurements)
        logger.info(f"-> {volume_ul:.2f} uL" + (f" (avg of {replicates})" if replicates > 1 else ""))
        pairs.append((bottom + stroke, volume_ul))
    return pairs


def run_phase_b(
    robot,
    side: MountSide,
    plunger_axis: AxisId,
    plunger_max: int,
    bottom: int,
    max_stroke: int,
    targets: list,
    aspirate_loc: WellLocation,
    dispense_loc: WellLocation,
    aspirate_calibration: PlungerCalibration,
    replicates: int,
    density: float,
    feed: int | None,
    dwell_s: float,
    *,
    simulate: bool,
) -> list:
    """See module docstring. Returns [(target, remaining_volume_ul), ...].
    dwell_s: see run_phase_a's own docstring."""
    fixed_position = bottom + max_stroke
    total_ul = aspirate_calibration.volume_for_microsteps(fixed_position, aspirating=True)
    logger.info(
        f"[Phase B] fixed aspirate stroke {max_stroke} usteps ~= {total_ul:.2f} uL "
        "(from the Phase A curve)"
    )

    accum = {t: [] for t in targets}
    for rep in range(1, replicates + 1):
        logger.info(f"[Phase B] replicate {rep}/{replicates}")
        move_plunger(robot, plunger_axis, bottom, plunger_max, feed)
        robot.safe_move_to(aspirate_loc.resolve(robot), side, feed=feed, verify=True)
        _log_at(robot, side, "source (aspirate)", aspirate_loc)
        move_plunger(robot, plunger_axis, fixed_position, plunger_max, feed)
        time.sleep(dwell_s)  # hold at the bottom, submerged, so the aspirate actually draws up
        dispense_point = dispense_loc.resolve(robot)
        robot.safe_move_to(dispense_point, side, feed=feed, verify=True)
        _log_at(robot, side, "scale (dispense)", dispense_loc)
        logger.info(
            "place/tare the vessel now -- it returns to this same spot between every step below."
        )
        for target in targets:
            move_plunger(robot, plunger_axis, target, plunger_max, feed)  # partial dispense
            time.sleep(dwell_s)  # hold before lifting so the dispensed droplet fully releases
            robot.raise_z(side, verify=True)  # lift clear (travel_z_mm)
            logger.info("lifted clear -- remove the vessel and weigh it (do NOT empty it or re-tare).")
            simulate_fn = (
                (lambda t=target: _synthetic_cumulative_mass_mg(bottom, fixed_position, t, density))
                if simulate
                else None
            )
            cumulative_mg = read_mass_mg(
                f"  CUMULATIVE mass dispensed so far (mg) [target {target}]: ", simulate_fn
            )
            remaining_ul = max(0.0, total_ul - cumulative_mg / density)
            accum[target].append(remaining_ul)
            robot.move_vertical_to(dispense_point.z, side, feed=feed, verify=True)  # back down for next step
            logger.info("place the vessel back in the same spot before the next step.")
    return [(t, sum(vals) / len(vals)) for t, vals in accum.items()]


def _load_points(path: str, key: str) -> list:
    cfg = load_config(path)
    section = cfg.get("pipette_calibration", cfg)
    return [(p["microsteps"], p["volume_ul"]) for p in section[key]]


def write_yaml(
    path: str,
    *,
    pipette_name: str,
    side: str,
    tip: str,
    density: float,
    aspirate: list,
    dispense: list,
) -> None:
    import yaml  # lazy dependency, matches config/loader.py's own convention

    data = {
        "pipette_calibration": {
            "pipette": pipette_name,
            "tip": tip,
            "side": side,
            "density_mg_per_ul": density,
            "aspirate": [{"microsteps": m, "volume_ul": v} for m, v in aspirate],
            "dispense": [{"microsteps": m, "volume_ul": v} for m, v in dispense],
        }
    }
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def _default_strokes(available: int, num_points: int) -> list:
    """Evenly spaced Phase A test strokes spanning most of the plunger's
    usable travel from the empty reference (0) up toward `available` --
    plunger_max minus bottom_microsteps, the room actually available
    before the tip-detach safety ceiling -- but stopping at 90% of it and
    starting at 5%, so an unattended default never tests right up against
    either extreme. Deduplicates in case rounding collides two points for
    a very small `available` or large `num_points`."""
    lo = max(1, round(available * 0.05))
    hi = max(lo + 1, round(available * 0.9))
    if num_points < 2:
        return [hi]
    step = (hi - lo) / (num_points - 1)
    return sorted({round(lo + i * step) for i in range(num_points)})


def print_summary(aspirate_pairs: list, dispense_pairs: list) -> None:
    lines = [f"{'microsteps':>12}  {'aspirate uL':>12}  {'dispense uL':>12}"]
    a, d = dict(aspirate_pairs), dict(dispense_pairs)
    for m in sorted(set(a) | set(d)):
        av = f"{a[m]:.2f}" if m in a else "-"
        dv = f"{d[m]:.2f}" if m in d else "-"
        lines.append(f"{m:>12}  {av:>12}  {dv:>12}")
    logger.info("=== Calibration summary ===\n" + "\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG),
        help="robot config YAML -- needs a mounted pipette on --side, a real deck "
        "calibration, and labware loaded on --aspirate-slot/--dispense-slot. Point "
        "this at a transport: {type: fake} config to --simulate without touching "
        "real hardware.",
    )
    parser.add_argument("--side", choices=sorted(_SIDES), default="left")
    parser.add_argument(
        "--tip-name",
        default="Opentrons OT-2 300ul no Filter",
        help="key this calibration is stored/matched under; must be in the config's "
        "tips: unless --tip-length-mm is also given",
    )
    parser.add_argument(
        "--tip-length-mm",
        default=59.0,
        type=float,
        help="Opentrons OT-2 300uL tip length by default; only used if --tip-name "
        "isn't already a known tip in the config",
    )

    parser.add_argument(
        "--aspirate-slot", default="7", help="deck slot holding the source (aspirate) labware"
    )
    parser.add_argument(
        "--dispense-slot", default="8", help="deck slot holding the destination (dispense) labware"
    )
    parser.add_argument("--aspirate-well", default="A1")
    parser.add_argument("--dispense-well", default="A1")
    parser.add_argument(
        "--well-ref",
        choices=("top", "bottom", "clearance"),
        default="clearance",
        help="reference height within each well -- \"clearance\" (default) is a safe "
        "standoff above the bottom, same as a normal aspirate/dispense routine step",
    )

    parser.add_argument(
        "--plunger-max-microsteps",
        type=int,
        default=15900,
        help="HARD SAFETY CEILING: the plunger (B on left, C on right) must never be "
        "commanded past this -- doing so detaches the tip instead of dispensing",
    )

    parser.add_argument(
        "--aspirate-microsteps",
        type=int,
        nargs="+",
        default=None,
        help="Phase A test strokes, microsteps from the empty reference (any order); "
        "default is --num-points evenly spaced strokes spanning most of the plunger's "
        "usable travel up to --plunger-max-microsteps, with a safety margin below it",
    )
    parser.add_argument(
        "--num-points",
        type=int,
        default=7,
        help="how many evenly-spaced Phase A test strokes to auto-generate when "
        "--aspirate-microsteps isn't given",
    )
    parser.add_argument(
        "--dispense-targets",
        type=int,
        nargs="+",
        help="Phase B partial-dispense targets, absolute microsteps; default is the "
        "reverse of the Phase A absolute positions",
    )
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument(
        "--density-mg-per-ul", type=float, default=0.998, help="water ~0.998 at 20C"
    )
    parser.add_argument(
        "--feed", type=int, help="plunger/final-approach feed rate, microsteps/sec; omit for default"
    )
    parser.add_argument(
        "--dwell-s",
        type=float,
        default=1.0,
        help="seconds to hold still, plunger already at target, at the bottom of each "
        "aspirate/dispense stroke before moving away -- lets the liquid actually finish "
        "moving (surface tension/viscosity lag behind the plunger itself stopping)",
    )
    parser.add_argument("--phase", choices=("aspirate", "dispense", "both"), default="both")
    parser.add_argument(
        "--aspirate-from",
        help="prior aspirate-phase YAML (see --out); required if " "--phase dispense",
    )
    parser.add_argument(
        "--out", help="output YAML path; default pipette_calibration_<side>_<tip>.yaml"
    )
    parser.add_argument("--skip-home", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan and exit without connecting"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="generate synthetic mass readings instead of prompting -- for testing/demo",
    )
    args = parser.parse_args()

    if args.phase == "dispense" and not args.aspirate_from:
        raise SystemExit("--phase dispense requires --aspirate-from a prior Phase A result")

    out_path = args.out or f"pipette_calibration_{args.side}_{args.tip_name}.yaml"

    robot = load_robot(args.config)
    side = _SIDES[args.side]
    pipette = robot.mounts[side].tool
    if pipette is None or not hasattr(pipette, "plunger"):
        raise SystemExit(f"no pipette attached to the {args.side} mount in {args.config!r}")
    if robot.calibration is None:
        raise SystemExit(
            f"{args.config!r} has no deck calibration -- gantry motion here goes through "
            "the same calibrated, well-addressed routine machinery as the rest of the app "
            "(see the module docstring), which needs a real calibration: section"
        )

    tip = robot.tips.get(args.tip_name)
    if tip is None:
        tip = TipGeometry(name=args.tip_name, length_mm=args.tip_length_mm)
    pipette.current_tip = tip  # so Z travel accounts for the tip length while calibrating

    plunger_axis = robot.mounts[side].plunger
    endstop_limit = robot.axes[plunger_axis].config.endstop_limit
    plunger_max = min(args.plunger_max_microsteps, endstop_limit)

    aspirate_labware = _labware_on_slot(robot, args.aspirate_slot)
    dispense_labware = _labware_on_slot(robot, args.dispense_slot)
    aspirate_loc = WellLocation(aspirate_labware.name, args.aspirate_well, ref=args.well_ref)
    dispense_loc = WellLocation(dispense_labware.name, args.dispense_well, ref=args.well_ref)

    bottom = pipette.plunger.bottom_microsteps
    strokes = (
        sorted(args.aspirate_microsteps)
        if args.aspirate_microsteps
        else _default_strokes(plunger_max - bottom, args.num_points)
    )
    max_stroke = strokes[-1]
    aspirate_positions = [bottom + s for s in strokes]
    dispense_targets = (
        sorted(args.dispense_targets, reverse=True)
        if args.dispense_targets
        else list(reversed(aspirate_positions))
    )

    all_plunger_targets = {bottom, *aspirate_positions, *dispense_targets}
    over_limit = sorted(t for t in all_plunger_targets if t > plunger_max)
    if over_limit:
        raise SystemExit(
            f"these plunger targets exceed --plunger-max-microsteps ({args.plunger_max_microsteps}, "
            f"axis endstop_limit {endstop_limit}) and would detach the tip: {over_limit}"
        )

    logger.info(
        f"Plan: {args.side} mount, pipette={pipette.name!r}, tip={args.tip_name!r}, bottom={bottom}\n"
        f"  Aspirate: slot {args.aspirate_slot} ({aspirate_labware.name}) well {args.aspirate_well}\n"
        f"  Dispense: slot {args.dispense_slot} ({dispense_labware.name}) well {args.dispense_well}\n"
        f"  Well ref: {args.well_ref}   Plunger ceiling: {plunger_max}\n"
        f"  Phase A strokes:  {strokes}  -> positions {aspirate_positions}\n"
        f"  Phase B targets:  {dispense_targets}\n"
        f"  phase={args.phase}  replicates={args.replicates}  density={args.density_mg_per_ul} mg/uL"
    )
    if args.dry_run:
        return

    with robot:
        if not args.skip_home:
            robot.home()  # leaves absolute mode
        # Defensive, even though this script never jogs and so never puts
        # the controller in G91: see the ambient-relative-mode bug fixed in
        # gui/manual_control.py's _go_to_point -- raw linear_move calls
        # (move_plunger) trust the caller is already in G90.
        robot.controller.set_absolute()

        if args.phase in ("aspirate", "both"):
            aspirate_pairs = [(bottom, 0.0)] + run_phase_a(
                robot,
                side,
                plunger_axis,
                plunger_max,
                bottom,
                strokes,
                aspirate_loc,
                dispense_loc,
                args.replicates,
                args.density_mg_per_ul,
                args.feed,
                args.dwell_s,
                simulate=args.simulate,
            )
        else:
            aspirate_pairs = [(bottom, 0.0)] + _load_points(args.aspirate_from, "aspirate")

        dispense_pairs = [(bottom, 0.0)]
        if args.phase in ("dispense", "both"):
            # A throwaway PlungerCalibration just to look up Phase A's fitted
            # volume for the fixed Phase B stroke (see module docstring) --
            # the dispense side is unused for that lookup, so it's given the
            # same points only to satisfy the constructor's validation.
            aspirate_only = PlungerCalibration.from_pairs(
                aspirate=aspirate_pairs, dispense=aspirate_pairs
            )
            dispense_pairs += run_phase_b(
                robot,
                side,
                plunger_axis,
                plunger_max,
                bottom,
                max_stroke,
                dispense_targets,
                aspirate_loc,
                dispense_loc,
                aspirate_only,
                args.replicates,
                args.density_mg_per_ul,
                args.feed,
                args.dwell_s,
                simulate=args.simulate,
            )

    if args.phase == "aspirate":
        print_summary(aspirate_pairs, [])
        write_yaml(
            out_path,
            pipette_name=pipette.name,
            side=args.side,
            tip=args.tip_name,
            density=args.density_mg_per_ul,
            aspirate=aspirate_pairs,
            dispense=aspirate_pairs,
        )
        logger.info(
            f"Wrote {out_path} (Phase A only -- re-run with --phase dispense --aspirate-from "
            f"{out_path} to finish)"
        )
    else:
        print_summary(aspirate_pairs, dispense_pairs)
        write_yaml(
            out_path,
            pipette_name=pipette.name,
            side=args.side,
            tip=args.tip_name,
            density=args.density_mg_per_ul,
            aspirate=aspirate_pairs,
            dispense=dispense_pairs,
        )
        logger.info(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
