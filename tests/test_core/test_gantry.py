import pytest

from src.core.gantry import Gantry
from src.core.mount import MountPosition


def test_new_gantry_has_all_positions_unmounted():
    gantry = Gantry()
    assert set(gantry.available_mounts()) == set(MountPosition)
    for position in MountPosition:
        assert not gantry.is_mounted(position)
        assert gantry.get(position) is None


def test_mount_and_get():
    gantry = Gantry()
    gantry.mount(MountPosition.LEFT_PRIMARY, "pipette")
    assert gantry.is_mounted(MountPosition.LEFT_PRIMARY)
    assert gantry.get(MountPosition.LEFT_PRIMARY) == "pipette"


def test_mount_rejects_already_occupied_position():
    gantry = Gantry()
    gantry.mount(MountPosition.LEFT_PRIMARY, "pipette")
    with pytest.raises(RuntimeError):
        gantry.mount(MountPosition.LEFT_PRIMARY, "touch_sensor")


def test_unmount_returns_and_clears_tool():
    gantry = Gantry()
    gantry.mount(MountPosition.REAR, "sensor")
    tool = gantry.unmount(MountPosition.REAR)
    assert tool == "sensor"
    assert not gantry.is_mounted(MountPosition.REAR)


def test_unmount_empty_position_raises():
    gantry = Gantry()
    with pytest.raises(RuntimeError):
        gantry.unmount(MountPosition.FRONT)


def test_restricting_available_mounts():
    gantry = Gantry(available_mounts=[MountPosition.LEFT_PRIMARY, MountPosition.RIGHT_PRIMARY])
    assert set(gantry.available_mounts()) == {MountPosition.LEFT_PRIMARY, MountPosition.RIGHT_PRIMARY}
    with pytest.raises(KeyError):
        gantry.mount(MountPosition.FRONT, "sensor")
