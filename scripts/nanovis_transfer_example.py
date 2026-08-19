"""Example: pick up a fresh tip, aspirate 5uL from the 96-well plate (slot
1), dispense 5uL onto the QATCH nanovis 24-well plate (slot 3) with a pause
to let the last drop fall, then drop the spent tip in the trash (slot 12) --
repeat for each well pair, up to the smaller plate's 24 wells.

Python-script twin of configs/routines/nanovis_transfer_example.json (the
GUI-loadable version, built from src/gui/routine_model.py's step model) --
this one is built from src/routines/ instead (Location/Step objects), for
running headless or importing as a library. Both walk the exact same
physical sequence against the exact same configs/robot.yaml labware; the
trash drop point/height match between the two for the same reason (see
_TRASH_OFFSET/_TRASH_EJECT_Z_MM below).

Not written "for" a specific mount: --side picks it at run time, and the
routine itself only ever learns which mount to use via an explicit
SwitchMountStep (see src/routines/steps.py) rather than a side baked into
the Routine object -- the same mechanism a routine would use mid-run to
address a second mount, e.g. aspirating on the left pipette and dispensing
on the right one, which this one doesn't need but could.

Runs against the in-memory FakeTransport by default, so it can be exercised
without hardware attached; pass --port to drive real hardware over serial
(overriding whatever configs/robot.yaml's own transport: says, same as the
GUI connection bar -- see gui/robot_factory.py).
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
from src.transport import FakeTransport, SerialTransport

#: Anchored to this script's own location, matching calibrate_pipette.py's
#: _DEFAULT_CONFIG -- a bare relative string would resolve against wherever
#: the process happened to be invoked from instead.
_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "configs" / "robot.yaml"

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT}

_TIP_RACK = "tiprack1"        # robot.yaml labware: instance, slot "10"
_TIP_NAME = "opentrons_p300_ot2_tip"   # robot.yaml tips: entry matching that rack
_SOURCE = "source"            # robot.yaml labware: instance, slot "1" (96-well)
_DEST = "dest"                # robot.yaml labware: instance, slot "3" (nanovis 24-well)
_PRESS_Z_MM = 64.6            # tiprack1's own measured first-contact height (its grid.origin.z)
_VOLUME_UL = 5.0
_PAUSE_S = 1.0                # "with pause" -- let the last drop fall before lifting away

#: Trash drop point: slot 12's origin (see configs/deck.yaml) plus an offset
#: comfortably inside its 170x164mm footprint and clear of its front-left
#: 37.5x37mm obstacle block. eject_z_mm matches configs/robot.yaml's own
#: travel_z_mm -- the safest available choice (guaranteed clear of every
#: known obstacle, including the bin's 85mm walls) for an as-yet-unverified
#: exact drop height. Both match configs/routines/nanovis_transfer_example.json.
_TRASH_OFFSET = DeckPoint(100.0, 100.0, 0.0)
_TRASH_EJECT_Z_MM = 120.0


def build_routine(robot, n_wells: int, side: MountSide) -> Routine:
    """See module docstring. `n_wells` is clamped to the smaller of
    source/dest's own well counts -- the destination (24 wells) in
    practice, since the source (96 wells) has far more.

    `side` is applied via a SwitchMountStep, not the Routine constructor
    (whose own `side` is only a fallback for a routine that never
    switches at all -- see Routine.run) -- so which mount runs this is
    always visible as an explicit step in the routine itself, the same
    way it would be if this needed to switch mid-run."""
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
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", default=str(_DEFAULT_CONFIG), help="robot config YAML")
    parser.add_argument(
        "--port", help="serial port for real hardware (e.g. COM6); omit to use the fake transport"
    )
    parser.add_argument(
        "--side", choices=sorted(_SIDES), default="left", help="which mount runs this routine"
    )
    parser.add_argument(
        "--wells", type=int, default=24, help="number of source/dest well pairs to run"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the planned steps and exit without connecting"
    )
    args = parser.parse_args()

    cfg = resolve_robot_config(args.config)
    transport = SerialTransport(args.port) if args.port else FakeTransport()
    robot = build_robot(cfg, transport)

    routine = build_routine(robot, args.wells, _SIDES[args.side])
    planned = "\n".join(f"  {line}" for line in routine.dry_run())
    logger.info(f"Planned routine ({len(routine.steps)} steps):\n{planned}")
    if args.dry_run:
        return

    with robot:
        routine.run(
            robot, on_step=lambda i, s: logger.info(f"[{i + 1}/{len(routine.steps)}] {s.describe()}")
        )
    logger.info("Done.")


if __name__ == "__main__":
    main()
