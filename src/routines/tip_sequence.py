from __future__ import annotations
from .location import WellLocation

_ROW_LETTERS = "ABCDEFGHIJKLMNOP"


class TipSequence:
    """Hands out successive tip wells from a rack, in the rack's own
    natural fill order (row A left-to-right, then row B, ...), so a routine
    can ask for "the next tip" instead of hand-listing every well name.

    Built from just ``rows``/``cols`` (a property of the rack type, e.g. 8x12
    for a 96-tip rack) rather than a placed ``Labware`` -- like every other
    Location in this package, a TipSequence is resolved against the robot
    only when a step actually runs, so a Routine can be built (and its tips
    handed out) before a robot exists.
    """
    def __init__(self, labware: str, *, rows: int = 8, cols: int = 12, start: str = "A1"):
        self.labware = labware
        self._names = [f"{_ROW_LETTERS[r]}{c + 1}" for r in range(rows) for c in range(cols)]
        try:
            self._i = self._names.index(start)
        except ValueError:
            raise ValueError(f"{start!r} is not a well in an {rows}x{cols} rack") from None

    def __iter__(self) -> "TipSequence":
        return self

    def __next__(self) -> WellLocation:
        if self._i >= len(self._names):
            raise StopIteration(f"tip rack {self.labware!r} is out of tips")
        where = WellLocation(self.labware, self._names[self._i], ref="top")
        self._i += 1
        return where

    def remaining(self) -> int:
        return len(self._names) - self._i
