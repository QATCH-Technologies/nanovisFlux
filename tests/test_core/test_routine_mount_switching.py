"""Routine.run threads a *current* mount through its steps rather than
pinning the whole run to one side: normally every step just gets whatever
side is already current (Routine.side to start), but SwitchMountStep
returns a new MountSide that becomes current for every step after it --
letting one routine freely address more than one mount instead of needing
to be written "for" a specific one (see routines/steps.py's own docstring)."""

from dataclasses import dataclass, field

from src.core import MountSide
from src.geometry.coordinates import DeckPoint
from src.routines import PointLocation, Routine, SwitchMountStep


@dataclass
class _RecordingStep:
    """A bare Step double that just records the side it was called with --
    avoids needing a real/fake robot to observe Routine.run's own
    side-threading logic in isolation."""

    seen: list = field(default_factory=list)

    def execute(self, robot, side):
        self.seen.append(side)

    def describe(self):
        return "recording step"


def test_routine_with_no_switch_uses_its_own_side_throughout():
    step = _RecordingStep()
    routine = Routine(side=MountSide.RIGHT).add(step, step, step)

    routine.run(robot=None)

    assert step.seen == [MountSide.RIGHT, MountSide.RIGHT, MountSide.RIGHT]


def test_run_side_argument_overrides_routine_default():
    step = _RecordingStep()
    routine = Routine(side=MountSide.LEFT).add(step)

    routine.run(robot=None, side=MountSide.RIGHT)

    assert step.seen == [MountSide.RIGHT]


def test_switch_mount_step_changes_side_for_every_step_after_it():
    step = _RecordingStep()
    routine = Routine(side=MountSide.LEFT).add(
        step, SwitchMountStep(MountSide.RIGHT), step, step
    )

    routine.run(robot=None)

    assert step.seen == [MountSide.LEFT, MountSide.RIGHT, MountSide.RIGHT]


def test_switch_mount_step_can_switch_back_and_forth():
    step = _RecordingStep()
    routine = Routine(side=MountSide.LEFT).add(
        step,
        SwitchMountStep(MountSide.RIGHT),
        step,
        SwitchMountStep(MountSide.LEFT),
        step,
    )

    routine.run(robot=None)

    assert step.seen == [MountSide.LEFT, MountSide.RIGHT, MountSide.LEFT]


class _RecordingRobot:
    """Just enough of Robot's interface for SwitchMountStep(where=...) to
    resolve and issue a move against, without any real hardware/transport."""

    def __init__(self):
        self.moves = []  # (point, side, feed)

    def safe_move_to(self, point, side, feed=None):
        self.moves.append((point, side, feed))


def test_switch_mount_step_with_where_moves_the_new_mount_there():
    robot = _RecordingRobot()
    point = DeckPoint(10.0, 20.0, 30.0)
    step = SwitchMountStep(MountSide.RIGHT, where=PointLocation(point))

    result = step.execute(robot, MountSide.LEFT)

    assert result is MountSide.RIGHT
    assert robot.moves == [(point, MountSide.RIGHT, None)]


def test_switch_mount_step_without_where_does_not_move():
    robot = _RecordingRobot()
    step = SwitchMountStep(MountSide.RIGHT)

    step.execute(robot, MountSide.LEFT)

    assert robot.moves == []


def test_switch_mount_step_describe():
    assert SwitchMountStep(MountSide.RIGHT).describe() == "switch to right mount"
    point = DeckPoint(1.0, 2.0, 3.0)
    described = SwitchMountStep(MountSide.LEFT, where=PointLocation(point)).describe()
    assert described.startswith("switch to left mount, move to")
