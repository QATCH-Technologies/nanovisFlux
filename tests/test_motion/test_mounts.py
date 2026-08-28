"""Mount (src/motion/mounts.py): the LEFT/RIGHT vertical and plunger axis
mappings are exercised indirectly elsewhere (e.g. Pipette/Probe wiring
tests), but REAR -- the fixed sensor mount with no independent vertical or
plunger axis -- is not, so both properties are covered directly here for all
three MountSide values. attach()/detach() tool-lifecycle behavior is also
covered directly since nothing else in the suite exercises it."""
from src.core import AxisId, MountSide
from src.motion.mounts import Mount


def test_left_mount_axes():
    mount = Mount(MountSide.LEFT)
    assert mount.vertical is AxisId.Z
    assert mount.plunger is AxisId.B


def test_right_mount_axes():
    mount = Mount(MountSide.RIGHT)
    assert mount.vertical is AxisId.A
    assert mount.plunger is AxisId.C


def test_rear_mount_has_no_vertical_or_plunger_axis():
    """The rear mount is fixed to the gantry frame -- it moves only with X/Y
    and has no dedicated vertical or plunger axis of its own."""
    mount = Mount(MountSide.REAR)
    assert mount.vertical is None
    assert mount.plunger is None


def test_mount_starts_with_no_tool_attached():
    mount = Mount(MountSide.LEFT)
    assert mount.tool is None


def test_attach_sets_the_mount_tool():
    mount = Mount(MountSide.LEFT)
    tool = object()

    mount.attach(tool)

    assert mount.tool is tool


def test_attach_replaces_a_previously_attached_tool():
    mount = Mount(MountSide.LEFT)
    old_tool = object()
    new_tool = object()
    mount.attach(old_tool)

    mount.attach(new_tool)

    assert mount.tool is new_tool


def test_detach_returns_the_previous_tool_and_leaves_the_mount_empty():
    mount = Mount(MountSide.RIGHT)
    tool = object()
    mount.attach(tool)

    detached = mount.detach()

    assert detached is tool
    assert mount.tool is None


def test_detach_with_no_tool_attached_returns_none_and_stays_empty():
    mount = Mount(MountSide.REAR)

    detached = mount.detach()

    assert detached is None
    assert mount.tool is None
