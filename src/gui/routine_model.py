"""Routine step model: small, JSON-serializable dataclasses the builder
edits and the runner executes. Each step's ``run(robot, log)`` talks to the
same Robot/Controller/Tool objects a hand-written script would -- the GUI
adds no new execution machinery of its own, just a UI over the same API
scripts/gamepad_control.py and scripts/scan_deck_topography.py already use.

Every step that targets a point in deck space (Move, Aspirate, Dispense,
PickUpTip, DropTip, BlowOut) supports two addressing modes:

  - ``labware`` + ``well``: a symbolic reference resolved against
    ``robot.labware`` at run time (mirrors src/routines/'s WellLocation),
    optionally auto-``advance``-ing through that labware's wells one at a
    time on successive runs -- the mechanism a Repeat block uses to hand
    out a fresh tip, or target a new destination well, each cycle.
  - raw ``x``/``y``/``z``: a bare deck-space coordinate, exactly like
    before. Left blank ``labware`` always falls back to this -- so a
    routine can freely mix symbolic wells and hand-picked coordinates.
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


def _resolve_point(step, robot, default_ref: str = "clearance"):
    """Shared location logic for every point-targeting step: a
    ``labware``/``well`` reference (optionally auto-advancing through that
    labware's wells each time this step runs) takes precedence over the
    step's raw ``x``/``y``/``z`` fields.

    Returns ``(DeckPoint, well_name_or_None)`` so callers can log which
    well was actually used.
    """
    if step.labware:
        labware = robot.labware.get(step.labware)
        if labware is None:
            raise StepError(
                f"unknown labware {step.labware!r} (check the loaded config's labware:)")
        names = list(labware.wells.keys())
        if getattr(step, "advance", False):
            if step._cursor is None:
                start = step.well or names[0]
                if start not in names:
                    raise StepError(f"{start!r} is not a well of labware {step.labware!r}")
                step._cursor = names.index(start)
            else:
                step._cursor += 1
            if step._cursor >= len(names):
                raise StepError(f"labware {step.labware!r} ran out of wells after {names[-1]!r}")
            well_name = names[step._cursor]
        else:
            if not step.well:
                raise StepError(f"labware {step.labware!r} given but no well specified")
            if step.well not in names:
                raise StepError(f"{step.well!r} is not a well of labware {step.labware!r}")
            well_name = step.well
        ref = getattr(step, "ref", default_ref)
        return labware.well(well_name, ref=ref), well_name
    return DeckPoint(step.x, step.y, getattr(step, "z", 0.0)), None


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
    #: param form; widget_kind in {"text", "float", "float_opt", "int",
    #: "int_opt", "side", "bool", "ref", "labware", "well", "axes"} --
    #: "labware" and "well" render as an editable combo box listing what's
    #: currently loaded on the deck (see RoutineBuilderWidget.set_robot),
    #: but still accept freely-typed text so a routine can be authored
    #: offline; "axes" renders per-axis checkboxes plus an ALL shortcut
    #: (see HomeAxesWidget) over the same space-separated-letters string.
    param_fields: ClassVar[tuple] = ()

    def summary(self) -> str:
        return self.label

    def run(self, robot, log) -> None:
        raise NotImplementedError

    def reset(self) -> None:
        """Clear any per-run state (e.g. an auto-advancing well cursor) so
        a routine behaves the same on every run instead of continuing from
        where a previous run left off. No-op unless overridden."""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Step":
        return cls(**d)


@dataclass
class HomeStep(Step):
    kind: ClassVar[str] = "home"
    label: ClassVar[str] = "Home"
    color: ClassVar[str] = "#5B7DB1"
    param_fields: ClassVar[tuple] = (("axes", "axes", ""),)
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
        ("side", "side", "left"), ("labware", "labware", ""), ("well", "well", ""),
        ("ref", "ref", "clearance"), ("x", "float", 0.0), ("y", "float", 0.0),
        ("z", "float", 0.0), ("feed", "int_opt", None), ("safe", "bool", True))
    side: str = "left"
    labware: str = ""
    well: str = ""
    ref: str = "clearance"
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    feed: int | None = None
    safe: bool = True

    def summary(self) -> str:
        tag = " [safe]" if self.safe else " [direct]"
        where = (f"{self.labware}:{self.well or '?'}" if self.labware
                 else f"({self.x:.1f}, {self.y:.1f}, {self.z:.1f}) mm")
        return f"Move {self.side} -> {where}{tag}"

    def run(self, robot, log) -> None:
        side = SIDES[self.side]
        pt, well_name = _resolve_point(self, robot)
        where = (f"{self.labware}:{well_name}" if well_name
                 else f"({pt.x:.1f}, {pt.y:.1f}, {pt.z:.1f}) mm")
        log(f"moving {self.side} mount to {where}")
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
        ("side", "side", "left"), ("volume_ul", "float", 50.0), ("feed", "int_opt", None),
        ("labware", "labware", ""), ("well", "well", ""), ("ref", "ref", "clearance"),
        ("advance", "bool", False), ("wait_s", "float", 0.0))
    side: str = "left"
    volume_ul: float = 50.0
    feed: int | None = None
    labware: str = ""
    well: str = ""
    ref: str = "clearance"
    advance: bool = False
    wait_s: float = 0.0   # pause this long after aspirating, e.g. to let liquid settle in the tip

    def __post_init__(self) -> None:
        self._cursor = None

    def reset(self) -> None:
        self._cursor = None

    def summary(self) -> str:
        where = ""
        if self.labware:
            where = f" from {self.labware}:{self.well or '(first well)'}"
            if self.advance:
                where += " [advancing]"
        wait = f", wait {self.wait_s:.1f}s" if self.wait_s > 0 else ""
        return f"Aspirate {self.volume_ul:.0f} uL{where}{wait} ({self.side})"

    def run(self, robot, log) -> None:
        tool = robot.mounts[SIDES[self.side]].tool
        if tool is None or not hasattr(tool, "aspirate"):
            raise StepError(f"no pipette attached to the {self.side} mount")
        if self.labware:
            pt, well_name = _resolve_point(self, robot)
            robot.safe_move_to(pt, SIDES[self.side], feed=self.feed)
            log(f"moved to {self.labware}:{well_name}")
        tool.aspirate(self.volume_ul, feed=self.feed)
        log(f"aspirated {self.volume_ul:.0f} uL -> {tool.current_volume_ul:.0f} uL in tip")
        if self.wait_s > 0:
            import time
            log(f"waiting {self.wait_s:.1f}s")
            time.sleep(self.wait_s)


@dataclass
class DispenseStep(Step):
    kind: ClassVar[str] = "dispense"
    label: ClassVar[str] = "Dispense"
    color: ClassVar[str] = "#B15B3E"
    param_fields: ClassVar[tuple] = (
        ("side", "side", "left"), ("volume_ul", "float_opt", None), ("feed", "int_opt", None),
        ("labware", "labware", ""), ("well", "well", ""), ("ref", "ref", "clearance"),
        ("advance", "bool", False), ("wait_s", "float", 0.0))
    side: str = "left"
    volume_ul: float | None = None   # None = dispense everything in the tip
    feed: int | None = None
    labware: str = ""
    well: str = ""
    ref: str = "clearance"
    advance: bool = False
    wait_s: float = 0.0   # pause this long after dispensing, e.g. to let the last drop fall

    def __post_init__(self) -> None:
        self._cursor = None

    def reset(self) -> None:
        self._cursor = None

    def summary(self) -> str:
        vol = "all" if self.volume_ul is None else f"{self.volume_ul:.0f} uL"
        where = ""
        if self.labware:
            where = f" to {self.labware}:{self.well or '(first well)'}"
            if self.advance:
                where += " [advancing]"
        wait = f", wait {self.wait_s:.1f}s" if self.wait_s > 0 else ""
        return f"Dispense {vol}{where}{wait} ({self.side})"

    def run(self, robot, log) -> None:
        tool = robot.mounts[SIDES[self.side]].tool
        if tool is None or not hasattr(tool, "dispense"):
            raise StepError(f"no pipette attached to the {self.side} mount")
        if self.labware:
            pt, well_name = _resolve_point(self, robot)
            robot.safe_move_to(pt, SIDES[self.side], feed=self.feed)
            log(f"moved to {self.labware}:{well_name}")
        tool.dispense(self.volume_ul, feed=self.feed)
        log(f"dispensed -> {tool.current_volume_ul:.0f} uL remaining in tip")
        if self.wait_s > 0:
            import time
            log(f"waiting {self.wait_s:.1f}s")
            time.sleep(self.wait_s)


@dataclass
class PickUpTipStep(Step):
    kind: ClassVar[str] = "pick_up_tip"
    label: ClassVar[str] = "Pick Up Tip"
    color: ClassVar[str] = "#6B8E5B"
    param_fields: ClassVar[tuple] = (
        ("side", "side", "left"), ("tip_name", "text", ""), ("press_z", "float", 0.0),
        ("labware", "labware", ""), ("well", "well", ""), ("advance", "bool", False),
        ("x", "float", 0.0), ("y", "float", 0.0))
    side: str = "left"
    x: float = 0.0
    y: float = 0.0
    tip_name: str = ""
    press_z: float = 0.0
    labware: str = ""
    well: str = ""
    advance: bool = False

    def __post_init__(self) -> None:
        self._cursor = None

    def reset(self) -> None:
        self._cursor = None

    def summary(self) -> str:
        if self.labware:
            where = f"{self.labware}:{self.well or '(first well)'}"
            if self.advance:
                where += " [advancing]"
        else:
            where = f"({self.x:.1f}, {self.y:.1f})"
        return f"Pick up {self.tip_name or 'tip'} at {where} ({self.side})"

    def run(self, robot, log) -> None:
        from ..tools import TipPickup
        tool = robot.mounts[SIDES[self.side]].tool
        if tool is None or not hasattr(tool, "pick_up_tip"):
            raise StepError(f"no pipette attached to the {self.side} mount")
        tip = robot.tips.get(self.tip_name)
        if tip is None:
            raise StepError(
                f"unknown tip geometry {self.tip_name!r} (check the loaded config's tips:)")
        pt, well_name = _resolve_point(self, robot, default_ref="top")
        where = f"{self.labware}:{well_name}" if well_name else f"({pt.x:.1f}, {pt.y:.1f})"
        log(f"picking up {tip.name} at {where}")
        tool.pick_up_tip(DeckPoint(pt.x, pt.y), tip, TipPickup(press_z_mm=self.press_z))


@dataclass
class DropTipStep(Step):
    kind: ClassVar[str] = "drop_tip"
    label: ClassVar[str] = "Drop Tip"
    color: ClassVar[str] = "#8E6B5B"
    param_fields: ClassVar[tuple] = (
        ("side", "side", "left"), ("eject_z", "float_opt", None),
        ("labware", "labware", ""), ("well", "well", ""),
        ("x", "float_opt", None), ("y", "float_opt", None))
    side: str = "left"
    x: float | None = None
    y: float | None = None
    eject_z: float | None = None
    labware: str = ""
    well: str = ""

    def summary(self) -> str:
        if self.labware:
            where = f"at {self.labware}:{self.well or '(first well)'}"
        elif self.x is None:
            where = "in place"
        else:
            where = f"at ({self.x:.1f}, {self.y:.1f})"
        return f"Drop tip {where} ({self.side})"

    def run(self, robot, log) -> None:
        tool = robot.mounts[SIDES[self.side]].tool
        if tool is None or not hasattr(tool, "drop_tip"):
            raise StepError(f"no pipette attached to the {self.side} mount")
        xy = None
        if self.labware:
            pt, well_name = _resolve_point(self, robot, default_ref="top")
            xy = DeckPoint(pt.x, pt.y)
            log(f"dropping tip at {self.labware}:{well_name}")
        elif self.x is not None and self.y is not None:
            xy = DeckPoint(self.x, self.y)
            log("dropping tip")
        else:
            log("dropping tip in place")
        tool.drop_tip(xy, self.eject_z)


@dataclass
class BlowOutStep(Step):
    kind: ClassVar[str] = "blow_out"
    label: ClassVar[str] = "Blow Out"
    color: ClassVar[str] = "#8E5BA8"
    param_fields: ClassVar[tuple] = (
        ("side", "side", "left"), ("labware", "labware", ""), ("well", "well", ""),
        ("ref", "ref", "clearance"), ("x", "float_opt", None), ("y", "float_opt", None),
        ("z", "float_opt", None))
    side: str = "left"
    labware: str = ""
    well: str = ""
    ref: str = "clearance"
    x: float | None = None
    y: float | None = None
    z: float | None = None

    def summary(self) -> str:
        if self.labware:
            where = f" at {self.labware}:{self.well or '(first well)'}"
        elif self.x is not None:
            where = f" at ({self.x:.1f}, {self.y:.1f})"
        else:
            where = ""
        return f"Blow out{where} ({self.side})"

    def run(self, robot, log) -> None:
        tool = robot.mounts[SIDES[self.side]].tool
        if tool is None or not hasattr(tool, "blow_out"):
            raise StepError(f"no pipette attached to the {self.side} mount")
        if self.labware:
            pt, well_name = _resolve_point(self, robot)
            robot.safe_move_to(pt, SIDES[self.side])
            log(f"moved to {self.labware}:{well_name}")
        elif self.x is not None and self.y is not None:
            robot.safe_move_to(DeckPoint(self.x, self.y, self.z or 0.0), SIDES[self.side])
            log("moved to blow-out point")
        tool.blow_out()
        log("blew out")


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


@dataclass
class RepeatStep(Step):
    """Re-runs a nested list of steps (its ``body``) ``times`` times --
    the loop primitive that makes auto-advancing steps useful: put a
    Pick Up Tip (advance=True) / Aspirate / Dispense (advance=True) /
    Blow Out / Drop Tip sequence in the body and each cycle draws the next
    tip and targets the next destination well automatically.

    Runs as a single unit from the outer routine's point of view -- Step ▸
    steps over the whole repeat block rather than one inner step at a time
    -- but every inner step still logs individually.
    """
    kind: ClassVar[str] = "repeat"
    label: ClassVar[str] = "Repeat"
    color: ClassVar[str] = "#7A5BB1"
    param_fields: ClassVar[tuple] = (("times", "int", 1),)
    times: int = 1
    body: "Routine" = field(default_factory=lambda: Routine(name="repeat body"))

    def summary(self) -> str:
        n = len(self.body.steps)
        return f"Repeat x{self.times}  ({n} step{'s' if n != 1 else ''})"

    def to_dict(self) -> dict:
        return {"kind": self.kind, "times": self.times, "body": self.body.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "RepeatStep":
        return cls(times=d.get("times", 1), body=Routine.from_dict(d.get("body", {})))

    def reset(self) -> None:
        for s in self.body.steps:
            s.reset()

    def run(self, robot, log) -> None:
        for i in range(self.times):
            log(f"-- repeat {i + 1}/{self.times} --")
            for step in self.body.steps:
                step.run(robot, log)


REGISTRY: dict = {
    s.kind: s for s in (
        HomeStep, MoveStep, AspirateStep, DispenseStep, PickUpTipStep, DropTipStep,
        BlowOutStep, WaitStep, ReadDistanceStep, RawGcodeStep, RepeatStep,
    )
}


@dataclass
class Routine:
    name: str = "untitled routine"
    steps: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "steps": [s.to_dict() for s in self.steps]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "Routine":
        steps = []
        for d in data.get("steps", []):
            d = dict(d)
            kind = d.pop("kind")
            steps.append(REGISTRY[kind].from_dict(d))
        return cls(name=data.get("name", "untitled routine"), steps=steps)

    @classmethod
    def from_json(cls, text: str) -> "Routine":
        return cls.from_dict(json.loads(text))
