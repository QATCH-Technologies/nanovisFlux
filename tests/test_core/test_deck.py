"""Deck calibration-mark geometry: a slot's corner, inset inward by a fixed
mm offset, is what deck.calibration_marks / the calibration dialog treat as
a fixed, known reference point (see deck.deck.inset_corner_point and
configs/deck.yaml's deck.calibration_marks comment)."""
import pytest

from src.config.loader import build_deck
from src.deck import Corner, Slot, corner_point, inset_corner_point
from src.geometry import DeckPoint

#: The 8 confirmed marks from configs/deck.yaml's deck.calibration_marks,
#: using its own slot origins/sizes -- caliper-measured 127.85x85.9mm
#: slots, 137x95mm pitch (4.5mm separators on each side; supersedes an
#: earlier rough 123x81mm/128x86 estimate that was off by ~5-6%) --
#: (slot_x, slot_y, corner) -> expected mark (x, y), each 12mm/9mm inward.
_CONFIRMED_MARKS = [
    ("1",  (0, 0),         Corner.FRONT_LEFT,  (12, 9)),
    ("3",  (274.0, 0),     Corner.FRONT_RIGHT, (389.85, 9)),
    ("4",  (0, 95.0),      Corner.FRONT_LEFT,  (12, 104.0)),
    ("6",  (274.0, 95.0),  Corner.FRONT_RIGHT, (389.85, 104.0)),
    ("7",  (0, 190.0),     Corner.REAR_LEFT,   (12, 266.9)),
    ("9",  (274.0, 190.0), Corner.REAR_RIGHT,  (389.85, 266.9)),
    ("10", (0, 285.0),     Corner.REAR_LEFT,   (12, 361.9)),
    ("11", (137.0, 285.0), Corner.REAR_RIGHT,  (252.85, 361.9)),
]


def _slot(name: str, origin_xy: tuple) -> Slot:
    return Slot(name=name, origin=DeckPoint(*origin_xy), size=(127.85, 85.9))


def test_corner_point_all_four_corners():
    slot = Slot(name="1", origin=DeckPoint(0, 0), size=(127.85, 85.9))
    assert corner_point(slot, Corner.FRONT_LEFT) == DeckPoint(0, 0)
    assert corner_point(slot, Corner.FRONT_RIGHT) == DeckPoint(127.85, 0)
    assert corner_point(slot, Corner.REAR_LEFT) == DeckPoint(0, 85.9)
    assert corner_point(slot, Corner.REAR_RIGHT) == DeckPoint(127.85, 85.9)


def test_corner_point_offset_origin():
    slot = Slot(name="6", origin=DeckPoint(274.0, 95.0), size=(127.85, 85.9))
    assert corner_point(slot, Corner.FRONT_RIGHT) == DeckPoint(401.85, 95.0)
    assert corner_point(slot, Corner.REAR_LEFT) == DeckPoint(274.0, 180.9)


def test_corner_point_requires_size():
    slot = Slot(name="x", origin=DeckPoint(0, 0))
    with pytest.raises(ValueError):
        corner_point(slot, Corner.FRONT_LEFT)


@pytest.mark.parametrize("name, origin_xy, corner, expected", _CONFIRMED_MARKS)
def test_inset_corner_point_matches_confirmed_marks(name, origin_xy, corner, expected):
    slot = _slot(name, origin_xy)
    mark = inset_corner_point(slot, corner, 12.0, 9.0)
    ex, ey = expected
    assert mark.x == pytest.approx(ex)
    assert mark.y == pytest.approx(ey)


def test_build_deck_calibration_marks_from_config():
    cfg = {
        "slots": [
            {"name": "1", "x": 0, "y": 0, "size": [127.85, 85.9]},
            {"name": "10", "x": 0, "y": 285.0, "size": [127.85, 85.9]},
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
    assert mark10.point.x == pytest.approx(12)
    assert mark10.point.y == pytest.approx(361.9)


def test_build_deck_without_calibration_marks_section():
    deck = build_deck({"slots": [{"name": "1", "x": 0, "y": 0, "size": [127.85, 85.9]}]})
    assert deck.calibration_marks == {}
