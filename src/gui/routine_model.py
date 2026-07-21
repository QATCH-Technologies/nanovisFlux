"""Routine step model: small, JSON-serializable dataclasses the builder
edits and the runner executes. Each step's ``run(robot, log)`` talks to the
same Robot/Controller/Tool objects a hand-written script would -- the GUI
adds no new execution machinery of its own, just a UI over the same API
scripts/gamepad_control.py and scripts/scan_deck_topography.py already use.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from typing import ClassVar

from ..core import AxisId, MountSide
from ..geometry.coordinates import DeckPoint

SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT, "rear": MountSide.REAR}


class StepError(Exception):
    """Raised for a step precondition the caller should see as a routine
    failure (e.g. no pipette attached) rather than a raw AttributeError."""


@dataclass
class _RawLine:
    """Duck-types protocol.commands.Command (render() + acknowledges) so a
    routine's raw-gcode escape hatch still goes through Controller.execute
    -- and is therefore traced/logged the same as every typed command."""
    line: str
    acknowledges: ClassVar[bool] = True

    def render(self) -> str:
        return self.line


@dataclass
class Step:
    kind: ClassVar[str] = "step"
    label: ClassVar[str] = "Step"
    color: ClassVar[str] = "#8A8780"
    #: ordered (field_name, widget_kind, default) the builder uses to draw a
    #: param form; widget_kind in {"text", "float", "float_opt", "int_opt", "side", "bool"}
    param_fields: ClassVar[tuple] = ()

    def summary(self) -> str:
        return self.label

    def run(self, robot, log) -> None:
        raise NotImplementedError

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind
        return d


@dataclass
class HomeStep(Step):
    kind: ClassVar[str] = "home"
    label: ClassVar[str] = "Home"
    color: ClassVar[str] = "#5B7DB1"
    param_fields: ClassVar[tuple] = (("axes", "text", ""),)
    axes: str = ""   # space-separated letters, e.g. "X Y"; empty = all

    def summary(self) -> str:
        return f"Home {self.axes.strip() or 'all axes'}"

    def run(self, robot, log) -> None:
        axes = tuple(AxisId(a.upper()) for a in self.axes.split()) if self.axes.strip() else ()
        log(f"homing {' '.join(a.letter for a in axes) or 'all axes'}")
        robot.home(*axes)


@dataclass
class MoveStep(Step):
    kind: ClassVar[str] = "move"
    label: ClassVar[str] = "Move"
    color: ClassVar[str] = "#3E8E5B"
    param_fields: ClassVar[tuple] = (
        ("side", "side", "left"), ("x", "float", 0.0), ("y", "float", 0.0),
        ("z", "float", 0.0), ("feed", "int_opt", None), ("safe", "bool", True))
    side: str = "left"
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    feed: int | None = None
    safe: bool = True

    def summary(self) -> str:
        tag = " [safe]" if self.safe else " [direct]"
        return f"Move {self.side} -> ({self.x:.1f}, {self.y:.1f}, {self.z:.1f}) mm{tag}"

    def run(self, robot, log) -> None:
        side = SIDES[self.side]
        pt = DeckPoint(self.x, self.y, self.z)
        log(f"moving {self.side} mount to ({pt.x:.1f}, {pt.y:.1f}, {pt.z:.1f}) mm")
        if self.safe:
            robot.safe_move_to(pt, side, feed=self.feed)
        else:
            robot.move_to(pt, side, feed=self.feed)


@dataclass
class AspirateStep(Step):
    kind: ClassVar[str] = "aspirate"
    label: ClassVar[str] = "Aspirate"
    color: ClassVar[str] = "#B18A3E"
    param_fields: ClassVar[tuple] = (
        ("side", "side", "left"), ("volume_ul", "float", 50.0), ("feed", "int_opt", None))
    side: str = "left"
    volume_ul: float = 50.0
    feed: int | None = None

    def summary(self) -> str:
        return f"Aspirate {self.volume_ul:.0f} uL ({self.side})"

    def run(self, robot, log) -> None:
        tool = robot.mounts[SIDES[self.side]].tool
        if tool is None or not hasattr(tool, "aspirate"):
            raise StepError(f"no pipette attached to the {self.side} mount")
        tool.aspirate(self.volume_ul, feed=self.feed)
        log(f"aspirated {self.volume_ul:.0f} uL -> {tool.current_volume_ul:.0f} uL in tip")


@dataclass
class DispenseStep(Step):
    kind: ClassVar[str] = "dispense"
    label: ClassVar[str] = "Dispense"
    color: ClassVar[str] = "#B15B3E"
    param_fields: ClassVar[tuple] = (
        ("side", "side", "left"), ("volume_ul", "float_opt", None), ("feed", "int_opt", None))
    side: str = "left"
    volume_ul: float | None = None   # None = dispense everything in the tip
    feed: int | None = None

    def summary(self) -> str:
        vol = "all" if self.volume_ul is None else f"{self.volume_ul:.0f} uL"
        return f"Dispense {vol} ({self.side})"

    def run(self, robot, log) -> None:
        tool = robot.mounts[SIDES[self.side]].tool
        if tool is None or not hasattr(tool, "dispense"):
            raise StepError(f"no pipette attached to the {self.side} mount")
        tool.dispense(self.volume_ul, feed=self.feed)
        log(f"dispensed -> {tool.current_volume_ul:.0f} uL remaining in tip")


@dataclass
class PickUpTipStep(Step):
    kind: ClassVar[str] = "pick_up_tip"
    label: ClassVar[str] = "Pick Up Tip"
    color: ClassVar[str] = "#6B8E5B"
    param_fields: ClassVar[tuple] = (
        ("side", "side", "left"), ("x", "float", 0.0), ("y", "float", 0.0),
        ("tip_name", "text", ""), ("press_z", "float", 0.0))
    side: str = "left"
    x: float = 0.0
    y: float = 0.0
    tip_name: str = ""
    press_z: float = 0.0

    def summary(self) -> str:
        return f"Pick up {self.tip_name or 'tip'} at ({self.x:.1f}, {self.y:.1f}) ({self.side})"

    def run(self, robot, log) -> None:
        from ..tools import TipPickup
        tool = robot.mounts[SIDES[self.side]].tool
        if tool is None or not hasattr(tool, "pick_up_tip"):
            raise StepError(f"no pipette attached to the {self.side} mount")
        tip = robot.tips.get(self.tip_name)
        if tip is None:
            raise StepError(f"unknown tip geometry {self.tip_name!r} (check the loaded config's tips:)")
        log(f"picking up {tip.name} at ({self.x:.1f}, {self.y:.1f})")
        tool.pick_up_tip(DeckPoint(self.x, self.y), tip, TipPickup(press_z_mm=self.press_z))


@dataclass
class DropTipStep(Step):
    kind: ClassVar[str] = "drop_tip"
    label: ClassVar[str] = "Drop Tip"
    color: ClassVar[str] = "#8E6B5B"
    param_fields: ClassVar[tuple] = (
        ("side", "side", "left"), ("x", "float_opt", None), ("y", "float_opt", None),
        ("eject_z", "float_opt", None))
    side: str = "left"
    x: float | None = None
    y: float | None = None
    eject_z: float | None = None

    def summary(self) -> str:
        where = "in place" if self.x is None else f"at ({self.x:.1f}, {self.y:.1f})"
        return f"Drop tip {where} ({self.side})"

    def run(self, robot, log) -> None:
        tool = robot.mounts[SIDES[self.side]].tool
        if tool is None or not hasattr(tool, "drop_tip"):
            raise StepError(f"no pipette attached to the {self.side} mount")
        xy = DeckPoint(self.x, self.y) if self.x is not None and self.y is not None else None
        log("dropping tip")
        tool.drop_tip(xy, self.eject_z)


@dataclass
class WaitStep(Step):
    kind: ClassVar[str] = "wait"
    label: ClassVar[str] = "Wait"
    color: ClassVar[str] = "#8A8780"
    param_fields: ClassVar[tuple] = (("seconds", "float", 1.0),)
    seconds: float = 1.0

    def summary(self) -> str:
        return f"Wait {self.seconds:.1f} s"

    def run(self, robot, log) -> None:
        import time
        log(f"waiting {self.seconds:.1f} s")
        time.sleep(self.seconds)


@dataclass
class ReadDistanceStep(Step):
    kind: ClassVar[str] = "read_distance"
    label: ClassVar[str] = "Read Distance"
    color: ClassVar[str] = "#5B8CB1"
    param_fields: ClassVar[tuple] = ()

    def summary(self) -> str:
        return "Read rear ultrasonic distance"

    def run(self, robot, log) -> None:
        sensor = robot.rear()
        if sensor is None:
            raise StepError("no ultrasonic sensor attached to the rear mount")
        distance = sensor.read_distance_mm()
        log("out of range / no echo" if distance is None else f"distance: {distance:.1f} mm")


@dataclass
class RawGcodeStep(Step):
    kind: ClassVar[str] = "raw"
    label: ClassVar[str] = "Raw G-code"
    color: ClassVar[str] = "#6B6B68"
    param_fields: ClassVar[tuple] = (("line", "text", "M114"),)
    line: str = "M114"

    def summary(self) -> str:
        return f"Send: {self.line}"

    def run(self, robot, log) -> None:
        log(f"sending raw line: {self.line}")
        robot.controller.execute(_RawLine(self.line))


REGISTRY: dict = {
    s.kind: s for s in (
        HomeStep, MoveStep, AspirateStep, DispenseStep, PickUpTipStep, DropTipStep,
        WaitStep, ReadDistanceStep, RawGcodeStep,
    )
}


@dataclass
class Routine:
    name: str = "untitled routine"
    steps: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({"name": self.name, "steps": [s.to_dict() for s in self.steps]}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Routine":
        data = json.loads(text)
        steps = []
        for d in data.get("steps", []):
            d = dict(d)
            kind = d.pop("kind")
            steps.append(REGISTRY[kind](**d))
        return cls(name=data.get("name", "untitled routine"), steps=steps)
