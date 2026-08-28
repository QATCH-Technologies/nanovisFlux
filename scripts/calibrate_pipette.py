"""Two-phase empirical calibration of a pipette's plunger.

This script builds a piecewise-linear `PlungerCalibration` for a specific (pipette, tip)
combination, replacing standard linear microstep models[cite: 1]. Aspirate and dispense
are measured separately to isolate their respective errors[cite: 1].

Calibration Phases:
    * Phase A (Aspirate): Varies the aspirate stroke length while performing identical,
      full purges[cite: 1]. This isolates the aspirate error[cite: 1].
    * Phase B (Dispense): Uses a fixed aspirate stroke and performs partial dispenses,
      recording cumulative mass[cite: 1]. Requires Phase A's curve to run (prior results
      are auto-loaded if available)[cite: 1].

Motion & Control:
    * Gantry: Uses standard, safe routing (`Robot.safe_move_to`) requiring a calibrated
      deck and labware[cite: 1].
    * Plunger: Controlled directly via raw motor microsteps rather than standard
      pipette routines to ensure precise calibration[cite: 1].

Usage & Safety:
    * Mass Entry: Operators must enter scale readings manually, or use the `--simulate`
      flag to test end-to-end with synthetic data[cite: 1].
    * Safety: A strict `--plunger-max-microsteps` ceiling prevents the pipette tip from
      detaching, which is checked both during planning and right before execution[cite: 1].
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
    """Convert a synthetic plunger stroke to the "true" volume it represents.

    Models the mild, seal-friction-like nonlinearity described in the module
    docstring's --simulate discussion: volume grows linearly with stroke
    length, less an efficiency loss at larger strokes controlled by
    `truth["nonlinearity"]`. Used by :func:`_synthetic_mass_mg` and
    :func:`_synthetic_cumulative_mass_mg` to generate synthetic readings from
    one of the two independent ground-truth curves (`_ASPIRATE_TRUTH`/
    `_DISPENSE_TRUTH`).

    Args:
        microsteps_from_bottom: Plunger stroke length, in microsteps,
            measured from the empty reference position.
        truth: Ground-truth curve parameters -- a mapping with
            `microsteps_per_ul` (the linear conversion factor) and
            `nonlinearity` (the efficiency-loss coefficient), i.e.
            `_ASPIRATE_TRUTH` or `_DISPENSE_TRUTH`.

    Returns:
        The synthetic "true" volume, in microliters, that
        `microsteps_from_bottom` represents under `truth`. Never negative.
    """
    linear = microsteps_from_bottom / truth["microsteps_per_ul"]
    return max(0.0, linear * (1.0 - truth["nonlinearity"] * microsteps_from_bottom))


def _synthetic_mass_mg(stroke: float, density: float, *, aspirating: bool) -> float:
    """Convert a synthetic plunger stroke to a synthetic mass reading.

    Selects the aspirate or dispense ground-truth curve (`_ASPIRATE_TRUTH`/
    `_DISPENSE_TRUTH`, see the module docstring's --simulate discussion) and
    converts the resulting synthetic volume to a mass using `density`,
    standing in for what an operator would otherwise read off a real scale.
    Used by :func:`run_phase_a` when `simulate=True`.

    Args:
        stroke: Plunger stroke length, in microsteps, measured from the
            empty reference position.
        density: Liquid density in mg per microliter, used to convert the
            synthetic volume to a synthetic mass.
        aspirating: Whether to use the aspirate ground-truth curve
            (`_ASPIRATE_TRUTH`) rather than the dispense one
            (`_DISPENSE_TRUTH`).

    Returns:
        The synthetic mass, in milligrams, that `stroke` would produce.
    """
    truth = _ASPIRATE_TRUTH if aspirating else _DISPENSE_TRUTH
    return _synthetic_volume_ul(stroke, truth) * density


def _synthetic_cumulative_mass_mg(
    bottom: int, fixed_position: int, target: int, density: float
) -> float:
    """Compute the synthetic CUMULATIVE mass dispensed at one Phase B target.

    Mirrors :func:`run_phase_b`'s real measurement protocol (see the module
    docstring's Phase B description and `run_phase_b`'s own docstring): the
    fixed aspirate stroke (`bottom` to `fixed_position`) represents a total
    volume under the dispense ground-truth curve (`_DISPENSE_TRUTH`), and the
    plunger's remaining distance from `bottom` to `target` represents what
    has NOT yet been dispensed. The synthetic reading returned here is the
    difference, converted to mass -- the same cumulative-since-start quantity
    an operator would report from one un-re-tared scale.

    Args:
        bottom: Plunger position, in microsteps, at the empty reference.
        fixed_position: Plunger position, in microsteps, after the fixed
            Phase B aspirate stroke.
        target: Plunger position, in microsteps, of the partial-dispense step
            being simulated.
        density: Liquid density in mg per microliter.

    Returns:
        The synthetic cumulative mass, in milligrams, dispensed by the time
        the plunger reaches `target`. Never negative.
    """
    total = _synthetic_volume_ul(bottom - fixed_position, _DISPENSE_TRUTH)
    remaining = _synthetic_volume_ul(bottom - target, _DISPENSE_TRUTH)
    return max(0.0, total - remaining) * density


def read_mass_mg(prompt: str, simulate_fn=None) -> float:
    """Prompt for a mass reading and keep asking until it parses as a number.

    This is the single seam between this script and an operator with a real
    scale -- every place that needs a mass reading goes through here, so
    swapping in `simulate_fn` (see the module docstring's --simulate
    discussion) is enough to exercise the whole two-phase flow without a
    human at the keyboard or any real hardware.

    Args:
        prompt: Text displayed to the operator (or logged, under
            `simulate_fn`) when requesting the reading.
        simulate_fn: Optional zero-argument callable returning a synthetic
            mass in milligrams. When given, it is called instead of
            prompting, and its result is logged in place of operator input.

    Returns:
        The mass reading in milligrams, either operator-entered or produced
        by `simulate_fn`.
    """
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
    robot,
    axis: AxisId,
    target: int,
    plunger_max: int,
    feed: int | None = None,
    *,
    verify: bool = True,
) -> None:
    """Move the plunger axis directly to a raw microstep target.

    This is the one place in the script that ever commands the plunger axis.
    It re-checks `plunger_max` immediately before sending, as a second,
    independent guard alongside the upfront plan-wide check in `main` (see
    SAFETY in the module docstring) -- moving past it detaches the tip
    instead of dispensing.

    Args:
        robot: Connected robot instance whose controller issues the move.
        axis: Plunger axis to command (B on the left mount, C on the right).
        target: Absolute plunger position, in microsteps, to move to.
        plunger_max: Hard safety ceiling -- the effective minimum of
            `--plunger-max-microsteps` and the axis's own `endstop_limit`.
        feed: Optional feed rate, in microsteps/sec, for the move.
        verify: Poll-confirm the plunger actually reached `target` before
            returning (see `Robot._await_settled`'s own docstring for why
            "ok" alone isn't trusted). On by default here, since a cut-short
            aspirate/dispense stroke would silently corrupt the whole
            calibration.

    Raises:
        RuntimeError: If `target` exceeds `plunger_max`.
    """
    if target > plunger_max:
        raise RuntimeError(
            f"refusing to move the plunger to {target} microsteps -- exceeds the "
            f"--plunger-max-microsteps safety ceiling ({plunger_max}); this would detach the tip"
        )
    robot.controller.linear_move({axis: target}, feed=feed)
    if verify:
        robot._await_settled({axis: target})


def _labware_on_slot(robot, slot_name: str):
    """Look up the labware placed on one named deck slot.

    Lets `--aspirate-slot`/`--dispense-slot` name a slot the way an operator
    thinks about the deck, rather than requiring them to know that slot's
    labware's config `name:`.

    Args:
        robot: Connected robot instance whose `labware` mapping is searched.
        slot_name: Deck slot name to look up, e.g. `"7"`.

    Returns:
        tuple[str, Labware]: The labware's config instance name and its
        `Labware` object.

    Raises:
        SystemExit: If no labware entry in the config is placed on
            `slot_name`.
    """
    for instance_name, lw in robot.labware.items():
        if lw.slot is not None and lw.slot.name == slot_name:
            return instance_name, lw
    raise SystemExit(
        f"no labware loaded on slot {slot_name!r} -- add a labware: entry with "
        f'slot: "{slot_name}" to the config (see configs/robot.yaml)'
    )


def _log_at(robot, side: MountSide, label: str, loc: WellLocation) -> None:
    """Log a move's target labware/well alongside its computed and actual raw motor position.

    Three separate numbers are logged on purpose: the resolved deck-mm
    point, the RAW MOTOR target that deck-mm point computes to, and the
    ACTUAL measured raw position (M114) after the move. Deck-mm alone can't
    tell you whether a calibration or tip-length miscalculation put the raw
    target somewhere wrong, or whether the move itself simply didn't reach a
    correctly-computed target -- having all three lets a bad calibration and
    a stalled/short move be told apart from the log alone.

    Args:
        robot: Connected robot instance to read calibration and controller
            position from.
        side: Mount whose vertical axis and tip offset are used to compute
            the raw target.
        label: Short human-readable label identifying the move, e.g.
            `"source (aspirate)"`.
        loc: Well location the move targeted.
    """
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
    """Run Phase A: measure the aspirate curve by varying the aspirate stroke.

    See the module docstring's Phase A description for the overall design:
    the dispense side of each trial is always an identical, full purge back
    to the empty reference (`bottom`), so its own error is constant across
    trials and the differences in measured volume between trials isolate the
    aspirate curve's shape. Each stroke in `strokes` is repeated `replicates`
    times and the resulting volumes are averaged.

    Args:
        robot: Connected robot instance driving the motion.
        side: Mount performing the aspirate/dispense cycle.
        plunger_axis: Plunger axis to command (B on the left mount, C on the
            right).
        plunger_max: Hard safety ceiling passed through to every
            :func:`move_plunger` call.
        bottom: Plunger position, in microsteps, at the empty reference.
        strokes: Aspirate stroke lengths to test, in microsteps from
            `bottom`.
        aspirate_loc: Well location of the aspirate source.
        dispense_loc: Well location of the dispense destination (the scale).
        replicates: Number of times to repeat each stroke; the reported
            volume for a stroke is the mean of its replicates.
        density: Liquid density in mg per microliter, used to convert each
            mass reading to a volume.
        feed: Optional feed rate, in microsteps/sec, for plunger and gantry
            moves.
        dwell_s: How long to hold still, plunger already at its target, at
            the bottom of each aspirate/dispense stroke. The stepper
            reaching its commanded position isn't the same as the liquid
            actually finishing moving -- surface tension and viscosity lag
            behind the plunger -- so raising away immediately can leave a
            stroke short of what it should have drawn or expelled.
        simulate: If `True`, generate synthetic mass readings via
            :func:`_synthetic_mass_mg` instead of prompting the operator.

    Returns:
        list[tuple[int, float]]: `(bottom - stroke, volume_ul)` pairs, one
        per stroke in `strokes`, giving the absolute plunger position and its
        averaged measured volume in microliters.
    """
    pairs = []
    for stroke in strokes:
        measurements = []
        for rep in range(1, replicates + 1):
            logger.info(
                f"[Phase A] stroke {stroke} usteps (position {bottom + stroke}), "
                f"replicate {rep}/{replicates}"
            )
            move_plunger(robot, plunger_axis, bottom, plunger_max, feed)  # 1. empty
            robot.safe_move_to(
                aspirate_loc.resolve(robot), side, feed=feed, verify=True
            )  # 2. to source
            _log_at(robot, side, "source (aspirate)", aspirate_loc)
            move_plunger(robot, plunger_axis, bottom - stroke, plunger_max, feed)  # 3. aspirate
            time.sleep(dwell_s)  # hold at the bottom, submerged, so the aspirate actually draws up
            robot.safe_move_to(
                dispense_loc.resolve(robot), side, feed=feed, verify=True
            )  # 4. to scale
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
        logger.info(
            f"-> {volume_ul:.2f} uL" + (f" (avg of {replicates})" if replicates > 1 else "")
        )
        pairs.append((bottom - stroke, volume_ul))
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
    """Run Phase B: measure the dispense curve by varying the dispense target.

    See the module docstring's Phase B description for the overall design:
    the aspirate side is always the same fixed stroke (`bottom` to
    `bottom - max_stroke`), so aspirate error is held constant, while the
    dispense target varies via partial dispenses within one continuous run.
    The same vessel returns to the same fixed spot between steps, and the
    operator reports the CUMULATIVE mass dispensed so far at each step
    (never re-tare mid-run); `aspirate_calibration` -- Phase A's fitted curve
    -- converts the fixed aspirate stroke to a known total volume so each
    step's remaining volume can be recovered as `total - cumulative`.

    Args:
        robot: Connected robot instance driving the motion.
        side: Mount performing the aspirate/dispense cycle.
        plunger_axis: Plunger axis to command (B on the left mount, C on the
            right).
        plunger_max: Hard safety ceiling passed through to every
            :func:`move_plunger` call.
        bottom: Plunger position, in microsteps, at the empty reference.
        max_stroke: Fixed aspirate stroke length, in microsteps from
            `bottom`, held constant for every replicate.
        targets: Absolute plunger positions, in microsteps, to partially
            dispense to, in the order they are visited within one replicate.
        aspirate_loc: Well location of the aspirate source.
        dispense_loc: Well location of the dispense destination (the scale).
        aspirate_calibration: Phase A's fitted aspirate curve, used to
            convert the fixed aspirate stroke to a known total volume.
        replicates: Number of times to repeat the full fixed-aspirate/
            partial-dispense sequence; the reported volume for each target
            is the mean of its replicates.
        density: Liquid density in mg per microliter, used to convert each
            cumulative mass reading to a volume.
        feed: Optional feed rate, in microsteps/sec, for plunger and gantry
            moves.
        dwell_s: See :func:`run_phase_a`'s own docstring.
        simulate: If `True`, generate synthetic cumulative mass readings via
            :func:`_synthetic_cumulative_mass_mg` instead of prompting the
            operator.

    Returns:
        list[tuple[int, float]]: `(target, remaining_volume_ul)` pairs, one
        per entry in `targets`, giving the absolute plunger position and its
        averaged measured remaining volume in microliters.
    """
    fixed_position = bottom - max_stroke
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
            logger.info(
                "lifted clear -- remove the vessel and weigh it (do NOT empty it or re-tare)."
            )
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
            robot.move_vertical_to(
                dispense_point.z, side, feed=feed, verify=True
            )  # back down for next step
            logger.info("place the vessel back in the same spot before the next step.")
    return [(t, sum(vals) / len(vals)) for t, vals in accum.items()]


def _load_points(path: str, key: str) -> list:
    """Load calibration points from one direction of a pipette_calibration YAML file.

    Accepts either a full config file with a top-level `pipette_calibration:`
    section (the shape `write_yaml` produces) or a file that is just that
    section's contents, so a hand-trimmed or bare calibration file also
    loads. Used by `main`'s `--aspirate-from` handling to load a prior Phase
    A result independently of the auto-loaded calibration in
    `pipette.tip_calibrations`.

    Args:
        path: Path to the YAML file to load.
        key: Which direction's points to read, `"aspirate"` or `"dispense"`.

    Returns:
        list[tuple[int, float]]: `(microsteps, volume_ul)` pairs in the order
        they appear in the file.
    """
    cfg = load_config(path)
    section = cfg.get("pipette_calibration", cfg)
    return [(p["microsteps"], p["volume_ul"]) for p in section[key]]


def write_yaml(
    path: str,
    *,
    pipette_name: str,
    tip: str,
    density: float,
    aspirate: list,
    dispense: list,
) -> None:
    """Write a pipette_calibration: YAML file for this (pipette, tip) result.

    Produces the shape `config/loader.py`'s `build_pipette_tip_calibrations`
    reads back. There is deliberately no `side:` in the output: a plunger's
    steps-to-volume mapping doesn't depend on which mount the pipette is on
    (see :class:`PlungerCalibration`), so unlike `mounts:`, this file is
    never split by side. Which mount `--side` drove during this run only
    matters for how the measurement was taken, not what gets saved.

    Args:
        path: Output file path. Parent directories are created as needed.
        pipette_name: Name of the pipette this calibration is for.
        tip: Tip name this calibration is for, matched against a pipette's
            `tip_calibrations` keys.
        density: Liquid density, in mg per microliter, used to take the
            measurements being saved.
        aspirate: `(microsteps, volume_ul)` pairs for the aspirate curve.
        dispense: `(microsteps, volume_ul)` pairs for the dispense curve.
    """
    import yaml

    data = {
        "pipette_calibration": {
            "pipette": pipette_name,
            "tip": tip,
            "density_mg_per_ul": density,
            "aspirate": [{"microsteps": m, "volume_ul": v} for m, v in aspirate],
            "dispense": [{"microsteps": m, "volume_ul": v} for m, v in dispense],
        }
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def _default_strokes(available: int, num_points: int) -> list:
    """Generate evenly spaced Phase A test strokes when none are given explicitly.

    Spans most of the plunger's usable travel from the empty reference (0)
    up toward `available` -- `plunger_max` minus `bottom_microsteps`, the
    room actually available before the tip-detach safety ceiling -- but
    stops at 90% of it and starts at 5%, so an unattended default never
    tests right up against either extreme.

    Args:
        available: Usable plunger travel, in microsteps, between the empty
            reference and the safety ceiling.
        num_points: Number of strokes to generate. Fewer than 2 yields a
            single stroke at the 90% mark.

    Returns:
        list[int]: Ascending, deduplicated stroke lengths in microsteps.
        Deduplication guards against rounding collapsing two points onto the
        same value for a very small `available` or large `num_points`.
    """
    lo = max(1, round(available * 0.05))
    hi = max(lo + 1, round(available * 0.9))
    if num_points < 2:
        return [hi]
    step = (hi - lo) / (num_points - 1)
    return sorted({round(lo + i * step) for i in range(num_points)})


def print_summary(aspirate_pairs: list, dispense_pairs: list) -> None:
    """Log a combined aspirate/dispense volume table for a calibration run.

    Rows are keyed by plunger position in microsteps and sorted ascending; a
    position measured on only one side of the calibration (e.g. a `--phase
    aspirate`-only run) shows `-` for the other column rather than being
    dropped, so a single-phase run still gets a readable summary.

    Args:
        aspirate_pairs: `(microsteps, volume_ul)` pairs from the aspirate
            curve.
        dispense_pairs: `(microsteps, volume_ul)` pairs from the dispense
            curve. May be empty.
    """
    lines = [f"{'microsteps':>12}  {'aspirate uL':>12}  {'dispense uL':>12}"]
    a, d = dict(aspirate_pairs), dict(dispense_pairs)
    for m in sorted(set(a) | set(d)):
        av = f"{a[m]:.2f}" if m in a else "-"
        dv = f"{d[m]:.2f}" if m in d else "-"
        lines.append(f"{m:>12}  {av:>12}  {dv:>12}")
    logger.info("=== Calibration summary ===\n" + "\n".join(lines))


def main() -> None:
    """Parse CLI arguments and drive the two-phase pipette calibration.

    Connects to the robot described by `--config`, validates the deck
    calibration and plunger safety ceiling described in the module
    docstring's SAFETY section, runs Phase A and/or Phase B per `--phase`
    (auto-loading a prior Phase A result for `--phase dispense` when one is
    already saved, per the module docstring's Phase B description), and
    writes the result with :func:`write_yaml`. See each flag's own
    `--help` text below for the full CLI surface.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG),
        help="robot config YAML -- needs a mounted pipette on --side, a real deck "
        "calibration, and labware loaded on --aspirate-slot/--dispense-slot. Point "
        "this at a transport: {type: simulated} config to --simulate without touching "
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
        help='reference height within each well -- "clearance" (default) is a safe '
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
        "--feed",
        type=int,
        help="plunger/final-approach feed rate, microsteps/sec; omit for default",
    )
    parser.add_argument(
        "--dwell-s",
        type=float,
        default=1.0,
        help="seconds to hold still, plunger already at target, at the bottom of each "
        "aspirate/dispense stroke before moving away -- lets the liquid actually finish "
        "moving (surface tension/viscosity lag behind the plunger itself stopping)",
    )
    parser.add_argument("--phase", choices=("aspirate", "dispense", "both"), default="dispense")
    parser.add_argument(
        "--aspirate-from",
        help="prior aspirate-phase YAML (see --out) to use for --phase dispense, overriding "
        "whatever's already auto-loaded for this pipette/tip (see "
        "config/loader.py's build_pipette_tip_calibrations) -- only needed to force a "
        "specific file; --phase dispense on its own already uses that auto-loaded result "
        "if one exists",
    )
    parser.add_argument(
        "--out",
        help="output YAML path; default <config's dir>/tools/pipettes/"
        "<pipette name>/calibrations/<tip>.yaml -- see config/loader.py's "
        "build_pipette_tip_calibrations, which auto-discovers every file under a "
        "pipette's own <pipette name>/calibrations/ directory",
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

    robot = load_robot(args.config)
    side = _SIDES[args.side]
    pipette = robot.mounts[side].tool
    if pipette is None or not hasattr(pipette, "plunger"):
        raise SystemExit(f"no pipette attached to the {args.side} mount in {args.config!r}")

    out_path = args.out or str(
        Path(args.config).resolve().parent
        / "tools"
        / "pipettes"
        / pipette.name
        / "calibrations"
        / f"{'_'.join(args.tip_name.split())}.yaml"
    )
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

    aspirate_instance, aspirate_labware = _labware_on_slot(robot, args.aspirate_slot)
    dispense_instance, dispense_labware = _labware_on_slot(robot, args.dispense_slot)
    aspirate_loc = WellLocation(aspirate_instance, args.aspirate_well, ref=args.well_ref)
    dispense_loc = WellLocation(dispense_instance, args.dispense_well, ref=args.well_ref)

    bottom = pipette.plunger.bottom_microsteps
    strokes = (
        sorted(args.aspirate_microsteps)
        if args.aspirate_microsteps
        else _default_strokes(bottom, args.num_points)
    )
    max_stroke = strokes[-1]
    aspirate_positions = [bottom - s for s in strokes]
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
            robot.home()
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
        elif args.aspirate_from:
            aspirate_pairs = _load_points(args.aspirate_from, "aspirate")
        else:
            existing = pipette.tip_calibrations.get(args.tip_name)
            if existing is None:
                raise SystemExit(
                    f"--phase dispense needs a prior Phase A result for pipette "
                    f"{pipette.name!r}, tip {args.tip_name!r} -- none is auto-loaded (no "
                    f"file under {pipette.name}/calibrations/ for this tip) and no "
                    "--aspirate-from was given. Run --phase aspirate first (writes there "
                    "by default), or pass --aspirate-from a prior result directly."
                )
            aspirate_pairs = [(p.microsteps, p.volume_ul) for p in existing.aspirate_points]

        dispense_pairs = [(bottom, 0.0)]
        if args.phase in ("dispense", "both"):
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
            tip=args.tip_name,
            density=args.density_mg_per_ul,
            aspirate=aspirate_pairs,
            dispense=aspirate_pairs,
        )
        logger.info(
            f"Wrote {out_path} (Phase A only -- re-run with --phase dispense to finish; "
            "auto-loaded from here for this same pipette/tip, no --aspirate-from needed "
            "unless out_path was overridden away from the default location)"
        )
    else:
        print_summary(aspirate_pairs, dispense_pairs)
        write_yaml(
            out_path,
            pipette_name=pipette.name,
            tip=args.tip_name,
            density=args.density_mg_per_ul,
            aspirate=aspirate_pairs,
            dispense=dispense_pairs,
        )
        logger.info(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
