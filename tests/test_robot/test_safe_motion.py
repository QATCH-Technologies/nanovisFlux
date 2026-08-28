"""Robot.safe_move_to's two safety properties added after a reported
near-collision on real hardware:

1. verify=True by default -- every leg of the raise/cross/descend arc is
   position-confirmed (Robot._await_settled) before the next one is
   issued, instead of trusting a G-code 'ok' alone (see _await_settled's
   own docstring for why that wasn't reliable).
2. The raise height itself accounts for whatever's tallest in any slot
   between the mount's current position and the target -- not just a
   single fixed travel_z_mm -- so a tall object loaded in a slot the
   direct route crosses over still gets cleared (see
   Robot._path_clearance_mm/_slots_crossed/_slot_top_height_mm)."""

from __future__ import annotations

import pytest

from src.core import AxisId, MountSide
from src.deck import Deck, Labware, Slot, SlotObstacle, Well, WellGeometry
from src.geometry.calibration import DeckCalibration
from src.geometry.coordinates import DeckPoint
from src.geometry.transform import AffineTransform2D
from src.geometry.units import AxisScale
from src.robot import Robot
from src.transport.simulated import SimulatedTransport


def _labware(name: str, top_z: float) -> Labware:
    return Labware(name=name, wells={"A1": Well("A1", DeckPoint(5.0, 5.0, top_z), WellGeometry())})


def _robot_with_deck(*, travel_z_mm: float = 30.0) -> Robot:
    """Three slots in a row: "1" (short source labware), "2" (a tall
    object -- neither source nor destination, just something in between),
    "3" (short destination labware)."""
    deck = Deck()
    deck.add(Slot(name="1", origin=DeckPoint(0.0, 0.0), size=(100.0, 100.0)))
    deck.add(Slot(name="2", origin=DeckPoint(110.0, 0.0), size=(100.0, 100.0)))
    deck.add(Slot(name="3", origin=DeckPoint(220.0, 0.0), size=(100.0, 100.0)))

    calibration = DeckCalibration(
        xy=AffineTransform2D(a=100.0, b=0.0, tx=0.0, c=0.0, d=100.0, ty=0.0),
        z_scale=AxisScale(steps_per_mm=100.0),  # -> 3200 raw microsteps/mm (see units.MICROSTEPS_PER_STEP)
        # Comfortably above any deck-mm height this file tests (tall_obj's
        # 80mm + margin, well under 200mm) once converted at 3200
        # microsteps/mm -- too small a z_zero here previously drove target
        # raw positions negative for an 85mm clearance, a test-fixture bug
        # unrelated to the safe_move_to logic being tested.
        z_zero={MountSide.LEFT: 800_000},
    )
    robot = Robot(
        SimulatedTransport(axis_limits={"X": 500_000, "Y": 500_000, "Z": 800_000}),
        calibration=calibration,
        deck=deck,
        travel_z_mm=travel_z_mm,
    )
    # Robot._validate_targets checks robot.axes' own endstop_limit
    # independently of SimulatedTransport's axis_limits above -- widen both
    # in lockstep, or every move in this file raises ValueError before the
    # simulated transport is ever reached.
    for axis, limit in ((AxisId.X, 500_000), (AxisId.Y, 500_000), (AxisId.Z, 800_000)):
        robot.axes[axis].config.endstop_limit = limit
    robot.load_labware(_labware("source", 10.0), "1", key="source")
    robot.load_labware(_labware("tall_obj", 80.0), "2", key="tall_obj")
    robot.load_labware(_labware("dest", 10.0), "3", key="dest")
    return robot


# -- path-aware clearance height ---------------------------------------------


def test_path_clearance_accounts_for_tall_intermediate_slot():
    robot = _robot_with_deck()
    robot.connect()
    robot.home()
    robot.move_to(DeckPoint(5.0, 5.0, 20.0), MountSide.LEFT)  # sits in slot "1"

    clr = robot._path_clearance_mm(MountSide.LEFT, (225.0, 5.0), robot.travel_z_mm)

    # tall_obj's own top (80.0) plus the margin, not just the flat default
    assert clr >= 85.0
    assert clr > robot.travel_z_mm


def test_path_clearance_ignores_slots_outside_the_path():
    """Moving entirely within slot "1" shouldn't be inflated by slot "2"'s
    tall object, which the path never crosses."""
    robot = _robot_with_deck()
    robot.connect()
    robot.home()
    robot.move_to(DeckPoint(2.0, 2.0, 20.0), MountSide.LEFT)

    clr = robot._path_clearance_mm(MountSide.LEFT, (8.0, 8.0), robot.travel_z_mm)

    assert clr == robot.travel_z_mm


def test_path_clearance_never_goes_below_the_requested_default():
    """A path crossing only short labware (source's own 10mm top) must
    not LOWER the clearance below whatever was requested -- only ever
    raise it."""
    robot = _robot_with_deck(travel_z_mm=50.0)
    robot.connect()
    robot.home()
    robot.move_to(DeckPoint(2.0, 2.0, 20.0), MountSide.LEFT)

    clr = robot._path_clearance_mm(MountSide.LEFT, (8.0, 8.0), robot.travel_z_mm)

    assert clr == 50.0


def test_path_clearance_falls_back_when_current_position_unknown():
    """Never homed -- report_position reads -1, so there's no trustworthy
    start point to compute a path from; must fall back to the plain
    default rather than guessing or raising."""
    robot = _robot_with_deck()
    robot.connect()

    clr = robot._path_clearance_mm(MountSide.LEFT, (225.0, 5.0), robot.travel_z_mm)

    assert clr == robot.travel_z_mm


def test_slots_crossed_skips_dimensionless_slots():
    """A named slot with no footprint (e.g. a calibration reference point
    or dock with size left at its (0.0, 0.0) default) has nothing to
    overlap a path bounding box with -- it must be excluded rather than
    matching every path via a degenerate always-true overlap test."""
    deck = Deck()
    deck.add(Slot(name="1", origin=DeckPoint(0.0, 0.0), size=(50.0, 50.0)))
    deck.add(Slot(name="dock", origin=DeckPoint(10.0, 10.0)))  # size defaults to (0.0, 0.0)
    robot = Robot(SimulatedTransport(), deck=deck)

    crossed = robot._slots_crossed((0.0, 0.0), (40.0, 40.0))

    assert [s.name for s in crossed] == ["1"]


def test_slot_top_height_considers_obstacles_and_walls_not_just_labware():
    deck = Deck()
    deck.add(
        Slot(
            name="12",
            origin=DeckPoint(0.0, 0.0),
            size=(100.0, 100.0),
            wall_height_mm=85.0,
            obstacles=[SlotObstacle(offset=(0, 0), size=(20, 20), height_mm=40.0)],
        )
    )
    robot = Robot(SimulatedTransport(), deck=deck)

    assert robot._slot_top_height_mm(deck["12"]) == 85.0  # walls are the tallest thing here


def test_safe_move_to_raises_higher_when_crossing_a_tall_slot():
    """End-to-end: the actual raise leg safe_move_to sends is high enough
    to clear the intermediate tall object, not just travel_z_mm."""
    robot = _robot_with_deck()
    robot.connect()
    robot.home()
    robot.move_to(DeckPoint(5.0, 5.0, 20.0), MountSide.LEFT)  # start in slot "1"

    sent = []
    robot.controller.on_send = lambda line, command: sent.append(line.strip().upper())
    robot.safe_move_to(DeckPoint(225.0, 5.0, 20.0), MountSide.LEFT)  # target in slot "3"

    raise_line = next(ln for ln in sent if ln.startswith(("G0", "G1")) and "Z" in ln and "X" not in ln)
    raw_target = int(raise_line.split("Z", 1)[1].split()[0])
    raised_deck_z = robot.calibration.motor_to_deck_z(raw_target, MountSide.LEFT)
    assert raised_deck_z >= 85.0
    assert raised_deck_z > robot.travel_z_mm


# -- verify=True by default --------------------------------------------------


def test_safe_move_to_verifies_by_default():
    robot = _robot_with_deck()
    robot.connect()
    robot.home()
    calls = []
    robot._await_settled = lambda *a, **k: calls.append((a, k))

    robot.safe_move_to(DeckPoint(5.0, 5.0, 20.0), MountSide.LEFT)

    assert calls, "expected _await_settled to be called at least once by default"


def test_safe_move_to_verify_false_skips_confirmation():
    robot = _robot_with_deck()
    robot.connect()
    robot.home()
    calls = []
    robot._await_settled = lambda *a, **k: calls.append((a, k))

    robot.safe_move_to(DeckPoint(5.0, 5.0, 20.0), MountSide.LEFT, verify=False)

    assert not calls, "verify=False must skip settling confirmation entirely"


def test_move_to_and_raise_z_verify_by_default_too():
    robot = _robot_with_deck()
    robot.connect()
    robot.home()
    calls = []
    robot._await_settled = lambda *a, **k: calls.append((a, k))

    robot.move_to(DeckPoint(5.0, 5.0, 20.0), MountSide.LEFT)
    assert calls, "move_to should verify by default"

    calls.clear()
    robot.move_vertical_to(0.0, MountSide.LEFT)  # below clearance, so raise_z must move
    robot.raise_z(MountSide.LEFT)
    assert calls, "raise_z should verify by default"


# -- _current_deck_xy --------------------------------------------------------


def test_current_deck_xy_returns_none_without_calibration():
    robot = Robot(SimulatedTransport(), deck=Deck())

    assert robot._current_deck_xy(MountSide.LEFT) is None


def test_current_deck_xy_returns_none_when_axes_are_unhomed():
    """Unhomed axes report -1 (SimulatedTransport's convention for "no
    trustworthy position yet") -- _current_deck_xy must not translate that
    into a bogus deck coordinate."""
    robot = _robot_with_deck()
    robot.connect()  # never homed

    assert robot._current_deck_xy(MountSide.LEFT) is None


def test_current_deck_xy_returns_the_deck_position_once_homed_and_moved():
    robot = _robot_with_deck()
    robot.connect()
    robot.home()
    robot.move_to(DeckPoint(12.0, 34.0, 5.0), MountSide.LEFT)

    xy = robot._current_deck_xy(MountSide.LEFT)

    assert xy == pytest.approx((12.0, 34.0), abs=0.1)


# -- stall -> resend retries -------------------------------------------------
#
# Added after a real-hardware run confirmed a physical stall mid-routine
# (the axis genuinely stopped short of target, its 'ok' already received --
# see move_to's own docstring) crashed the whole 122-step routine on the
# very first occurrence. A couple of automatic retries rides out an
# occasional firmware/comms hiccup instead of aborting the entire run over
# one cut-short move.


def _stub_robot() -> Robot:
    """A bare Robot -- _await_settled only touches self.controller, so no
    calibration/deck is needed to exercise it directly."""
    return Robot(SimulatedTransport())


def test_await_settled_resends_on_stall_and_recovers():
    robot = _stub_robot()
    # Position stays stuck at 100 (a real stall) until resend() is called,
    # at which point it "reaches" target -- simulating a resend that
    # genuinely gets the axis moving again.
    state = {"resent": False}
    robot.controller.report_position = lambda: {AxisId.X: 200 if state["resent"] else 100}
    resend_calls = []

    def resend():
        resend_calls.append(1)
        state["resent"] = True

    robot._await_settled(
        {AxisId.X: 200}, resend=resend, stall_timeout=0.02, poll_interval=0.005, timeout=5.0
    )

    assert len(resend_calls) == 1


def test_await_settled_gives_up_after_max_resends():
    robot = _stub_robot()
    robot.controller.report_position = lambda: {AxisId.X: 100}  # never moves, ever
    resend_calls = []

    try:
        robot._await_settled(
            {AxisId.X: 200},
            resend=lambda: resend_calls.append(1),
            max_resends=2,
            stall_timeout=0.02,
            poll_interval=0.005,
            timeout=5.0,
        )
        assert False, "expected TimeoutError"
    except TimeoutError as exc:
        assert "2 retries" in str(exc)

    assert len(resend_calls) == 2


def test_await_settled_times_out_while_still_moving_not_stalled():
    """Distinct from the stall branch above: position keeps changing on
    every poll (so the stall path never triggers), it just never reaches
    the target before the overall timeout elapses -- e.g. a move toward an
    unreachable target that's still genuinely, slowly, in progress."""
    robot = _stub_robot()
    state = {"pos": 0}

    def report():
        state["pos"] += 1
        return {AxisId.X: state["pos"]}

    robot.controller.report_position = report

    with pytest.raises(TimeoutError, match="did not settle within"):
        robot._await_settled(
            {AxisId.X: 10_000}, timeout=0.05, poll_interval=0.005, stall_timeout=10.0
        )


def test_await_settled_no_resend_fails_immediately_on_stall():
    """resend=None (the default for callers with no natural resend action)
    must still fail fast on a stall, same as before resend existed --
    just without ever retrying."""
    robot = _stub_robot()
    robot.controller.report_position = lambda: {AxisId.X: 100}

    try:
        robot._await_settled({AxisId.X: 200}, stall_timeout=0.02, poll_interval=0.005, timeout=5.0)
        assert False, "expected TimeoutError"
    except TimeoutError as exc:
        assert "retr" not in str(exc)
