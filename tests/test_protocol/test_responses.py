"""extract_reason/parse_position/parse_probe/parse_distance edge cases.

These parsers scan `info` lines gathered by Controller._read_response()
before a terminal `ok`/`NOT ok`. They are deliberately tolerant of
unrelated informational lines mixed in around the line of interest, and
fall back to `None` (or, for parse_position, an empty dict) rather than
raising when the expected `[PRB:...]`/`[RNG:...]`/`AXIS:VALUE` shape isn't
present -- these tests pin down that tolerant behavior line by line.
"""

from __future__ import annotations

from src.core import AxisId
from src.protocol.responses import (
    DistanceResult,
    Response,
    extract_reason,
    parse_distance,
    parse_position,
    parse_probe,
)


# -- extract_reason -------------------------------------------------------------


def test_extract_reason_returns_text_between_parens():
    assert extract_reason("NOT ok (axis Z not homed)") == "axis Z not homed"


def test_extract_reason_uses_first_open_and_last_close_paren():
    # A reason that itself contains parens should still come back whole,
    # since the first "(" and the *last* ")" bound the extracted text.
    assert extract_reason("NOT ok (bad target (300) for axis Z)") == "bad target (300) for axis Z"


def test_extract_reason_returns_none_when_no_parens_present():
    assert extract_reason("NOT ok") is None


def test_extract_reason_returns_none_when_only_open_paren_present():
    assert extract_reason("NOT ok (unterminated") is None


def test_extract_reason_returns_none_when_only_close_paren_present():
    assert extract_reason("NOT ok unterminated)") is None


# -- parse_position ---------------------------------------------------------------


def test_parse_position_parses_axis_value_tokens():
    positions = parse_position([" X:100 Y:200 Z:300 A:-1 B:0 C:0"])

    assert positions == {
        AxisId.X: 100,
        AxisId.Y: 200,
        AxisId.Z: 300,
        AxisId.A: -1,
        AxisId.B: 0,
        AxisId.C: 0,
    }


def test_parse_position_ignores_lines_with_no_colon():
    assert parse_position(["OpenFlux OT-2 Stepper Controller (simulated)"]) == {}


def test_parse_position_skips_unknown_axis_letters():
    # "Q" is not a valid AxisId -- AxisId("Q") raises ValueError, which
    # parse_position swallows and skips rather than propagating.
    positions = parse_position(["X:100 Q:999"])

    assert positions == {AxisId.X: 100}


def test_parse_position_skips_tokens_with_non_integer_values():
    positions = parse_position(["X:100 Y:notanumber"])

    assert positions == {AxisId.X: 100}


def test_parse_position_skips_whitespace_tokens_without_a_colon():
    # A line that does contain ":" somewhere still has to skip any
    # individual token that itself lacks a colon (token.partition gives
    # sep == "" for those), rather than crashing on the missing value.
    positions = parse_position(["X:100 garbage Y:200"])

    assert positions == {AxisId.X: 100, AxisId.Y: 200}


def test_parse_position_merges_across_multiple_info_lines():
    positions = parse_position(["X:100", "Y:200"])

    assert positions == {AxisId.X: 100, AxisId.Y: 200}


def test_parse_position_empty_info_returns_empty_dict():
    assert parse_position([]) == {}


# -- parse_probe ------------------------------------------------------------------


def test_parse_probe_parses_contacted_result():
    result = parse_probe(["[PRB:1000,2000,3000:1]"])

    assert result.contacted is True
    assert result.positions == {AxisId.X: 1000, AxisId.Y: 2000, AxisId.A: 3000}


def test_parse_probe_parses_no_contact_result():
    result = parse_probe(["[PRB:1000,2000,3000:0]"])

    assert result.contacted is False


def test_parse_probe_ignores_surrounding_informational_lines():
    result = parse_probe(["ok so far", "[PRB:5,6,7:1]", "trailer"])

    assert result is not None
    assert result.positions == {AxisId.X: 5, AxisId.Y: 6, AxisId.A: 7}


def test_parse_probe_handles_fewer_than_three_coordinates():
    result = parse_probe(["[PRB:42:1]"])

    assert result.positions == {AxisId.X: 42}


def test_parse_probe_returns_none_when_no_prb_line_present():
    assert parse_probe(["some line", "ok"]) is None


def test_parse_probe_returns_none_for_empty_info():
    assert parse_probe([]) is None


def test_parse_probe_strips_surrounding_whitespace_on_the_line():
    result = parse_probe(["   [PRB:1,2,3:1]   "])

    assert result is not None
    assert result.contacted is True


# -- parse_distance ---------------------------------------------------------------


def test_parse_distance_parses_all_three_slots():
    result = parse_distance(["[RNG:10.5,20.0,30.25]"])

    assert result == DistanceResult(x_mm=10.5, y_mm=20.0, z_mm=30.25)


def test_parse_distance_converts_negative_sentinel_to_none():
    result = parse_distance(["[RNG:-1,-1,15.0]"])

    assert result == DistanceResult(x_mm=None, y_mm=None, z_mm=15.0)


def test_parse_distance_treats_missing_trailing_slots_as_unavailable():
    result = parse_distance(["[RNG:10.0]"])

    assert result == DistanceResult(x_mm=10.0, y_mm=None, z_mm=None)


def test_parse_distance_ignores_surrounding_informational_lines():
    result = parse_distance(["banner", "[RNG:1.0,2.0,3.0]", "ok"])

    assert result == DistanceResult(x_mm=1.0, y_mm=2.0, z_mm=3.0)


def test_parse_distance_returns_none_when_no_rng_line_present():
    assert parse_distance(["some other line"]) is None


def test_parse_distance_returns_none_for_empty_info():
    assert parse_distance([]) is None


# -- Response dataclass ---------------------------------------------------------


def test_response_info_default_is_not_shared_between_instances():
    a = Response(ok=True)
    b = Response(ok=True)
    a.info.append("line")

    assert b.info == []
