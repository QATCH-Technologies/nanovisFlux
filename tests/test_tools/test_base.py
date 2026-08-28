"""Tool: the shared attach/detach lifecycle and default hook behavior that
every concrete tool (Pipette, TouchProbe, UltrasonicSensor) inherits.
`Tool` declares no abstract methods, so it is directly instantiable -- these
tests exercise the base class itself rather than a subclass."""

from unittest.mock import MagicMock

from src.core import MountSide
from src.motion.mounts import Mount
from src.tools import Tool


def test_tool_starts_detached():
    tool = Tool()
    assert tool.mount is None


def test_uses_plunger_defaults_to_false():
    assert Tool().uses_plunger() is False


def test_on_attach_associates_mount_and_robot():
    tool = Tool()
    mount = Mount(side=MountSide.LEFT)
    robot = MagicMock()

    tool.on_attach(mount, robot)

    assert tool.mount is mount
    assert tool._robot is robot


def test_on_detach_clears_mount_and_robot():
    tool = Tool()
    mount = Mount(side=MountSide.LEFT)
    robot = MagicMock()
    tool.on_attach(mount, robot)

    tool.on_detach()

    assert tool.mount is None
    assert tool._robot is None


def test_mount_property_reflects_reattachment():
    """The `mount` property must report whatever mount was most recently
    attached, not a value snapshotted at construction time."""
    tool = Tool()
    mount_a = Mount(side=MountSide.LEFT)
    mount_b = Mount(side=MountSide.RIGHT)

    tool.on_attach(mount_a, MagicMock())
    assert tool.mount is mount_a

    tool.on_attach(mount_b, MagicMock())
    assert tool.mount is mount_b
