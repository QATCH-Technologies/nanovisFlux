import pytest

from src.core.offset import Offset, OffsetStack


def test_offset_apply():
    offset = Offset(name="mount", steps={"X": 100.0, "Y": 200.0})
    assert offset.apply({"X": 1.0, "Y": 2.0}) == {"X": 101.0, "Y": 202.0}


def test_offset_apply_handles_axes_only_present_on_one_side():
    offset = Offset(name="tip", steps={"Z": 5.0})
    assert offset.apply({"X": 1.0}) == {"X": 1.0, "Z": 5.0}


def test_offset_remove_is_inverse_of_apply():
    offset = Offset(name="mount", steps={"X": 100.0})
    original = {"X": 1.0, "Y": 2.0}
    assert offset.remove(offset.apply(original)) == original


def test_offset_stack_applies_in_order():
    stack = OffsetStack()
    stack.add(Offset(name="mount", steps={"X": 100.0}))
    stack.add(Offset(name="tip", steps={"X": 10.0, "Z": 5.0}))
    assert stack.apply({"X": 1.0}) == {"X": 111.0, "Z": 5.0}


def test_offset_stack_remove_is_inverse_of_apply():
    stack = OffsetStack()
    stack.add(Offset(name="mount", steps={"X": 100.0}))
    stack.add(Offset(name="tip", steps={"X": 10.0, "Y": 5.0}))
    original = {"X": 1.0, "Y": 2.0}
    assert stack.remove(stack.apply(original)) == original


def test_offset_stack_named_lookup():
    stack = OffsetStack()
    mount_offset = Offset(name="mount", steps={"X": 100.0})
    stack.add(mount_offset)
    assert stack.named("mount") is mount_offset
    with pytest.raises(KeyError):
        stack.named("labware")
