"""SimulatedTransport protocol coverage not already exercised indirectly
through tests/test_robot/*.py and tests/test_control/test_jog.py (which
drive G90/G91/G28/G0/G1/M114 extensively via Robot/JogController). This
file targets what's still untested at the SimulatedTransport level itself:
queue lifecycle (open/close/reset_input_buffer), read_line's idle/timeout
paths, the G38 probe-cycle branches (contact vs. no-contact, TOWARD vs.
AWAY modes, an axis with no configured contact point), and the M911/M412/
silent-command/unrecognized-command branches of _handle.

Note: SimulatedTransport._prb_line only ever reports X, Y, and A axis
positions (not Z), regardless of which axis was actually probed -- that's
an existing quirk of the simulator's response format, not a test bug, so
probe tests below probe the A axis to see the reported value change."""

from src.transport.simulated import SimulatedTransport


def _opened(**kwargs) -> SimulatedTransport:
    t = SimulatedTransport(**kwargs)
    t.open()
    t.read_line()  # startup banner
    t.read_line()  # "ok"
    return t


# -- queue lifecycle: open / close / reset_input_buffer ---------------------


def test_probe_contact_constructor_arg_merges_with_defaults():
    t = SimulatedTransport(probe_contact={"A": 999})
    assert t.probe_contact == {"Z": 120000, "A": 999}  # Z default kept, A overridden


def test_close_discards_any_queued_responses():
    t = SimulatedTransport()
    t.open()  # queues the startup banner + "ok" -- never read

    t.close()

    assert t.read_line(timeout=0) == ""  # discarded, not just already consumed


def test_reset_input_buffer_discards_queued_responses():
    t = _opened()
    t.write_line("G90")  # queues "Absolute mode set." + "ok"

    t.reset_input_buffer()

    assert t.read_line(timeout=0) == ""


# -- read_line idle / timeout behavior ---------------------------------------


def test_read_line_returns_empty_immediately_when_nothing_queued_or_moving():
    t = _opened()
    assert t.read_line() == ""  # no timeout given, no motion in flight -- must not hang


def test_read_line_times_out_while_a_move_is_still_in_flight():
    t = _opened(axis_limits={"X": 10_000_000})
    t.write_line("G1 X1000000 F1")  # feed=1 usteps/s: nowhere near done within this test

    result = t.read_line(timeout=0.02)

    assert result == ""  # deadline expired; the move's deferred "ok" hasn't arrived yet


# -- G38 probe cycle ----------------------------------------------------------


def test_g38_toward_registers_contact_when_target_reaches_the_contact_point():
    t = _opened(probe_contact={"A": 5000}, axis_limits={"A": 500_000})
    t.write_line("G28 A")
    t.read_line()  # "Homed A."
    t.read_line()  # "ok"

    t.write_line("G38.2 A10000")  # target overshoots the configured contact point

    assert t.read_line() == "[PRB:-1,-1,5000:1]"  # X/Y unhomed -> -1, A stopped AT contact
    assert t.read_line() == "ok"


def test_g38_toward_reaches_target_when_contact_point_not_reached():
    t = _opened(probe_contact={"A": 5000}, axis_limits={"A": 500_000})
    t.write_line("G28 A")
    t.read_line()
    t.read_line()

    t.write_line("G38.3 A1000")  # target falls short of the contact point

    assert t.read_line() == "[PRB:-1,-1,1000:0]"  # stops at the commanded target, no contact
    assert t.read_line() == "ok"


def test_g38_away_mode_ignores_configured_contact_point():
    """G38.4/.5 probe AWAY from a surface -- the TOWARD-only contact check
    must not fire even when the target numerically overshoots the
    configured contact point."""
    t = _opened(probe_contact={"A": 5000}, axis_limits={"A": 500_000})
    t.write_line("G28 A")
    t.read_line()
    t.read_line()

    t.write_line("G38.5 A50000")  # far past "contact" at 5000, but AWAY mode

    assert t.read_line() == "[PRB:-1,-1,50000:0]"  # reached the commanded target directly
    assert t.read_line() == "ok"


def test_g38_axis_with_no_configured_contact_point_never_registers_contact():
    t = _opened(axis_limits={"X": 500_000})  # default probe_contact has no "X" entry

    t.write_line("G38.2 X5000")

    assert t.read_line() == "[PRB:-1,-1,-1:0]"  # X isn't even reported; no contact possible
    assert t.read_line() == "ok"


def test_g38_clears_in_flight_motion_and_its_pending_completion():
    """G38 takes over outright, same as G28/M410 -- any move already in
    flight must be abandoned, and its deferred completion 'ok' must never
    show up later and get mistaken for a response to a later command."""
    t = _opened(axis_limits={"X": 10_000_000, "A": 500_000})
    t.write_line("G1 X1000000 F1")  # feed=1: guaranteed still in flight
    assert t.read_line(timeout=0) == ""  # no "ok" yet -- move hasn't completed

    t.write_line("G38.2 A100")

    assert t.read_line() == "[PRB:-1,-1,-1:0]"  # A unhomed here -- still reports -1, per convention
    assert t.read_line() == "ok"
    assert t.read_line(timeout=0) == ""  # the X move's completion "ok" never arrives


# -- M911 / M412 / silent / unrecognized commands ----------------------------


def test_m911_reports_safety_guards_off():
    t = _opened()
    t.write_line("M911")

    assert t.read_line() == "Movement safety guards OFF."
    assert t.read_line() == "ok"


def test_m412_reports_configured_ultrasonic_distance_only_when_z_queried():
    t = _opened(ultrasonic_mm=42.5)

    t.write_line("M412 Z")
    assert t.read_line() == "[RNG:-1,-1,42.5]"
    assert t.read_line() == "ok"

    t.write_line("M412 X")  # "Z" not present in the command -> reported as -1
    assert t.read_line() == "[RNG:-1,-1,-1]"
    assert t.read_line() == "ok"


def test_m412_reports_no_reading_when_ultrasonic_not_configured():
    t = _opened()  # ultrasonic_mm defaults to None

    t.write_line("M412 Z")

    assert t.read_line() == "[RNG:-1,-1,-1]"
    assert t.read_line() == "ok"


def test_silent_commands_produce_no_response_at_all():
    t = _opened()

    t.write_line("M201 X500")

    assert t.read_line(timeout=0) == ""  # not even a bare "ok" -- fully silent


def test_unrecognized_command_returns_a_bare_ok():
    t = _opened()

    t.write_line("M999")

    assert t.read_line() == "ok"
