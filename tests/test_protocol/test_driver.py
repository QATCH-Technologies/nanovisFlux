"""Controller: context-manager lifecycle, probe()/measure_distance() result
parsing, emergency/quick stop, reset_input_buffer(), and _read_response()'s
timeout/NOT-ok branches.

SimulatedTransport (src/transport/simulated.py) never itself emits a
`NOT ok` line -- every recognized command in its `_handle()` resolves to
`ok` (or a silent no-op for config/stop commands). To exercise
Controller's NOT-ok -> typed-exception path realistically we prime the
transport's internal `_queue` with a raw `NOT ok (...)` line ahead of the
next command's own response, the same way a real controller's error line
would arrive before anything else. Similarly, a genuine "controller never
responds" timeout is simulated by stubbing `transport.write_line` to a
no-op for one call (matching this codebase's existing convention of
swapping in a lambda for a single collaborator method, as in
tests/test_robot/test_safe_motion.py).

Also note: per ProbeResult's docstring, probe results always report the X,
Y, and A axis registers regardless of which axis was actually probed --
this is a real firmware quirk the simulator reproduces, not a test bug.
"""

from __future__ import annotations

import pytest

from src.core import AxisId
from src.protocol import commands as cmd
from src.protocol.driver import Controller
from src.protocol.errors import AxisNotHomedError, TransportError
from src.protocol.responses import DistanceResult
from src.transport.simulated import SimulatedTransport


# -- context-manager lifecycle -------------------------------------------------


def test_context_manager_opens_transport_and_captures_banner():
    transport = SimulatedTransport()
    with Controller(transport) as ctrl:
        assert isinstance(ctrl, Controller)
        assert ctrl.banner == ["OpenFlux OT-2 Stepper Controller (simulated)"]


def test_context_manager_closes_transport_on_exit():
    transport = SimulatedTransport()
    with Controller(transport):
        pass
    # SimulatedTransport.close() clears its queue; reading afterwards
    # returns "" immediately rather than any stale banner/ok data.
    assert transport.read_line(timeout=0.05) == ""


def test_context_manager_closes_transport_even_on_exception():
    transport = SimulatedTransport()
    with pytest.raises(ValueError):
        with Controller(transport):
            raise ValueError("boom")
    assert transport.read_line(timeout=0.05) == ""


# -- reset_input_buffer ---------------------------------------------------------


def test_reset_input_buffer_discards_unread_transport_output():
    transport = SimulatedTransport()
    ctrl = Controller(transport)
    ctrl.open()
    # A command whose response was never read by the controller (e.g. sent
    # with wait_for_ok=False and never drained) -- represented here by
    # writing directly to the transport, bypassing Controller.execute.
    transport.write_line("G90")
    ctrl.reset_input_buffer()

    assert transport.read_line(timeout=0.05) == ""


# -- _read_response: timeout and NOT-ok branches -------------------------------


def test_execute_raises_transport_error_when_controller_never_responds():
    transport = SimulatedTransport()
    ctrl = Controller(transport, timeout=0.05)
    ctrl.open()
    transport.write_line = lambda line: None  # controller silently drops the command

    with pytest.raises(TransportError, match="timed out"):
        ctrl.report_position()


def test_execute_raises_mapped_controller_error_on_not_ok_response():
    transport = SimulatedTransport()
    ctrl = Controller(transport)
    ctrl.open()
    transport._queue.append("NOT ok (axis Z not homed)")

    with pytest.raises(AxisNotHomedError) as exc_info:
        ctrl.report_position()

    assert exc_info.value.axis == "Z"
    assert exc_info.value.response.status == "NOT ok (axis Z not homed)"
    assert exc_info.value.response.ok is False


# -- probe(): mode variants ------------------------------------------------------


def test_probe_default_mode_reports_contact_at_configured_position():
    transport = SimulatedTransport(probe_contact={"X": 5000})
    ctrl = Controller(transport)
    ctrl.open()
    ctrl.home(AxisId.X)

    result = ctrl.probe(AxisId.X, target=10000)  # mode defaults to TOWARD_OR_FAIL

    assert result.contacted is True
    assert result.positions[AxisId.X] == 5000
    assert result.positions[AxisId.Y] == -1  # unhomed axis: simulator's sentinel


def test_probe_toward_mode_no_contact_when_target_not_reached():
    transport = SimulatedTransport(probe_contact={"X": 50000})
    ctrl = Controller(transport)
    ctrl.open()
    ctrl.home(AxisId.X)

    result = ctrl.probe(AxisId.X, target=1000, mode=cmd.ProbeMode.TOWARD)

    assert result.contacted is False


def test_probe_away_mode_never_reports_contact():
    transport = SimulatedTransport(probe_contact={"X": 5000})
    ctrl = Controller(transport)
    ctrl.open()
    ctrl.home(AxisId.X)

    result = ctrl.probe(AxisId.X, target=0, mode=cmd.ProbeMode.AWAY_OR_FAIL)

    assert result.contacted is False


# -- measure_distance() ----------------------------------------------------------


def test_measure_distance_parses_configured_reading():
    transport = SimulatedTransport(ultrasonic_mm=42.5)
    ctrl = Controller(transport)
    ctrl.open()

    result = ctrl.measure_distance(AxisId.Z)

    assert result.z_mm == 42.5
    assert result.x_mm is None
    assert result.y_mm is None


def test_measure_distance_returns_all_none_when_no_echo_configured():
    transport = SimulatedTransport()  # ultrasonic_mm defaults to None
    ctrl = Controller(transport)
    ctrl.open()

    assert ctrl.measure_distance(AxisId.Z) == DistanceResult(None, None, None)


# -- set_hard_limits / emergency_stop / quick_stop: silent commands ----------


def test_set_hard_limits_sends_silent_command_without_waiting():
    sent = []
    transport = SimulatedTransport()
    ctrl = Controller(transport, on_send=lambda line, command: sent.append(line))
    ctrl.open()

    assert ctrl.set_hard_limits({AxisId.X: 500_000}) is None
    assert sent == ["M201 X500000"]


def test_emergency_stop_sends_m112_without_waiting_for_ack():
    sent = []
    transport = SimulatedTransport()
    ctrl = Controller(transport, on_send=lambda line, command: sent.append(line))
    ctrl.open()

    ctrl.emergency_stop()

    assert sent == ["M112"]


def test_quick_stop_sends_m410_without_waiting_for_ack():
    sent = []
    transport = SimulatedTransport()
    ctrl = Controller(transport, on_send=lambda line, command: sent.append(line))
    ctrl.open()

    ctrl.quick_stop()

    assert sent == ["M410"]


def test_quick_stop_halts_in_flight_linear_motion():
    transport = SimulatedTransport(axis_limits={"X": 500_000})
    ctrl = Controller(transport)
    ctrl.open()
    ctrl.home(AxisId.X)
    ctrl.linear_move({AxisId.X: 100_000}, feed=1000, wait_for_ok=False)

    ctrl.quick_stop()  # freezes the axis wherever the interpolated move had reached

    pos = ctrl.report_position()
    assert 0 <= pos[AxisId.X] < 100_000
