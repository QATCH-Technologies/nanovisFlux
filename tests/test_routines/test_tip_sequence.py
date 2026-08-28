"""TipSequence: row-major well allocation for a tip rack, independent of any
placed labware instance (see tip_sequence.py's own module docstring). Covers
iteration order, an arbitrary starting well, exhaustion (StopIteration), the
invalid-start ValueError, and remaining()'s bookkeeping."""

from __future__ import annotations

import pytest

from src.routines.location import WellLocation
from src.routines.tip_sequence import TipSequence


def test_default_rack_starts_at_a1_in_row_major_order():
    seq = TipSequence("tips_300")

    assert next(seq) == WellLocation("tips_300", "A1", ref="top")
    assert next(seq) == WellLocation("tips_300", "A2", ref="top")


def test_row_major_order_wraps_to_next_row():
    seq = TipSequence("tips", rows=2, cols=3)

    names = [next(seq).well for _ in range(6)]

    assert names == ["A1", "A2", "A3", "B1", "B2", "B3"]


def test_iter_returns_the_same_sequence_instance():
    seq = TipSequence("tips", rows=1, cols=2)
    assert iter(seq) is seq


def test_start_at_an_arbitrary_well_skips_earlier_wells():
    seq = TipSequence("tips", rows=2, cols=2, start="B1")

    assert next(seq) == WellLocation("tips", "B1", ref="top")
    assert next(seq) == WellLocation("tips", "B2", ref="top")


def test_start_well_not_found_raises_value_error():
    with pytest.raises(ValueError, match=r"'Z9' is not a well in an 1x2 rack"):
        TipSequence("tips", rows=1, cols=2, start="Z9")


def test_start_well_out_of_range_for_rack_dimensions_raises_value_error():
    # "B1" is a real well name, just not one that exists in a single-row rack.
    with pytest.raises(ValueError, match="is not a well"):
        TipSequence("tips", rows=1, cols=4, start="B1")


def test_remaining_counts_down_as_wells_are_consumed():
    seq = TipSequence("tips", rows=1, cols=3)

    assert seq.remaining() == 3
    next(seq)
    assert seq.remaining() == 2
    next(seq)
    next(seq)
    assert seq.remaining() == 0


def test_remaining_reflects_a_non_default_start_position():
    seq = TipSequence("tips", rows=2, cols=2, start="B1")  # names: A1,A2,B1,B2

    assert seq.remaining() == 2


def test_stop_iteration_once_rack_is_exhausted():
    seq = TipSequence("tips", rows=1, cols=2)
    next(seq)
    next(seq)

    with pytest.raises(StopIteration, match=r"tip rack 'tips' is out of tips"):
        next(seq)


def test_stop_iteration_is_permanent_once_exhausted():
    seq = TipSequence("tips", rows=1, cols=1)
    next(seq)
    with pytest.raises(StopIteration):
        next(seq)
    # calling next() again on an already-exhausted sequence keeps raising,
    # rather than resetting or going negative.
    with pytest.raises(StopIteration):
        next(seq)
    assert seq.remaining() == 0


def test_iterating_with_a_for_loop_yields_every_well_exactly_once():
    seq = TipSequence("tips", rows=1, cols=4)

    wells = [loc.well for loc in seq]

    assert wells == ["A1", "A2", "A3", "A4"]
