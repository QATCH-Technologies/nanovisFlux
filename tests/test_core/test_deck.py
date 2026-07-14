import pytest

from src.core.deck import Deck, DeckLocation

LAYOUT = {
    "slots": {
        "1": {"x_offset_mm": 0.0, "y_offset_mm": 0.0, "z_offset_mm": 0.0},
        "2": {"x_offset_mm": 132.0, "y_offset_mm": 0.0, "z_offset_mm": 0.0},
    }
}


def test_resolve_mm_at_slot_origin():
    deck = Deck.from_config(LAYOUT)
    location = DeckLocation(slot_id="1", x_mm=10.0, y_mm=5.0, z_mm=2.0)
    assert deck.resolve_mm(location) == {"X": 10.0, "Y": 5.0, "Z": 2.0}


def test_resolve_mm_applies_slot_offset():
    deck = Deck.from_config(LAYOUT)
    location = DeckLocation(slot_id="2", x_mm=10.0, y_mm=5.0, z_mm=2.0)
    assert deck.resolve_mm(location) == {"X": 142.0, "Y": 5.0, "Z": 2.0}


def test_get_slot_unknown_raises():
    deck = Deck.from_config(LAYOUT)
    with pytest.raises(KeyError):
        deck.get_slot("99")


def test_resolve_mm_unknown_slot_raises():
    deck = Deck.from_config(LAYOUT)
    with pytest.raises(KeyError):
        deck.resolve_mm(DeckLocation(slot_id="99"))
