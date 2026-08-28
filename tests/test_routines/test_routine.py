"""Routine behavior not already covered by test_mount_switching.py (which
owns the side-threading / SwitchMountStep coverage): extend() with a plain
iterable, dry_run()'s numbered formatting, and run()'s on_step callback
firing plus exception propagation from a step or the callback itself."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.routines import CommentStep, DelayStep, HomeStep, Routine


def test_extend_appends_steps_from_a_plain_iterable_in_order():
    routine = Routine().add(CommentStep("first"))

    result = routine.extend([CommentStep("second"), CommentStep("third")])

    assert result is routine  # fluent, like add()
    assert [s.text for s in routine.steps] == ["first", "second", "third"]


def test_extend_consumes_a_generator_fully():
    routine = Routine()

    def gen():
        yield CommentStep("a")
        yield CommentStep("b")

    routine.extend(gen())

    assert [s.text for s in routine.steps] == ["a", "b"]


def test_dry_run_formats_one_based_numbered_descriptions():
    routine = Routine().add(HomeStep(), CommentStep("note"), DelayStep(1.5))

    assert routine.dry_run() == [
        " 1. home all",
        " 2. # note",
        " 3. delay 1.5s",
    ]


def test_dry_run_on_an_empty_routine_is_an_empty_list():
    assert Routine().dry_run() == []


def test_dry_run_pads_double_digit_positions_without_a_leading_zero():
    routine = Routine().extend(CommentStep(str(i)) for i in range(10))
    lines = routine.dry_run()
    assert lines[9] == "10. # 9"


@dataclass
class _RecordingStep:
    """Bare Step double recording the side it ran with -- same pattern as
    test_mount_switching.py's _RecordingStep, no real robot required."""

    seen: list = field(default_factory=list)

    def execute(self, robot, side):
        self.seen.append(side)

    def describe(self):
        return "recording step"


def test_run_invokes_on_step_before_each_step_with_zero_based_index():
    step_a, step_b = _RecordingStep(), _RecordingStep()
    routine = Routine().add(step_a, step_b)
    calls = []

    routine.run(robot=None, on_step=lambda i, s: calls.append((i, s)))

    assert calls == [(0, step_a), (1, step_b)]
    # on_step fired strictly before each step executed
    assert step_a.seen and step_b.seen


def test_run_without_on_step_callback_does_not_require_one():
    routine = Routine().add(_RecordingStep())
    routine.run(robot=None)  # must not raise for the default on_step=None


class _BoomStep:
    def execute(self, robot, side):
        raise ValueError("boom")

    def describe(self):
        return "boom"


def test_run_propagates_an_exception_raised_by_a_step():
    routine = Routine().add(_BoomStep())

    with pytest.raises(ValueError, match="boom"):
        routine.run(robot=None)


def test_run_stops_at_the_failing_step_and_never_reaches_later_steps():
    step_after = _RecordingStep()
    routine = Routine().add(_BoomStep(), step_after)

    with pytest.raises(ValueError):
        routine.run(robot=None)

    assert step_after.seen == []


def test_run_propagates_an_exception_raised_by_the_on_step_callback():
    step = _RecordingStep()
    routine = Routine().add(step)

    def failing_callback(i, s):
        raise RuntimeError("callback exploded")

    with pytest.raises(RuntimeError, match="callback exploded"):
        routine.run(robot=None, on_step=failing_callback)

    # the callback raised before the step itself ran
    assert step.seen == []
