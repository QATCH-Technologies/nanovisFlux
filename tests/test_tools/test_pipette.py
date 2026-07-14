from typing import Dict, List, Optional, Tuple

import pytest

from src.tools.pipette import Pipette


class FakeMotionController:
    """Hand-rolled test double, matching this codebase's existing convention
    (tests/mock_connection.py) rather than unittest.mock -- records calls so
    tests can assert exact move sequences without MotionController's mode
    tracking / G-code serialization getting in the way."""

    def __init__(self, current_position: Optional[Dict[str, Optional[float]]] = None):
        self.current_position: Dict[str, Optional[float]] = current_position or {}
        self.calls: List[Tuple[str, dict, Optional[float]]] = []

    def move_relative(self, offsets: dict, speed: Optional[float] = None) -> None:
        self.calls.append(("move_relative", offsets, speed))
        for axis, delta in offsets.items():
            current = self.current_position.get(axis, 0.0) or 0.0
            self.current_position[axis] = current + delta

    def move_absolute(self, positions: dict, speed: Optional[float] = None) -> None:
        self.calls.append(("move_absolute", positions, speed))
        for axis, value in positions.items():
            self.current_position[axis] = value


def make_pipette(motion: FakeMotionController, **overrides) -> Pipette:
    kwargs = dict(
        mount_axis="Z",
        plunger_axis="B",
        max_volume=300.0,
        steps_per_ul=100,
        motion=motion,
        blowout_distance=100,
        plunger_max_steps=20000,
        tip_pickup_presses=3,
        tip_pickup_press_depth=300.0,
        tip_pickup_press_speed=300.0,
    )
    kwargs.update(overrides)
    return Pipette(**kwargs)


def test_pick_up_tip_issues_press_cycles():
    motion = FakeMotionController(current_position={"Z": 0.0})
    pipette = make_pipette(motion)

    pipette.pick_up_tip()

    move_calls = [c for c in motion.calls if c[0] == "move_relative"]
    assert len(move_calls) == 6  # 3 presses * (down + up)
    for i in range(0, 6, 2):
        assert move_calls[i][1] == {"Z": 300.0}
        assert move_calls[i + 1][1] == {"Z": -300.0}
    assert pipette.has_tip is True


def test_pick_up_tip_respects_explicit_presses_override():
    motion = FakeMotionController(current_position={"Z": 0.0})
    pipette = make_pipette(motion)

    pipette.pick_up_tip(presses=1)

    move_calls = [c for c in motion.calls if c[0] == "move_relative"]
    assert len(move_calls) == 2


def test_drop_tip_drives_plunger_to_max_steps():
    motion = FakeMotionController(current_position={"B": 0.0})
    pipette = make_pipette(motion)
    pipette.current_volume = 150.0
    pipette.has_tip = True

    pipette.drop_tip()

    assert motion.calls == [("move_absolute", {"B": 20000}, 500.0)]
    assert pipette.has_tip is False
    assert pipette.current_volume == 0.0


def test_drop_tip_raises_without_plunger_max_steps():
    motion = FakeMotionController(current_position={"B": 0.0})
    pipette = make_pipette(motion, plunger_max_steps=None)

    with pytest.raises(RuntimeError):
        pipette.drop_tip()

    assert motion.calls == []


def test_aspirate_raises_when_projected_position_hits_limit():
    motion = FakeMotionController(current_position={"B": 0.0})
    pipette = make_pipette(motion)

    # 250uL * 100 steps/uL = 25000 steps, over the 20000-step limit.
    with pytest.raises(RuntimeError):
        pipette.aspirate(volume=250.0)

    assert motion.calls == []


def test_aspirate_succeeds_when_under_limit():
    motion = FakeMotionController(current_position={"B": 0.0})
    pipette = make_pipette(motion)

    pipette.aspirate(volume=100.0)

    assert motion.calls == [("move_relative", {"B": 10000.0}, 300.0)]
    assert pipette.current_volume == 100.0


def test_dispense_not_blocked_by_plunger_limit():
    motion = FakeMotionController(current_position={"B": 19000.0})
    pipette = make_pipette(motion)
    pipette.current_volume = 190.0

    pipette.dispense(volume=100.0)

    assert motion.calls == [("move_relative", {"B": -10000.0}, 300.0)]


def test_blowout_not_blocked_by_plunger_limit():
    motion = FakeMotionController(current_position={"B": 19000.0})
    pipette = make_pipette(motion)
    pipette.current_volume = 190.0

    pipette.blowout()

    assert motion.calls == [
        ("move_relative", {"B": -100}, 500.0),
        ("move_absolute", {"B": 0.0}, 500.0),
    ]
    assert pipette.current_volume == 0.0
