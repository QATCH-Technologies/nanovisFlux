"""Location and its concrete resolvers (WellLocation, SlotLocation,
PointLocation). Each resolve() defers coordinate lookup to a robot at
execution time -- see location.py's own module docstring -- so these tests
build a small real Deck/Labware/Robot fixture rather than mocking robot.deck
or robot.labware directly."""

from __future__ import annotations

import pytest

from src.deck import Deck, Labware, Slot, Well, WellGeometry
from src.geometry.coordinates import DeckPoint
from src.robot import Robot
from src.routines.location import Location, PointLocation, SlotLocation, WellLocation
from src.transport.simulated import SimulatedTransport


def _labware(name: str) -> Labware:
    return Labware(
        name=name,
        wells={
            "A1": Well(
                "A1",
                DeckPoint(5.0, 5.0, 10.0),
                WellGeometry(depth_mm=40.0, bottom_clearance_mm=2.0),
            )
        },
    )


def _robot_with_deck() -> Robot:
    deck = Deck()
    deck.add(Slot(name="1", origin=DeckPoint(100.0, 50.0, 0.0), size=(100.0, 100.0)))
    robot = Robot(SimulatedTransport(), deck=deck)
    robot.load_labware(_labware("plate"), "1", key="plate")
    return robot


# -- Location base ------------------------------------------------------


def test_location_base_resolve_is_not_implemented():
    with pytest.raises(NotImplementedError):
        Location().resolve(None)


# -- WellLocation ---------------------------------------------------------


def test_well_location_resolves_top_reference():
    robot = _robot_with_deck()
    point = WellLocation("plate", "A1", ref="top").resolve(robot)
    # slot origin (100, 50, 0) + well offset (5, 5, 10), top ref has zero z delta
    assert point == DeckPoint(105.0, 55.0, 10.0)


def test_well_location_resolves_bottom_reference():
    robot = _robot_with_deck()
    point = WellLocation("plate", "A1", ref="bottom").resolve(robot)
    # bottom is depth_mm (40.0) below the well opening
    assert point.z == pytest.approx(10.0 - 40.0)


def test_well_location_default_ref_is_clearance_using_labware_default():
    robot = _robot_with_deck()
    point = WellLocation("plate", "A1").resolve(robot)  # ref defaults to "clearance"
    # clearance stands off bottom_clearance_mm (2.0) above the true bottom
    assert point.z == pytest.approx(10.0 - (40.0 - 2.0))


def test_well_location_clearance_mm_overrides_labware_default():
    robot = _robot_with_deck()
    point = WellLocation("plate", "A1", ref="clearance", clearance_mm=5.0).resolve(robot)
    assert point.z == pytest.approx(10.0 - (40.0 - 5.0))


def test_well_location_offset_is_applied_after_the_well_reference():
    robot = _robot_with_deck()
    point = WellLocation("plate", "A1", ref="top", offset=DeckPoint(1.0, 2.0, 3.0)).resolve(robot)
    assert point == DeckPoint(106.0, 57.0, 13.0)


def test_well_location_unknown_labware_raises_key_error():
    robot = _robot_with_deck()
    with pytest.raises(KeyError):
        WellLocation("nonexistent", "A1").resolve(robot)


def test_well_location_unknown_well_raises_key_error():
    robot = _robot_with_deck()
    with pytest.raises(KeyError):
        WellLocation("plate", "Z9").resolve(robot)


# -- SlotLocation ---------------------------------------------------------


def test_slot_location_resolves_slot_origin_plus_offset():
    robot = _robot_with_deck()
    point = SlotLocation("1", offset=DeckPoint(0.0, 0.0, 5.0)).resolve(robot)
    assert point == DeckPoint(100.0, 50.0, 5.0)


def test_slot_location_default_offset_is_zero():
    robot = _robot_with_deck()
    assert SlotLocation("1").resolve(robot) == DeckPoint(100.0, 50.0, 0.0)


def test_slot_location_raises_runtime_error_when_deck_is_not_configured():
    robot = Robot(SimulatedTransport())  # no deck passed in
    assert robot.deck is None

    with pytest.raises(RuntimeError, match="deck"):
        SlotLocation("1").resolve(robot)


def test_slot_location_unknown_slot_raises_key_error():
    robot = _robot_with_deck()
    with pytest.raises(KeyError):
        SlotLocation("nonexistent").resolve(robot)


# -- PointLocation ---------------------------------------------------------


def test_point_location_returns_the_stored_point_unchanged():
    point = DeckPoint(1.0, 2.0, 3.0)
    assert PointLocation(point).resolve(robot=None) is point


def test_point_location_ignores_the_supplied_robot():
    point = DeckPoint(7.0, 8.0, 9.0)
    robot = _robot_with_deck()
    assert PointLocation(point).resolve(robot) == point
