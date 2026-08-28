"""Example routine for transferring 5uL from a 96-well plate to a 24-well plate.

This script is the headless, Python-based equivalent of the GUI-loadable
`nanovis_transfer_example.json` routine. It iterates through up to 24 well pairs,
sequencing tip pickup, aspiration (slot 1), dispensing with a pause (slot 3),
and tip disposal (slot 12).

Key Configuration Details:
    * Mount-Agnostic: The active mount is chosen at runtime via `--side`. The
      routine directs the mount dynamically using `SwitchMountStep`.
    * Hardware Simulation: Defaults to an in-memory `SimulatedTransport` for safe,
      hardware-free testing. Pass the `--port` argument to override the config
      and drive real hardware over serial.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from src.config.loader import resolve_robot_config
from src.core import MountSide
from src.geometry.coordinates import DeckPoint
from src.gui.robot_factory import build_robot
from src.routines import (
    AspirateStep,
    DelayStep,
    DispenseStep,
    DropTipStep,
    HomeStep,
    PickUpTipStep,
    Routine,
    SlotLocation,
    SwitchMountStep,
    TipSequence,
    WellLocation,
)
from src.tools import TipPickup
from src.transport import SerialTransport, SimulatedTransport

_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "configs" / "robot.yaml"

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT}

_TIP_RACK = "tiprack1"
_TIP_NAME = "opentrons_p300_ot2_tip"
_SOURCE = "source"
_DEST = "dest"
_PRESS_Z_MM = 64.6
_VOLUME_UL = 5.0
_PAUSE_S = 1.0
_TRASH_OFFSET = DeckPoint(60.0, 60.0, 0.0)
_TRASH_EJECT_Z_MM = 120.0


def build_routine(robot, n_wells: int, side: MountSide) -> Routine:
    """Build the pick-tip/aspirate/dispense/drop-tip routine described in
    the module docstring, addressed by well name against `robot`'s own
    loaded labware.

    `n_wells` is clamped to the smaller of the source and destination
    plate's own well counts -- the destination (24 wells) in practice,
    since the source (96 wells) has far more. This means an
    operator-supplied `n_wells` that exceeds what's actually on the deck
    doesn't fail outright; it just runs the largest well-paired sequence
    that's actually possible, with a warning logged so the shortfall
    isn't silent.

    `side` is applied via a :class:`SwitchMountStep` at the front of the
    routine, not through the :class:`Routine` constructor's own `side`
    (which is only a fallback used by :meth:`Routine.run` for a routine
    that never switches mounts at all). This keeps which mount runs this
    routine visible as an explicit step in the routine's own step list --
    the same way it would need to be if this routine ever had to switch
    mounts mid-run, e.g. aspirating on one pipette and dispensing on
    another.

    Args:
        robot: :class:`Robot` instance whose `labware` supplies the well
            names for `_SOURCE` and `_DEST`.
        n_wells: Requested number of source/destination well pairs to
            run; clamped to whichever of the two plates has fewer wells.
        side: Mount that the routine's `SwitchMountStep` switches to
            before the first tip pickup.

    Returns:
        Routine: Ordered pick-up/aspirate/dispense/pause/drop-tip steps
        for each well pair, ready to be dry-run or executed against
        `robot`.
    """
    source_names = list(robot.labware[_SOURCE].wells)
    dest_names = list(robot.labware[_DEST].wells)
    n = min(n_wells, len(source_names), len(dest_names))
    if n < n_wells:
        logger.warning(
            f"--wells {n_wells} exceeds the smaller of {_SOURCE} ({len(source_names)}) / "
            f"{_DEST} ({len(dest_names)}) -- running {n} instead"
        )

    tips = TipSequence(_TIP_RACK, rows=8, cols=12, start="A1")
    routine = Routine(name="nanovis transfer example")
    routine.add(HomeStep(), SwitchMountStep(side))
    for src_name, dest_name in zip(source_names[:n], dest_names[:n]):
        routine.extend(
            [
                PickUpTipStep(next(tips), _TIP_NAME, TipPickup(press_z_mm=_PRESS_Z_MM)),
                AspirateStep(_VOLUME_UL, WellLocation(_SOURCE, src_name)),
                DispenseStep(_VOLUME_UL, WellLocation(_DEST, dest_name)),
                DelayStep(_PAUSE_S),
                DropTipStep(SlotLocation("12", offset=_TRASH_OFFSET), _TRASH_EJECT_Z_MM),
            ]
        )
    return routine


def main() -> None:
    """Run this script as a CLI.

    Parses arguments, resolves the robot config, builds a :class:`Robot`
    via :func:`src.gui.robot_factory.build_robot`, builds the routine
    (see :func:`build_routine`), and logs its dry-run plan. Unless
    `--dry-run` is passed, also connects to the robot and executes the
    routine, logging each step as it completes.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", default=str(_DEFAULT_CONFIG), help="robot config YAML")
    parser.add_argument(
        "--port",
        default="COM6",
        help="serial port for real hardware (e.g. COM6); omit to use the simulated transport",
    )
    parser.add_argument(
        "--side",
        choices=sorted(_SIDES),
        default="left",
        help="which mount runs this routine",
    )
    parser.add_argument(
        "--wells", type=int, default=24, help="number of source/dest well pairs to run"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned steps and exit without connecting",
    )
    args = parser.parse_args()

    cfg = resolve_robot_config(args.config)
    transport = SerialTransport(args.port) if args.port else SimulatedTransport()
    robot = build_robot(cfg, transport)

    routine = build_routine(robot, args.wells, _SIDES[args.side])
    planned = "\n".join(f"  {line}" for line in routine.dry_run())
    logger.info(f"Planned routine ({len(routine.steps)} steps):\n{planned}")
    if args.dry_run:
        return

    with robot:
        routine.run(
            robot,
            on_step=lambda i, s: logger.info(f"[{i + 1}/{len(routine.steps)}] {s.describe()}"),
        )
    logger.info("Done.")


if __name__ == "__main__":
    main()
