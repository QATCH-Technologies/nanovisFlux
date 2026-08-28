"""
Base abstraction for tools attachable to robot mounts.

This module defines the :class:`Tool` base class, which provides the common
lifecycle and mount-association interface for hardware tools such as
pipettes, touch probes, grippers, and cameras.

Concrete tools can subclass :class:`Tool` to add tool-specific behavior
without requiring changes to the robot, mount, or motion-control layers.
The base class tracks the mount and robot to which a tool is currently
attached and provides lifecycle hooks for attachment and detachment.
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from motion import Mount
    from robot import Robot


class Tool(ABC):
    """Define the base interface for tools attachable to robot mounts.

    `Tool` is the extension point for hardware that can be mounted to a
    robot carriage. Concrete subclasses can implement tool-specific behavior
    while relying on the common attachment lifecycle provided here.

    A tool may be associated with both its physical mount and the owning
    :class:`Robot` while attached. These references are cleared when the tool
    is detached.

    Subclasses can override :meth:`uses_plunger` when they require control of
    the mount's plunger axis.

    Attributes:
        name: Human-readable or registry identifier for the tool.
        mount: The mount to which the tool is currently attached, or `None`
            when detached.
    """

    name: str = "tool"

    def __init__(self):
        """Initialize a detached tool.

        The tool starts without an associated mount or robot. These associations
        are established by :meth:`on_attach`.
        """
        self._mount: Mount | None = None
        self._robot: Robot | None = None

    def uses_plunger(self) -> bool:
        """Indicate whether the tool uses the mount's plunger axis.

        The default implementation identifies the tool as not requiring plunger
        control.

        Returns:
            `True` if the tool drives the mount's plunger axis; otherwise
            `False`.
        """
        return False

    def on_attach(self, mount, robot) -> None:
        """Associate the tool with a mount and robot.

        This lifecycle hook is called after the tool has been attached to a mount.
        Subclasses may override this method to perform additional initialization,
        but should preserve the base associations when appropriate.

        Args:
            mount: Mount to which the tool has been attached.
            robot: Robot instance managing the mount.
        """
        self._mount = mount
        self._robot = robot

    def on_detach(self) -> None:
        """Detach the tool from its current mount and robot.

        Clears the internal mount and robot associations. Subclasses may override
        this hook to perform tool-specific cleanup.
        """
        self._mount = None
        self._robot = None

    @property
    def mount(self):
        """Return the mount currently associated with the tool.

        Returns:
            The attached mount, or `None` when the tool is detached.
        """
        return self._mount
