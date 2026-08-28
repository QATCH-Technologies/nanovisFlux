"""ControllerError hierarchy and map_error()'s reason-string classification.

map_error() inspects a raw controller failure reason (the text inside a
`NOT ok (...)` response, see responses.extract_reason) and picks the most
specific ControllerError subclass. Matching against known patterns
("not homed", "endstop", "serial pending", "null pointer", "too many axes")
is case-insensitive, but AxisNotHomedError's axis-name extraction re-splits
the *original* (non-lowered) reason on the literal lowercase substrings
"axis" and "not" -- so extraction itself is case-sensitive even though
classification is not. That quirk is asserted explicitly below rather than
silently assumed.
"""

from __future__ import annotations

import pytest

from src.protocol.errors import (
    AxisNotHomedError,
    ControllerError,
    EndstopError,
    ProbeError,
    TooManyAxesError,
    TransportError,
    map_error,
)
from src.protocol.responses import Response


# -- ControllerError base -----------------------------------------------------


def test_controller_error_stores_message_reason_and_response():
    resp = Response(ok=False, info=["a line"], status="NOT ok (boom)", reason="boom")
    err = ControllerError("boom", reason="boom", response=resp)

    assert str(err) == "boom"
    assert err.reason == "boom"
    assert err.response is resp


def test_controller_error_defaults_reason_and_response_to_none():
    err = ControllerError("generic failure")

    assert err.reason is None
    assert err.response is None


# -- plain subclasses ---------------------------------------------------------


@pytest.mark.parametrize(
    "exc_type", [TransportError, EndstopError, ProbeError, TooManyAxesError]
)
def test_plain_subclasses_are_controller_errors_with_no_extra_behavior(exc_type):
    err = exc_type("some message", reason="some reason")

    assert isinstance(err, ControllerError)
    assert isinstance(err, Exception)
    assert str(err) == "some message"
    assert err.reason == "some reason"


# -- AxisNotHomedError ---------------------------------------------------------


def test_axis_not_homed_error_sets_axis_message_and_reason():
    resp = Response(ok=False)
    err = AxisNotHomedError("Z", resp)

    assert err.axis == "Z"
    assert str(err) == "axis Z not homed"
    assert err.reason == "axis Z not homed"
    assert err.response is resp
    assert isinstance(err, ControllerError)


# -- map_error(): no reason ----------------------------------------------------


def test_map_error_none_reason_returns_generic_controller_error():
    err = map_error(None)

    assert type(err) is ControllerError
    assert str(err) == "command failed"
    assert err.reason is None
    assert err.response is None


def test_map_error_empty_string_reason_falls_back_like_none_for_message():
    # "" is falsy like None for the message fallback, but unlike None it is
    # still what gets stored on .reason (the "or" only guards the message).
    err = map_error("")

    assert type(err) is ControllerError
    assert str(err) == "command failed"
    assert err.reason == ""


# -- map_error(): axis-not-homed branch ---------------------------------------


def test_map_error_not_homed_extracts_axis_name_from_reason():
    err = map_error("axis Z not homed")

    assert isinstance(err, AxisNotHomedError)
    assert err.axis == "Z"


def test_map_error_not_homed_extracts_axis_from_surrounding_text():
    err = map_error("Error: axis A not homed, please home first")

    assert isinstance(err, AxisNotHomedError)
    assert err.axis == "A"


def test_map_error_not_homed_without_axis_prefix_defaults_to_question_mark():
    err = map_error("not homed")

    assert isinstance(err, AxisNotHomedError)
    assert err.axis == "?"


def test_map_error_not_homed_axis_extraction_is_case_sensitive():
    # Classification ("not homed" in r) is case-insensitive so this is still
    # an AxisNotHomedError, but the axis-name split looks for the literal
    # lowercase substrings "axis"/"not" in the *original* reason -- since
    # neither appears lowercase here, the whole reason string is used as the
    # "axis" rather than the intended "Z".
    err = map_error("AXIS Z NOT HOMED")

    assert isinstance(err, AxisNotHomedError)
    assert err.axis == "AXIS Z NOT HOMED"


def test_map_error_not_homed_preserves_response():
    resp = Response(ok=False, status="NOT ok (axis B not homed)")
    err = map_error("axis B not homed", resp)

    assert err.response is resp


# -- map_error(): endstop branch (endstop / serial pending / null pointer) ---


@pytest.mark.parametrize(
    "reason",
    [
        "Homing aborted: endstop not triggered",
        "serial pending",
        "null pointer",
    ],
)
def test_map_error_endstop_family_reasons(reason):
    err = map_error(reason)

    assert type(err) is EndstopError
    assert err.reason == reason


def test_map_error_endstop_branch_is_case_insensitive():
    err = map_error("ENDSTOP TIMEOUT")

    assert type(err) is EndstopError
    assert err.reason == "ENDSTOP TIMEOUT"  # original case preserved on .reason


# -- map_error(): too-many-axes branch ----------------------------------------


def test_map_error_too_many_axes():
    err = map_error("too many axes")

    assert type(err) is TooManyAxesError
    assert str(err) == "too many axes"


def test_map_error_too_many_axes_case_insensitive():
    err = map_error("Too Many Axes specified for probe")

    assert type(err) is TooManyAxesError
    assert err.reason == "Too Many Axes specified for probe"


# -- map_error(): fallback ------------------------------------------------------


def test_map_error_unrecognized_reason_falls_back_to_generic_controller_error():
    resp = Response(ok=False, status="NOT ok (unexpected controller fault)")
    err = map_error("unexpected controller fault", resp)

    assert type(err) is ControllerError
    assert str(err) == "unexpected controller fault"
    assert err.reason == "unexpected controller fault"
    assert err.response is resp
