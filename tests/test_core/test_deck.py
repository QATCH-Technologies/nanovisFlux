import pytest

from src.core.deck import Deck, DeckLocation, build_grid_layout

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


def test_build_grid_layout_slot_count():
    slots = build_grid_layout(rows=4, cols=3, slot_width_mm=128.0, slot_depth_mm=86.0)
    assert len(slots) == 12
    assert {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "trash"} == set(slots.keys())


def test_build_grid_layout_trash_defaults_to_top_right():
    slots = build_grid_layout(rows=4, cols=3, slot_width_mm=128.0, slot_depth_mm=86.0)
    trash = slots["trash"]
    assert trash.is_trash
    assert trash.x_offset_mm == 2 * 128.0
    assert trash.y_offset_mm == 3 * 86.0
    assert all(not slot.is_trash for slot_id, slot in slots.items() if slot_id != "trash")


def test_build_grid_layout_numbering_is_row_major_from_bottom_left():
    slots = build_grid_layout(rows=4, cols=3, slot_width_mm=128.0, slot_depth_mm=86.0)
    assert (slots["1"].x_offset_mm, slots["1"].y_offset_mm) == (0.0, 0.0)
    assert (slots["3"].x_offset_mm, slots["3"].y_offset_mm) == (256.0, 0.0)
    assert (slots["4"].x_offset_mm, slots["4"].y_offset_mm) == (0.0, 86.0)


def test_build_grid_layout_custom_trash_position():
    slots = build_grid_layout(
        rows=2, cols=2, slot_width_mm=100.0, slot_depth_mm=100.0, trash_position=(0, 0)
    )
    assert slots["trash"].x_offset_mm == 0.0
    assert slots["trash"].y_offset_mm == 0.0
    assert set(slots.keys()) == {"1", "2", "3", "trash"}


def test_build_grid_layout_explicit_pitch_adds_gaps():
    slots = build_grid_layout(
        rows=1, cols=3, slot_width_mm=100.0, slot_depth_mm=100.0, x_pitch_mm=110.0
    )
    assert slots["2"].x_offset_mm == 110.0


def test_deck_standard_grid_resolves_like_from_config():
    deck = Deck.standard_grid(rows=4, cols=3, slot_width_mm=128.0, slot_depth_mm=86.0)
    location = DeckLocation(slot_id="5", x_mm=1.0, y_mm=1.0, z_mm=1.0)
    resolved = deck.resolve_mm(location)
    assert resolved == {"X": 128.0 + 1.0, "Y": 86.0 + 1.0, "Z": 1.0}


def test_deck_trash_slot_ids():
    deck = Deck.standard_grid(rows=4, cols=3, slot_width_mm=128.0, slot_depth_mm=86.0)
    assert deck.trash_slot_ids() == ["trash"]


def test_build_grid_layout_gap_mm_adds_to_pitch():
    slots = build_grid_layout(rows=1, cols=3, slot_width_mm=100.0, slot_depth_mm=100.0, gap_mm=5.0)
    assert slots["1"].x_offset_mm == 0.0
    assert slots["2"].x_offset_mm == 105.0


def test_build_grid_layout_explicit_pitch_overrides_gap_mm():
    slots = build_grid_layout(
        rows=1, cols=3, slot_width_mm=100.0, slot_depth_mm=100.0, gap_mm=5.0, x_pitch_mm=200.0
    )
    assert slots["2"].x_offset_mm == 200.0


def test_build_grid_layout_trash_can_have_its_own_footprint():
    slots = build_grid_layout(
        rows=2,
        cols=2,
        slot_width_mm=100.0,
        slot_depth_mm=80.0,
        gap_mm=5.0,
        trash_width_mm=170.0,
        trash_depth_mm=164.0,
    )
    trash = slots["trash"]
    assert trash.width_mm == 170.0
    assert trash.depth_mm == 164.0
    # trash still sits at its cell's grid origin -- only its footprint grows
    assert trash.x_offset_mm == 1 * (100.0 + 5.0)
    assert trash.y_offset_mm == 1 * (80.0 + 5.0)
    # non-trash slots are unaffected
    assert slots["1"].width_mm == 100.0
    assert slots["1"].depth_mm == 80.0


def test_build_grid_layout_trash_defaults_to_standard_footprint():
    slots = build_grid_layout(rows=2, cols=2, slot_width_mm=100.0, slot_depth_mm=80.0)
    assert slots["trash"].width_mm == 100.0
    assert slots["trash"].depth_mm == 80.0
