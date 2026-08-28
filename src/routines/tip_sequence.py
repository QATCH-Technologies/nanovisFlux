"""Sequential tip-rack well allocation for robot routines.

This module provides :class:`TipSequence`, an iterator that hands out
successive :class:`WellLocation` objects for the wells of a tip rack. Wells
are generated in the rack's natural row-major fill order, proceeding from
left to right across each row before advancing to the next row.

A sequence is defined by the rack dimensions and labware name rather than by
a placed labware instance. This keeps tip allocation independent of the
robot's runtime configuration: routines can construct and consume a
`TipSequence` before a robot exists, while the resulting
:class:`WellLocation` objects defer deck-coordinate resolution until
execution.

The sequence can optionally begin at any valid well, making it possible to
resume allocation from a known position within a rack. The
:meth:`TipSequence.remaining` method provides a lightweight way to inspect
how many tip positions remain unconsumed.
"""

from __future__ import annotations

from .location import WellLocation

_ROW_LETTERS = "ABCDEFGHIJKLMNOP"


class TipSequence:
    """Generate successive tip-well locations in a rack's natural fill order.

    A tip sequence provides an iterator-based abstraction for consuming tip
    wells without requiring a routine to explicitly enumerate each well. Wells
    are generated in row-major order, proceeding left-to-right across each
    row before advancing to the next row.

    The sequence is defined from the rack's dimensions rather than a placed
    labware instance. Consequently, it can be constructed before a robot
    exists and produces :class:`WellLocation` objects whose actual deck
    coordinates are resolved only when the corresponding step executes.

    Attributes:
        labware: Name identifying the tip-rack labware used when resolving
            generated well locations.
    """

    def __init__(
        self,
        labware: str,
        *,
        rows: int = 8,
        cols: int = 12,
        start: str = "A1",
    ):
        """Initialize a tip sequence.

        Wells are generated in row-major order according to the specified rack
        dimensions, beginning at `start`. The starting well itself is included
        as the first well returned by the iterator.

        Args:
            labware: Name identifying the tip-rack labware.
            rows: Number of rows in the rack. Defaults to 8.
            cols: Number of columns in the rack. Defaults to 12.
            start: Well name at which iteration should begin. Defaults to
                `"A1"`.

        Raises:
            ValueError: If `start` does not correspond to a well within the
                specified rack dimensions.
        """
        self.labware = labware
        self._names = [f"{_ROW_LETTERS[r]}{c + 1}" for r in range(rows) for c in range(cols)]
        try:
            self._i = self._names.index(start)
        except ValueError:
            raise ValueError(f"{start!r} is not a well in an {rows}x{cols} rack") from None

    def __iter__(self) -> TipSequence:
        """Return the sequence iterator.

        Returns:
            TipSequence: This sequence instance, which maintains its own
            consumption state.
        """
        return self

    def __next__(self) -> WellLocation:
        """Return the next available tip-well location.

        Wells are returned in the sequence's configured row-major fill order.
        Each returned location references the top of the corresponding well,
        making it suitable for tip pickup operations.

        Returns:
            WellLocation: Location representing the next tip well in the rack.

        Raises:
            StopIteration: If all wells in the sequence have already been
                consumed.
        """
        if self._i >= len(self._names):
            raise StopIteration(f"tip rack {self.labware!r} is out of tips")
        where = WellLocation(self.labware, self._names[self._i], ref="top")
        self._i += 1
        return where

    def remaining(self) -> int:
        """Return the number of unconsumed tip wells.

        Returns:
            int: Number of wells remaining in the sequence, including the current
            next well.
        """
        return len(self._names) - self._i
