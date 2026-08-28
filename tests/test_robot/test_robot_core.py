"""Robot facade coverage for the pieces that tie the other layers together:
controller connection lifecycle (connect/disconnect/context-manager), tool
attachment, labware/tip-geometry registration, tip-offset resolution, mount
convenience accessors, and emergency_stop. Motion/settling/clearance behavior
is covered by test_motion.py, test_safe_motion.py, and test_pipette_verify.py
-- this file is everything else on the Robot facade."""

from __future__ import annotations

import pytest

from src.core import MountSide
from src.deck import Deck, Labware, Slot, TipRackDefinition, WellPlateDefinition
from src.geometry.coordinates import DeckPoint
from src.robot import Robot
from src.tools import Tool, TouchProbe, UltrasonicSensor
from src.transport.simulated import SimulatedTransport


# -- connect / disconnect / context-manager lifecycle ------------------------


def test_connect_opens_the_controller_and_returns_self():
    robot = Robot(SimulatedTransport())

    result = robot.connect()

    assert result is robot
    # A real (unstubbed) open() ran and its startup banner was consumed --
    # proof connect() actually drove the controller, not just returned self.
    assert robot.controller.banner == ["OpenFlux OT-2 Stepper Controller (simulated)"]


def test_disconnect_closes_the_controller():
    robot = Robot(SimulatedTransport())
    robot.connect()
    closed = []
    robot.controller.close = lambda: closed.append(True)

    robot.disconnect()

    assert closed == [True]


def test_context_manager_connects_on_enter_and_disconnects_on_exit():
    robot = Robot(SimulatedTransport())
    events = []
    robot.controller.open = lambda: events.append("open")
    robot.controller.close = lambda: events.append("close")

    with robot as entered:
        assert entered is robot
        assert events == ["open"]

    assert events == ["open", "close"]


def test_context_manager_disconnects_even_when_the_body_raises():
    robot = Robot(SimulatedTransport())
    events = []
    robot.controller.close = lambda: events.append("close")

    with pytest.raises(ValueError):
        with robot:
            raise ValueError("boom")

    assert events == ["close"], "the controller must still be closed after an exception"


# -- attach -------------------------------------------------------------------


class _RecordingTool(Tool):
    """A real Tool subclass (not a mock) that records on_attach calls while
    still running the base class's own association logic."""

    name = "recorder"

    def __init__(self):
        super().__init__()
        self.attach_calls: list = []

    def on_attach(self, mount, robot) -> None:
        super().on_attach(mount, robot)
        self.attach_calls.append((mount, robot))


def test_attach_updates_the_mount_and_invokes_on_attach_with_mount_and_robot():
    robot = Robot(SimulatedTransport())
    tool = _RecordingTool()

    robot.attach(MountSide.RIGHT, tool)

    mount = robot.mounts[MountSide.RIGHT]
    assert mount.tool is tool
    assert tool.attach_calls == [(mount, robot)]
    assert tool.mount is mount  # Tool.on_attach's own base behavior also ran


# -- left / right / rear -------------------------------------------------------


def test_left_right_rear_are_none_before_anything_is_attached():
    robot = Robot(SimulatedTransport())

    assert robot.left() is None
    assert robot.right() is None
    assert robot.rear() is None


def test_left_right_rear_return_the_tool_attached_to_each_mount():
    robot = Robot(SimulatedTransport())
    left_tool = TouchProbe(name="left-probe")
    right_tool = TouchProbe(name="right-probe")
    rear_tool = UltrasonicSensor()
    robot.attach(MountSide.LEFT, left_tool)
    robot.attach(MountSide.RIGHT, right_tool)
    robot.attach(MountSide.REAR, rear_tool)

    assert robot.left() is left_tool
    assert robot.right() is right_tool
    assert robot.rear() is rear_tool


# -- load_labware ---------------------------------------------------------------


def test_load_labware_raises_without_a_configured_deck():
    robot = Robot(SimulatedTransport())
    labware = Labware(name="plate")

    with pytest.raises(RuntimeError, match="no deck configured"):
        robot.load_labware(labware, "1")


def test_load_labware_defaults_the_registry_key_to_the_labware_name():
    deck = Deck()
    deck.add(Slot(name="1", origin=DeckPoint(0.0, 0.0), size=(100.0, 100.0)))
    robot = Robot(SimulatedTransport(), deck=deck)
    labware = Labware(name="plate")

    result = robot.load_labware(labware, "1")

    assert result is labware
    assert robot.labware == {"plate": labware}


def test_load_labware_explicit_key_lets_same_named_labware_coexist():
    deck = Deck()
    deck.add(Slot(name="1", origin=DeckPoint(0.0, 0.0), size=(100.0, 100.0)))
    deck.add(Slot(name="2", origin=DeckPoint(150.0, 0.0), size=(100.0, 100.0)))
    robot = Robot(SimulatedTransport(), deck=deck)
    plate_a = Labware(name="plate")
    plate_b = Labware(name="plate")

    robot.load_labware(plate_a, "1", key="plate_a")
    robot.load_labware(plate_b, "2", key="plate_b")

    # Without the explicit keys, the second call would silently overwrite
    # the first registry entry since both share the same labware.name.
    assert robot.labware == {"plate_a": plate_a, "plate_b": plate_b}


# -- load (definition-driven placement + tip-geometry registration) -----------


def test_load_raises_without_a_configured_deck():
    robot = Robot(SimulatedTransport())
    definition = TipRackDefinition(
        identifier="tips_300",
        footprint_mm=(127.0, 85.0),
        height_mm=50.0,
        rows=1,
        cols=1,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
    )

    with pytest.raises(RuntimeError, match="no deck configured"):
        robot.load(definition, "1")


def test_load_registers_tip_geometry_for_a_definition_with_callable_tip_geometry():
    deck = Deck()
    deck.add(Slot(name="1", origin=DeckPoint(0.0, 0.0), size=(150.0, 150.0)))
    robot = Robot(SimulatedTransport(), deck=deck)
    definition = TipRackDefinition(
        identifier="tips_300",
        footprint_mm=(127.0, 85.0),
        height_mm=50.0,
        rows=8,
        cols=12,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
        tip_volume_ul=300.0,
        tip_length_mm=51.7,
    )

    labware = robot.load(definition, "1")

    assert robot.labware["tips_300"] is labware
    assert "tips_300" in robot.tips
    tip = robot.tips["tips_300"]
    assert tip.length_mm == 51.7
    assert tip.max_volume_ul == 300.0


def test_load_does_not_touch_tips_for_a_definition_without_tip_geometry():
    deck = Deck()
    deck.add(Slot(name="1", origin=DeckPoint(0.0, 0.0), size=(150.0, 150.0)))
    robot = Robot(SimulatedTransport(), deck=deck)
    definition = WellPlateDefinition(
        identifier="plate_96",
        footprint_mm=(127.0, 85.0),
        height_mm=14.0,
        rows=8,
        cols=12,
        row_spacing_mm=9.0,
        col_spacing_mm=9.0,
    )

    robot.load(definition, "1")

    assert robot.tips == {}


# -- tip_offset -----------------------------------------------------------------


def test_tip_offset_is_zero_with_no_tool_attached():
    robot = Robot(SimulatedTransport())

    assert robot.tip_offset(MountSide.LEFT) == 0.0


def test_tip_offset_is_zero_for_a_tool_with_no_tip_offset_mm_method():
    """UltrasonicSensor has no tip_offset_mm -- it's not a vertically
    actuated tool, so the getattr/callable check must fall back to 0.0
    instead of raising."""
    robot = Robot(SimulatedTransport())
    robot.attach(MountSide.LEFT, UltrasonicSensor())

    assert robot.tip_offset(MountSide.LEFT) == 0.0


def test_tip_offset_returns_the_attached_tools_reported_length():
    robot = Robot(SimulatedTransport())
    robot.attach(MountSide.RIGHT, TouchProbe(length_mm=42.5))

    assert robot.tip_offset(MountSide.RIGHT) == 42.5


# -- emergency_stop ---------------------------------------------------------


def test_emergency_stop_sends_the_stop_command_and_clears_homed_state():
    robot = Robot(SimulatedTransport())
    robot.connect()
    robot.home()
    assert all(axis.homed for axis in robot.axes.values())
    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())

    robot.emergency_stop()

    assert sent == ["M112"]
    assert all(not axis.homed for axis in robot.axes.values())
