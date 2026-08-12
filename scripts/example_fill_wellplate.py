"""Example: pick up a tip, aspirate from a fixed source well, dispense into
a destination well, blow out into the trash, drop the tip in the trash --
then repeat with a fresh tip for the next destination well.

Demonstrates src/routines/ (Location/Step objects plus the transfer() and
distribute() helpers) instead of hand-computing every x/y/z coordinate --
compare with config/protocols/fill_24well_plate.json, which is this exact
pattern with every one of its ~100 steps unrolled and coordinates baked in
by hand.

Layout (a minimal 4-slot deck matching the scenario this was written for):
  slot 1  -- 96-tip rack, tips consumed starting at A1
  slot 2  -- source well plate, aspirate always from A1
  slot 3  -- destination well plate, dispense across each well in turn
  slot 12 -- trash: blow out and drop each spent tip here

Runs against the in-memory FakeTransport by default, so it can be exercised
without hardware attached; pass --port to drive real hardware over serial.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

from loguru import logger

from src.core import MountSide
from src.deck import (
    BottomShape,
    Deck,
    TipRackDefinition,
    WellPlateDefinition,
    WellShape,
)
from src.geometry import AffineTransform2D, AxisScale, DeckCalibration, DeckPoint
from src.robot import Robot
from src.routines import Routine, SlotLocation, TipSequence, WellLocation, distribute
from src.tools import Pipette, PlungerModel, TipPickup
from src.transport import FakeTransport, SerialTransport

# -- standard labware definitions -- declared once, placed on any slot ----

TIP_RACK = TipRackDefinition(
    identifier="tiprack1",
    footprint_mm=(127.76, 85.48),
    height_mm=64.5,
    rows=8,
    cols=12,
    row_spacing_mm=9,
    col_spacing_mm=9,
    grid_offset=DeckPoint(14.38, 11.24, 90),  # A1 top = tip first-contact height
    tip_volume_ul=300,
    tip_length_mm=51.7,
)

WELL_PLATE_96 = WellPlateDefinition(
    identifier="wellplate_96",
    footprint_mm=(127.76, 85.48),
    height_mm=14.4,
    rows=8,
    cols=12,
    row_spacing_mm=9,
    col_spacing_mm=9,
    grid_offset=DeckPoint(14.38, 11.24, 14.4),  # A1 top = plate top surface
    well_volume_ul=360,
    well_shape=WellShape.CIRCULAR,
    well_diameter_mm=6.9,
    well_depth_mm=10.9,
    well_bottom=BottomShape.ROUND,
    bottom_clearance_mm=1.5,
)


def build_robot(port: str | None) -> Robot:
    transport = SerialTransport(port) if port else FakeTransport()

    # Placeholder calibration -- replace with points/z_zero captured for this
    # machine (see src/config/robot.example.yaml for the field meanings).
    calibration = DeckCalibration(
        xy=AffineTransform2D.from_point_pairs(
            [(0, 0), (100, 0), (0, 100)], [(0, 0), (21320, 0), (0, 14478)]
        ),
        z_scale=AxisScale(steps_per_mm=25.0),
        z_zero={MountSide.LEFT: 144000, MountSide.RIGHT: 144000},
    )

    deck = Deck.grid(
        rows=1, cols=4, origin=DeckPoint(10, 10), pitch=(140, 0), names=["1", "2", "3", "12"]
    )

    robot = Robot(transport, calibration=calibration, deck=deck, travel_z_mm=120)

    # User just declares the labware and the slot; robot.load computes the
    # well/tip offsets (and, for a tip rack, registers its TipGeometry too).
    robot.load(TIP_RACK, "1")
    robot.load(replace(WELL_PLATE_96, identifier="source"), "2")
    robot.load(replace(WELL_PLATE_96, identifier="dest"), "3")

    robot.attach(
        MountSide.LEFT,
        Pipette(name="p300", plunger=PlungerModel(microsteps_per_ul=50), max_volume_ul=300),
    )
    return robot


def build_routine(volume_ul: float, n_wells: int) -> Routine:
    tips = TipSequence("tiprack1", rows=8, cols=12, start="A1")
    source = WellLocation("source", "A1")
    trash = SlotLocation("12")

    well_names = [f"{r}{c}" for r in "ABCDEFGH" for c in range(1, 13)][:n_wells]
    dests = [WellLocation("dest", name) for name in well_names]

    steps = distribute(
        volume_ul,
        source,
        dests,
        tip="tiprack1",
        tips=tips,
        pickup=TipPickup(press_z_mm=90),
        trash=trash,
    )
    return Routine(name="fill well plate", side=MountSide.LEFT).extend(steps)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", help="serial port for real hardware (e.g. COM6); omit to use the fake transport"
    )
    parser.add_argument(
        "--volume", type=float, default=50.0, help="microliters per destination well"
    )
    parser.add_argument("--wells", type=int, default=24, help="number of destination wells to fill")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the planned steps and exit without connecting"
    )
    args = parser.parse_args()

    routine = build_routine(args.volume, args.wells)
    planned = "\n".join(f"  {line}" for line in routine.dry_run())
    logger.info(f"Planned routine ({len(routine.steps)} steps):\n{planned}")

    if args.dry_run:
        return

    robot = build_robot(args.port)
    with robot:
        robot.home()
        routine.run(
            robot,
            on_step=lambda i, s: logger.info(f"[{i + 1}/{len(routine.steps)}] {s.describe()}"),
        )
    logger.info("Done.")


if __name__ == "__main__":
    main()
