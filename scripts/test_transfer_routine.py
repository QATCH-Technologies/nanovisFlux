"""Smoke-test routine: connect to the robot, pick up a tip from slot 1,
aspirate from a well plate in slot 2, and dispense into a well plate in
slot 3.

Labware is declared once as a *definition* (footprint, grid, well/tip
geometry, spacing, grid offset -- see src/deck/definitions.py) and then
placed on a slot; the well/tip offsets are computed from the definition,
never hand-picked per script.

Runs against the in-memory FakeTransport by default so it can be exercised
without hardware attached; pass --port to drive real hardware over serial.
"""
from __future__ import annotations
import argparse
from dataclasses import replace

from src.core import MountSide
from src.transport import FakeTransport, SerialTransport
from src.geometry import DeckPoint, AffineTransform2D, AxisScale, DeckCalibration
from src.deck import Deck, WellPlateDefinition, TipRackDefinition, WellShape, BottomShape
from src.tools import Pipette, PlungerModel, TipPickup
from src.robot import Robot
from src.routines import (Routine, WellLocation, PickUpTipStep, AspirateStep,
                          DispenseStep, DropTipStep)

# -- standard labware definitions -- declared once, placed on any slot ----

TIP_RACK = TipRackDefinition(
    identifier="p300_tiprack_96",
    footprint_mm=(127.76, 85.48),
    height_mm=64.5,
    rows=8, cols=12,
    row_spacing_mm=9, col_spacing_mm=9,
    grid_offset=DeckPoint(14.38, 11.24, 90),   # A1 top = tip first-contact height
    tip_volume_ul=300,
    tip_length_mm=51.7,
)

WELL_PLATE_96 = WellPlateDefinition(
    identifier="generic_96_wellplate_360ul",
    footprint_mm=(127.76, 85.48),
    height_mm=14.4,
    rows=8, cols=12,
    row_spacing_mm=9, col_spacing_mm=9,
    grid_offset=DeckPoint(14.38, 11.24, 14.4),  # A1 top = plate top surface
    well_volume_ul=360,
    well_shape=WellShape.CIRCULAR,
    well_diameter_mm=6.9,
    well_depth_mm=10.9,
    well_bottom=BottomShape.ROUND,
    bottom_clearance_mm=1.5,
)
SOURCE_PLATE = replace(WELL_PLATE_96, identifier="source_plate")
DEST_PLATE = replace(WELL_PLATE_96, identifier="dest_plate")


def build_robot(port: str | None) -> Robot:
    transport = SerialTransport(port) if port else FakeTransport()

    # Placeholder calibration -- replace with points/z_zero captured for this
    # machine (see src/config/robot.example.yaml for the field meanings).
    calibration = DeckCalibration(
        xy=AffineTransform2D.from_point_pairs(
            [(0, 0), (100, 0), (0, 100)],
            [(0, 0), (21320, 0), (0, 14478)]),
        z_scale=AxisScale(steps_per_mm=25.0),
        z_zero={MountSide.LEFT: 144000, MountSide.RIGHT: 144000})

    deck = Deck.grid(rows=1, cols=3, origin=DeckPoint(10, 10), pitch=(140, 0),
                     names=["1", "2", "3"])

    robot = Robot(transport, calibration=calibration, deck=deck, travel_z_mm=120)

    # User just declares the labware and the slot; robot.load computes the
    # well/tip offsets (and, for a tip rack, registers its TipGeometry too).
    robot.load(TIP_RACK, "1")
    robot.load(SOURCE_PLATE, "2")
    robot.load(DEST_PLATE, "3")

    robot.attach(MountSide.LEFT, Pipette(
        name="p300", plunger=PlungerModel(microsteps_per_ul=50), max_volume_ul=300))
    return robot


def build_routine(volume_ul: float) -> Routine:
    tip_at = WellLocation("p300_tiprack_96", "A1", ref="top")   # tip top = first-contact height
    return Routine(name="slot1 -> slot2 -> slot3 transfer", side=MountSide.LEFT).add(
        PickUpTipStep(tip_at, TIP_RACK.identifier, TipPickup(press_z_mm=90)),
        AspirateStep(volume_ul, WellLocation("source_plate", "A1")),   # ref="clearance"
        DispenseStep(volume_ul, WellLocation("dest_plate", "A1")),     # ref="clearance"
        DropTipStep(tip_at, eject_z_mm=90),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="serial port for real hardware (e.g. COM6); omit to use the fake transport")
    parser.add_argument("--volume", type=float, default=100.0, help="microliters to transfer")
    parser.add_argument("--dry-run", action="store_true", help="print the planned steps and exit without connecting")
    args = parser.parse_args()

    routine = build_routine(args.volume)
    print("Planned routine:")
    for line in routine.dry_run():
        print(" ", line)

    if args.dry_run:
        return

    robot = build_robot(args.port)
    with robot:
        robot.home()
        routine.run(robot, on_step=lambda i, s: print(f"[{i + 1}/{len(routine.steps)}] {s.describe()}"))
    print("Done.")


if __name__ == "__main__":
    main()
