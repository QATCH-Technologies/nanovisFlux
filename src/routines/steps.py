from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..core import MountSide
from .location import Location


class Step:
    """One instruction in a routine. Steps operate in deck space (slots and
    wells) and delegate the actual motion to the robot -- mirroring the
    protocol layer's 'objects, not strings' idea one level up.

    ``side`` is the routine's *current* mount, threaded through by
    Routine.run -- normally every step just acts on it and returns None.
    SwitchMountStep is the one exception: it returns the new MountSide,
    which Routine.run then uses for every step after it. This is what lets
    one routine address more than one mount without being written "for" a
    specific side (see SwitchMountStep's own docstring).
    """

    def execute(self, robot, side: MountSide) -> MountSide | None:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> str:
        return type(self).__name__


@dataclass
class HomeStep(Step):
    axes: tuple = ()

    def execute(self, robot, side):
        robot.home(*self.axes)

    def describe(self):
        return "home " + (" ".join(a.letter for a in self.axes) or "all")


@dataclass
class MoveStep(Step):
    where: Location
    feed: int | None = None

    def execute(self, robot, side):
        robot.safe_move_to(self.where.resolve(robot), side, feed=self.feed)

    def describe(self):
        return f"move to {self.where}"


@dataclass
class SwitchMountStep(Step):
    """Make ``mount`` the active side for every step after this one --
    e.g. an aspirate on the left pipette followed by a dispense on the
    right one, in a single routine that was never pinned to one side to
    begin with (see Routine.run). Optionally also moves that mount to
    ``where`` as part of the same action (the common case: switch to
    whichever mount needs to act next, right where it needs to act) --
    equivalent to this step plus a separate MoveStep(where), just as one
    instruction; leave ``where`` unset to switch without moving.
    """

    mount: MountSide
    where: Location | None = None
    feed: int | None = None

    def execute(self, robot, side):
        if self.where is not None:
            robot.safe_move_to(self.where.resolve(robot), self.mount, feed=self.feed)
        return self.mount

    def describe(self):
        base = f"switch to {self.mount.value} mount"
        return f"{base}, move to {self.where}" if self.where is not None else base


@dataclass
class PickUpTipStep(Step):
    where: Location  # tip position in the rack (XY resolved here)
    tip: str  # key into robot-known tip geometries
    pickup: object  # a TipPickup (press_z etc.)

    def execute(self, robot, side):
        pip = robot.mounts[side].tool
        xy = self.where.resolve(robot)
        tip = robot.tips[self.tip] if hasattr(robot, "tips") else self.tip
        pip.pick_up_tip(xy, tip, self.pickup)

    def describe(self):
        return f"pick up tip {self.tip} at {self.where}"


@dataclass
class DropTipStep(Step):
    where: Location | None = None
    eject_z_mm: float | None = None

    def execute(self, robot, side):
        pip = robot.mounts[side].tool
        xy = self.where.resolve(robot) if self.where else None
        pip.drop_tip(xy, self.eject_z_mm)

    def describe(self):
        return "drop tip" + (f" at {self.where}" if self.where else "")


@dataclass
class AspirateStep(Step):
    volume_ul: float
    where: Location
    feed: int | None = None

    def execute(self, robot, side):
        robot.safe_move_to(self.where.resolve(robot), side, feed=self.feed)
        robot.mounts[side].tool.aspirate(self.volume_ul, feed=self.feed)

    def describe(self):
        return f"aspirate {self.volume_ul} uL from {self.where}"


@dataclass
class DispenseStep(Step):
    volume_ul: float | None
    where: Location
    feed: int | None = None

    def execute(self, robot, side):
        robot.safe_move_to(self.where.resolve(robot), side, feed=self.feed)
        robot.mounts[side].tool.dispense(self.volume_ul, feed=self.feed)

    def describe(self):
        v = "all" if self.volume_ul is None else f"{self.volume_ul} uL"
        return f"dispense {v} to {self.where}"


@dataclass
class BlowOutStep(Step):
    where: Location | None = None

    def execute(self, robot, side):
        if self.where is not None:
            robot.safe_move_to(self.where.resolve(robot), side)
        robot.mounts[side].tool.blow_out()

    def describe(self):
        return "blow out"


@dataclass
class DelayStep(Step):
    seconds: float

    def execute(self, robot, side):
        time.sleep(self.seconds)

    def describe(self):
        return f"delay {self.seconds}s"


@dataclass
class CommentStep(Step):
    text: str

    def execute(self, robot, side):
        pass

    def describe(self):
        return f"# {self.text}"
