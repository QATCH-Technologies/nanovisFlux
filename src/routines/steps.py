from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..core import MountSide
from .location import Location


class Step:
    """One instruction in a routine. Steps operate in deck space (slots and
    wells) and delegate the actual motion to the robot -- mirroring the
    protocol layer's 'objects, not strings' idea one level up.
    """

    def execute(self, robot, side: MountSide) -> None:  # pragma: no cover
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
