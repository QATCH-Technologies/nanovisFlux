"""Executable steps for constructing and running robot routines.

This module defines the instruction-level building blocks used by
:class:`Routine` to describe robot operations. Each :class:`Step` represents
one ordered action, such as homing axes, moving to a semantic
:class:`Location`, manipulating tips, aspirating or dispensing liquid,
switching the active mount, pausing execution, or inserting a non-operative
comment.

Steps operate through the robot abstraction rather than directly managing
hardware details. Locations are resolved against the robot at execution time,
allowing routines to remain independent of specific deck coordinates and
labware placement.

Mount selection is threaded through routine execution by `Routine.run`.
Most steps operate on the currently active :class:`MountSide` and leave it
unchanged. :class:`SwitchMountStep` is the exception: it returns a new
:class:`MountSide`, causing subsequent steps to use that mount. This permits a
single routine to operate across multiple mounts while retaining a simple,
ordered execution model.

The step descriptions produced by :meth:`Step.describe` provide a
human-readable representation suitable for dry-run output, logging, and
routine inspection.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..core import AxisId, MountSide
from ..robot import Robot
from ..tools.tips import TipGeometry, TipPickup
from .location import Location


class Step:
    """Abstract base class for an executable routine instruction.

    A step represents one operation in a :class:`Routine`. Steps operate at
    the semantic deck-space level, using :class:`Location` objects for
    positions and delegating hardware-specific motion or tool operations to
    the robot.

    The `side` argument passed to :meth:`execute` represents the routine's
    currently active mount. Most steps use this mount and return `None`.
    :class:`SwitchMountStep` is the exception: it returns the newly selected
    :class:`MountSide`, which :class:`Routine.run` propagates to subsequent
    steps.

    Methods:
        execute: Execute the instruction against a robot.
        describe: Return a human-readable description of the instruction.
    """

    def execute(self, robot: Robot, side: MountSide) -> MountSide | None:
        """Execute the step against a robot.

        Args:
            robot: Robot instance against which the step is executed.
            side: Mount currently active for the routine.

        Returns:
            MountSide | None: Optional mount update. Returning a
            :class:`MountSide` changes the active mount for subsequent routine
            steps; returning `None` leaves it unchanged.

        Raises:
            NotImplementedError: Always raised by the base implementation.
                Concrete step subclasses must implement this method.
        """
        raise NotImplementedError

    def describe(self) -> str:
        """Return a human-readable description of the step.

        The base implementation uses the concrete step class name. Subclasses
        typically override this method with a more informative representation
        suitable for dry-run output and routine inspection.

        Returns:
            str: Human-readable description of the step.
        """
        return type(self).__name__


@dataclass
class HomeStep(Step):
    """Home one or more robot axes.

    An empty axis tuple requests homing of all axes. When specific axes are
    provided, only those axes are passed to the robot's homing operation.

    Attributes:
        axes: Tuple of axis objects to home. Defaults to an empty tuple,
            indicating that all axes should be homed.
    """

    axes: tuple[AxisId, ...] = ()

    def execute(self, robot: Robot, side: MountSide) -> None:
        """Home the configured robot axes.

        Args:
            robot: Robot instance whose axes should be homed.
            side: Currently active mount. Unused by this step.
        """
        robot.home(*self.axes)

    def describe(self) -> str:
        """Return a human-readable description of the homing operation.

        Returns:
            str: `"home all"` when no specific axes are configured, otherwise
            a space-separated list of the configured axis letters.
        """
        return "home " + (" ".join(a.letter for a in self.axes) or "all")


@dataclass
class MoveStep(Step):
    """Move the active mount to a resolved deck-space location.

    Attributes:
        where: Semantic location to resolve against the robot at execution
            time.
        feed: Optional movement feed rate passed to the robot's safe movement
            operation.
    """

    where: Location
    feed: int | None = None

    def execute(self, robot: Robot, side: MountSide) -> None:
        """Move the active mount to the configured location.

        The location is resolved against the current robot state immediately
        before the movement is issued.

        Args:
            robot: Robot instance used to resolve the location and perform the
                movement.
            side: Currently active mount that should perform the movement.
        """
        robot.safe_move_to(self.where.resolve(robot), side, feed=self.feed)

    def describe(self) -> str:
        """Return a human-readable description of the movement.

        Returns:
            str: Description identifying the destination location.
        """
        return f"move to {self.where}"


@dataclass
class SwitchMountStep(Step):
    """Switch the routine's active mount, optionally moving it to a location.

    The selected `mount` becomes the active mount for every subsequent step
    in the routine. If `where` is provided, the selected mount is also
    safely moved to that location as part of this step.

    This allows a single routine to transition between mounts without being
    permanently associated with a particular starting side. When `where` is
    omitted, the step changes only the active mount.

    Attributes:
        mount: Mount to make active after this step executes.
        where: Optional location to which the newly selected mount should be
            moved.
        feed: Optional movement feed rate used when `where` is provided.
    """

    mount: MountSide
    where: Location | None = None
    feed: int | None = None

    def execute(self, robot: Robot, side: MountSide) -> MountSide:
        """Optionally move to the target location and activate the selected mount.

        Args:
            robot: Robot instance used to resolve the location and perform the
                optional movement.
            side: Mount that is active before this step. It is not used to select
                the mount being activated.

        Returns:
            MountSide: The mount configured by :attr:`mount`, which becomes the
            active mount for subsequent routine steps.
        """
        if self.where is not None:
            robot.safe_move_to(self.where.resolve(robot), self.mount, feed=self.feed)
        return self.mount

    def describe(self) -> str:
        """Return a human-readable description of the mount switch.

        Returns:
            str: Description identifying the selected mount and, when configured,
            its destination location.
        """
        base = f"switch to {self.mount.value} mount"
        return f"{base}, move to {self.where}" if self.where is not None else base


@dataclass
class PickUpTipStep(Step):
    """Pick up a disposable tip from a specified rack location.

    The location is resolved at execution time to obtain the deck-space
    position of the tip. The tip geometry is then obtained from the robot's
    registered tip collection when available.

    Attributes:
        where: Location of the tip within the tip rack.
        tip: Key identifying the tip geometry in the robot's known tip
            geometries, or a tip object accepted directly by the robot.
        pickup: Tip-pickup configuration describing how the tool should engage
            the tip, such as pickup press or Z parameters.
    """

    where: Location
    tip: str | TipGeometry
    pickup: TipPickup

    def execute(self, robot: Robot, side: MountSide) -> None:
        """Pick up the specified tip using the active mount.

        Args:
            robot: Robot instance containing the active mount and tip geometry
                configuration.
            side: Currently active mount used to perform the pickup.
        """
        pip = robot.mounts[side].tool
        xy = self.where.resolve(robot)
        tip = robot.tips[self.tip] if hasattr(robot, "tips") else self.tip
        pip.pick_up_tip(xy, tip, self.pickup)  # type: ignore

    def describe(self) -> str:
        """Return a human-readable description of the tip pickup.

        Returns:
            str: Description identifying the tip and pickup location.
        """
        return f"pick up tip {self.tip} at {self.where}"


@dataclass
class DropTipStep(Step):
    """Drop the currently held tip at an optional location.

    If `where` is provided, the active mount is moved to the resolved
    location before the tip is ejected. When omitted, the tool's drop-tip
    operation determines the ejection location or behavior.

    Attributes:
        where: Optional location at which to drop the tip.
        eject_z_mm: Optional Z height, in millimeters, used for tip ejection.
    """

    where: Location | None = None
    eject_z_mm: float | None = None

    def execute(self, robot: Robot, side: MountSide) -> None:
        """Drop the currently attached tip using the active mount.

        Args:
            robot: Robot instance containing the active mount's tool.
            side: Currently active mount used to perform the tip drop.
        """
        pip = robot.mounts[side].tool
        xy = self.where.resolve(robot) if self.where else None
        pip.drop_tip(xy, self.eject_z_mm)  # type: ignore

    def describe(self) -> str:
        """Return a human-readable description of the tip drop.

        Returns:
            str: Description indicating a destination when one is configured.
        """
        return "drop tip" + (f" at {self.where}" if self.where else "")


@dataclass
class AspirateStep(Step):
    """Move to a location and aspirate a specified liquid volume.

    The destination is resolved at execution time, the active mount is safely
    moved there, and its tool performs the aspiration.

    Attributes:
        volume_ul: Volume to aspirate, in microliters.
        where: Location from which the liquid is aspirated.
        feed: Optional movement and aspiration feed rate passed to the robot
            and tool.
    """

    volume_ul: float
    where: Location
    feed: int | None = None

    def execute(self, robot: Robot, side: MountSide) -> None:
        """Move to the source location and aspirate liquid.

        Args:
            robot: Robot instance used for movement and aspiration.
            side: Currently active mount used for the operation.
        """
        robot.safe_move_to(self.where.resolve(robot), side, feed=self.feed)
        robot.mounts[side].tool.aspirate(self.volume_ul, feed=self.feed)  # type: ignore

    def describe(self) -> str:
        """Return a human-readable description of the aspiration.

        Returns:
            str: Description containing the volume and source location.
        """
        return f"aspirate {self.volume_ul} uL from {self.where}"


@dataclass
class DispenseStep(Step):
    """Move to a location and dispense liquid using the active tool.

    A `None` volume delegates the interpretation of the dispense amount to
    the underlying tool, typically representing dispensing all available
    liquid.

    Attributes:
        volume_ul: Volume to dispense, in microliters, or `None` to request
            the tool's all-liquid dispense behavior.
        where: Location into which the liquid is dispensed.
        feed: Optional movement and dispense feed rate.
    """

    volume_ul: float | None
    where: Location
    feed: int | None = None

    def execute(self, robot: Robot, side: MountSide) -> None:
        """Move to the destination location and dispense liquid.

        Args:
            robot: Robot instance used for movement and dispensing.
            side: Currently active mount used for the operation.
        """
        robot.safe_move_to(self.where.resolve(robot), side, feed=self.feed)
        robot.mounts[side].tool.dispense(self.volume_ul, feed=self.feed)  # type: ignore

    def describe(self) -> str:
        """Return a human-readable description of the dispense.

        Returns:
            str: Description containing the dispense volume, or `"all"` when
            `volume_ul` is `None`, and the destination location.
        """
        v = "all" if self.volume_ul is None else f"{self.volume_ul} uL"
        return f"dispense {v} to {self.where}"


@dataclass
class BlowOutStep(Step):
    """Perform a blow-out operation using the active tool.

    An optional location may be supplied. When present, the active mount is
    safely moved to that location before the blow-out operation.

    Attributes:
        where: Optional location at which to perform the blow-out.
    """

    where: Location | None = None

    def execute(self, robot: Robot, side: MountSide) -> None:
        """Optionally move to the blow-out location and perform a blow-out.

        Args:
            robot: Robot instance used for movement and tool operation.
            side: Currently active mount used for the blow-out.
        """
        if self.where is not None:
            robot.safe_move_to(self.where.resolve(robot), side)
        robot.mounts[side].tool.blow_out()  # type: ignore

    def describe(self) -> str:
        """Return a human-readable description of the blow-out operation.

        Returns:
            str: Description of the blow-out operation.
        """
        return "blow out"


@dataclass
class DelayStep(Step):
    """Pause routine execution for a specified duration.

    Attributes:
        seconds: Number of seconds to pause execution. Fractional values are
            supported.
    """

    seconds: float

    def execute(self, robot: Robot, side: MountSide) -> None:
        """Pause execution for the configured duration.

        Args:
            robot: Robot instance. Unused by this step.
            side: Currently active mount. Unused by this step.
        """
        time.sleep(self.seconds)

    def describe(self) -> str:
        """Return a human-readable description of the delay.

        Returns:
            str: Description containing the configured delay duration in seconds.
        """
        return f"delay {self.seconds}s"


@dataclass
class CommentStep(Step):
    """Non-operative step used to annotate a routine.

    A comment step has no hardware effect and exists to make routines easier
    to inspect, dry-run, log, and understand. It participates in the routine's
    ordered step sequence like any other step.

    Attributes:
        text: Human-readable annotation associated with the step.
    """

    text: str

    def execute(self, robot: Robot, side: MountSide) -> None:
        """Perform no operation.

        Args:
            robot: Robot instance. Unused by this step.
            side: Currently active mount. Unused by this step.
        """

    def describe(self) -> str:
        """Return the comment in display form.

        Returns:
            str: Comment text prefixed with `"#"` for use in dry-run output.
        """
        return f"# {self.text}"
