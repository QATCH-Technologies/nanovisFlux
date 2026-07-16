from src.core.mount import MountPosition


def test_gantry_mounts_are_not_fixed():
    assert not MountPosition.LEFT_PRIMARY.fixed()
    assert not MountPosition.LEFT_SECONDARY.fixed()
    assert not MountPosition.RIGHT_PRIMARY.fixed()
    assert not MountPosition.RIGHT_SECONDARY.fixed()


def test_frame_mounts_are_fixed():
    assert MountPosition.FRONT.fixed()
    assert MountPosition.REAR.fixed()
