"""ScriptedInput (src/control/inputs.py): a dependency-free InputSource that
replays a fixed action sequence through session.handle(), used for
deterministic tests and scripted jog sequences without a real input device.

A minimal fake session (not a mock -- just a small stub exposing the two
things InputSource.run() actually touches, `running` and `handle()`) stands
in for a real jog session so these tests exercise ScriptedInput's own
control flow in isolation."""
import pytest

from src.control.inputs import InputSource, ScriptedInput


class _FakeSession:
    """Records dispatched actions; can simulate stopping mid-sequence."""

    def __init__(self, stop_after: str | None = None):
        self.running = True
        self.handled: list = []
        self._stop_after = stop_after

    def handle(self, action) -> None:
        self.handled.append(action)
        if action == self._stop_after:
            self.running = False


def test_input_source_is_abstract():
    with pytest.raises(TypeError):
        InputSource()


def test_scripted_input_materializes_any_iterable_into_a_list():
    si = ScriptedInput(iter(["jog_x+", "jog_z-"]))

    assert si.actions == ["jog_x+", "jog_z-"]


def test_run_dispatches_each_action_in_order():
    si = ScriptedInput(["jog_x+", "jog_z-", "select_mount"])
    session = _FakeSession()

    si.run(session)

    assert session.handled == ["jog_x+", "jog_z-", "select_mount"]


def test_run_stops_early_when_the_session_stops_running():
    """A scripted action that itself causes the session to stop (e.g. a
    quit/estop action) must prevent any later actions from being dispatched."""
    si = ScriptedInput(["jog_x+", "estop", "jog_z-"])
    session = _FakeSession(stop_after="estop")

    si.run(session)

    assert session.handled == ["jog_x+", "estop"]
    assert session.running is False


def test_run_with_no_actions_does_nothing():
    si = ScriptedInput([])
    session = _FakeSession()

    si.run(session)

    assert session.handled == []
