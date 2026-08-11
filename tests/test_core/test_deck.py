"""Deck calibration-mark geometry: a slot's corner, inset inward by a fixed
mm offset, is what deck.calibration_marks / the calibration dialog treat as
a fixed, known reference point (see deck.deck.inset_corner_point and
config/robot.example.yaml's deck.calibration_marks comment)."""
import pytest

from src.config.loader import build_deck
from src.deck import Corner, Slot, corner_point, inset_corner_point
from src.geometry import DeckPoint

#: The 8 confirmed marks from robot.example.yaml's deck.calibration_marks,
#: using its own slot origins/sizes (123x81mm slots, pitch 128x86) --
#: (slot_x, slot_y, corner) -> expected mark (x, y), each 12mm/9mm inward.
_CONFIRMED_MARKS = [
    ("1",  (0, 0),     Corner.FRONT_LEFT,  (12, 9)),
    ("3",  (256, 0),   Corner.FRONT_RIGHT, (367, 9)),
    ("4",  (0, 86),    Corner.FRONT_LEFT,  (12, 95)),
    ("6",  (256, 86),  Corner.FRONT_RIGHT, (367, 95)),
    ("7",  (0, 172),   Corner.REAR_LEFT,   (12, 244)),
    ("9",  (256, 172), Corner.REAR_RIGHT,  (367, 244)),
    ("10", (0, 258),   Corner.REAR_LEFT,   (12, 330)),
    ("11", (128, 258), Corner.REAR_RIGHT,  (239, 330)),
]


def _slot(name: str, origin_xy: tuple) -> Slot:
    return Slot(name=name, origin=DeckPoint(*origin_xy), size=(123.0, 81.0))


def test_corner_point_all_four_corners():
    slot = Slot(name="1", origin=DeckPoint(0, 0), size=(123.0, 81.0))
    assert corner_point(slot, Corner.FRONT_LEFT) == DeckPoint(0, 0)
    assert corner_point(slot, Corner.FRONT_RIGHT) == DeckPoint(123, 0)
    assert corner_point(slot, Corner.REAR_LEFT) == DeckPoint(0, 81)
    assert corner_point(slot, Corner.REAR_RIGHT) == DeckPoint(123, 81)


def test_corner_point_offset_origin():
    slot = Slot(name="6", origin=DeckPoint(256, 86), size=(123.0, 81.0))
    assert corner_point(slot, Corner.FRONT_RIGHT) == DeckPoint(379, 86)
    assert corner_point(slot, Corner.REAR_LEFT) == DeckPoint(256, 167)


def test_corner_point_requires_size():
    slot = Slot(name="x", origin=DeckPoint(0, 0))
    with pytest.raises(ValueError):
        corner_point(slot, Corner.FRONT_LEFT)


@pytest.mark.parametrize("name, origin_xy, corner, expected", _CONFIRMED_MARKS)
def test_inset_corner_point_matches_confirmed_marks(name, origin_xy, corner, expected):
    slot = _slot(name, origin_xy)
    mark = inset_corner_point(slot, corner, 12.0, 9.0)
    ex, ey = expected
    assert mark == DeckPoint(ex, ey)


def test_build_deck_calibration_marks_from_config():
    cfg = {
        "slots": [
            {"name": "1", "x": 0, "y": 0, "size": [123, 81]},
            {"name": "10", "x": 0, "y": 258, "size": [123, 81]},
        ],
        "calibration_marks": {
            "inset_mm": {"x": 12.0, "y": 9.0},
            "points": [
                {"name": "1", "slot": "1", "corner": "front_left"},
                {"name": "10", "slot": "10", "corner": "rear_left"},
            ],
        },
    }
    deck = build_deck(cfg)
    assert set(deck.calibration_marks) == {"1", "10"}
    mark1 = deck.calibration_marks["1"]
    assert mark1.slot == "1"
    assert mark1.corner is Corner.FRONT_LEFT
    assert mark1.point == DeckPoint(12, 9)
    mark10 = deck.calibration_marks["10"]
    assert mark10.point == DeckPoint(12, 330)


def test_build_deck_without_calibration_marks_section():
    deck = build_deck({"slots": [{"name": "1", "x": 0, "y": 0, "size": [123, 81]}]})
    assert deck.calibration_marks == {}
