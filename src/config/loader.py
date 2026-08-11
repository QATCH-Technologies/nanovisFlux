"""Build the whole object graph from a YAML file, so nothing is hard-coded.

Every builder takes a plain dict (one YAML section) and returns domain
objects, and ``load_robot`` wires them into a ready Robot. PyYAML is imported
lazily, so importing this module never requires it.
"""

from __future__ import annotations

from ..core import AxisId, MountSide
from ..deck import Deck, Labware, Slot, SlotObstacle, Corner, CalibrationMark, inset_corner_point
from ..geometry import AffineTransform2D, AxisScale, DeckCalibration, DeckPoint
from ..motion.axis import AxisConfig, default_axis_configs
from ..robot import Robot
from ..tools import Pipette, PlungerModel, TipGeometry, UltrasonicSensor
from ..transport import FakeTransport, SerialTransport

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT, "rear": MountSide.REAR}


def load_config(path: str) -> dict:
    import yaml  # lazy dependency

    with open(path, "r") as fh:
        return yaml.safe_load(fh)


# -- individual sections ----------------------------------------------------
def build_transport(cfg: dict):
    kind = cfg.get("type", "fake")
    if kind == "serial":
        return SerialTransport(cfg["port"], cfg.get("baudrate", 115200), cfg.get("timeout", 30.0))
    if kind == "fake":
        return FakeTransport()
    if kind == "tcp":
        raise NotImplementedError("add a TCPTransport and wire it here")
    raise ValueError(f"unknown transport type: {kind}")


def build_axes(cfg: dict) -> dict:
    """Start from firmware defaults and apply per-axis overrides."""
    axes = default_axis_configs()
    for letter, over in (cfg or {}).items():
        a = AxisId(letter.upper())
        base = axes[a]
        axes[a] = AxisConfig(
            axis=a,
            endstop_limit=over.get("endstop_limit", base.endstop_limit),
            homing_dir_forward=over.get("homing_dir_forward", base.homing_dir_forward),
            invert=over.get("invert", base.invert),
            travel_speed=over.get("travel_speed", base.travel_speed),
            homing_speed=over.get("homing_speed", base.homing_speed),
            travel_accel=over.get("travel_accel", base.travel_accel),
            endstop_bounce=over.get("endstop_bounce", base.endstop_bounce),
            steps_per_mm=over.get("steps_per_mm", base.steps_per_mm),
        )
    return axes


def load_calibration(path: str) -> DeckCalibration:
    """Load a calibration section either from a full robot config (under
    the ``calibration:`` key) or a standalone calibration-only file (as
    written by scripts/calibrate_deck.py)."""
    cfg = load_config(path)
    return build_calibration(cfg.get("calibration", cfg))


def build_calibration(cfg: dict) -> DeckCalibration:
    if "affine" in cfg:
        xy = AffineTransform2D(*cfg["affine"])
    else:
        deck_pts = [DeckPoint(p["x"], p["y"]) for p in cfg["points"]["deck"]]
        xy = AffineTransform2D.from_point_pairs(
            [(p.x, p.y) for p in deck_pts], [tuple(m) for m in cfg["points"]["motor"]]
        )
    z_scale = AxisScale(steps_per_mm=cfg["z_scale"]["steps_per_mm"])
    z_zero = {_SIDES[k]: int(v) for k, v in cfg.get("z_zero", {}).items()}
    return DeckCalibration(xy=xy, z_scale=z_scale, z_zero=z_zero)


def _build_slot_obstacles(cfg: list) -> list:
    return [
        SlotObstacle(offset=tuple(o["offset"]), size=tuple(o["size"]), height_mm=o["height_mm"])
        for o in (cfg or [])
    ]


def _build_calibration_marks(cfg: dict | None, slots: dict) -> dict:
    """Named fixed reference points for the deck<->motor calibration wizard
    (see gui/calibration_dialog.py) -- each is a slot corner inset by a
    shared mm offset (see deck.inset_corner_point), so only the slot +
    corner need naming in YAML rather than hand-computed absolute mm."""
    if not cfg:
        return {}
    inset = cfg.get("inset_mm", {})
    inset_x, inset_y = inset.get("x", 12.0), inset.get("y", 9.0)
    marks = {}
    for m in cfg.get("points", []):
        slot = slots[str(m["slot"])]
        corner = Corner(m["corner"])
        point = inset_corner_point(slot, corner, inset_x, inset_y)
        marks[m["name"]] = CalibrationMark(name=m["name"], slot=slot.name, corner=corner, point=point)
    return marks


def build_deck(cfg: dict) -> Deck:
    if "grid" in cfg:
        g = cfg["grid"]
        deck = Deck.grid(
            rows=g["rows"],
            cols=g["cols"],
            origin=DeckPoint(g["origin"]["x"], g["origin"]["y"]),
            pitch=tuple(g["pitch"]),
            names=g.get("names"),
        )
    else:
        deck = Deck()
        for s in cfg.get("slots", []):
            walls = s.get("walls", {})
            deck.add(
                Slot(
                    name=str(s["name"]),
                    origin=DeckPoint(s["x"], s["y"], s.get("z", 0.0)),
                    size=tuple(s.get("size", (0.0, 0.0))),
                    wall_height_mm=walls.get("height_mm", 0.0),
                    wall_thickness_mm=walls.get("thickness_mm", 0.0),
                    obstacles=_build_slot_obstacles(s.get("obstacles")),
                )
            )
    deck.margins = cfg.get("margins")
    deck.frame_margins = cfg.get("frame_margins")
    deck.enclosure_height_mm = cfg.get("enclosure_height_mm")
    deck.calibration_marks = _build_calibration_marks(cfg.get("calibration_marks"), deck.slots)
    return deck


def build_labware(cfg: dict) -> Labware:
    return Labware.from_dict(cfg)


def build_tips(cfg: list) -> dict:
    tips = {}
    for t in cfg or []:
        tips[t["name"]] = TipGeometry(
            name=t["name"],
            length_mm=t["length_mm"],
            max_volume_ul=t.get("max_volume_ul", 0.0),
            inner_diameter_mm=t.get("inner_diameter_mm", 0.0),
        )
    return tips


def _build_pipette(cfg: dict) -> Pipette:
    return Pipette(
        name=cfg["name"],
        plunger=PlungerModel(
            microsteps_per_ul=cfg["microsteps_per_ul"],
            bottom_microsteps=cfg.get("bottom_microsteps", 0),
        ),
        max_volume_ul=cfg["max_volume_ul"],
    )


def _build_ultrasonic(cfg: dict) -> UltrasonicSensor:
    off = cfg.get("offset_mm", {})
    return UltrasonicSensor(
        offset_mm=(off.get("x", 0.0), off.get("y", 0.0), off.get("z", 0.0)),
        max_range_mm=cfg.get("max_range_mm", 4000.0),
    )


# -- top level --------------------------------------------------------------
def load_robot(path: str) -> Robot:
    cfg = load_config(path)
    transport = build_transport(cfg.get("transport", {"type": "fake"}))
    calibration = build_calibration(cfg["calibration"]) if "calibration" in cfg else None
    deck = build_deck(cfg["deck"]) if "deck" in cfg else None

    robot = Robot(
        transport,
        calibration=calibration,
        deck=deck,
        travel_z_mm=cfg.get("travel_z_mm", 60.0),
        timeout=cfg.get("timeout", 30.0),
    )
    # override axis configs from YAML
    for a, ac in build_axes(cfg.get("axes", {})).items():
        robot.axes[a].config = ac
    # tips
    robot.tips = build_tips(cfg.get("tips", []))
    # labware placed on named slots
    for lw in cfg.get("labware", []):
        robot.load_labware(build_labware(lw), str(lw["slot"]))
    # mounted tools
    for side_name, tool_cfg in cfg.get("mounts", {}).items():
        if tool_cfg.get("type") == "pipette":
            robot.attach(_SIDES[side_name], _build_pipette(tool_cfg))
        elif tool_cfg.get("type") == "ultrasonic":
            robot.attach(_SIDES[side_name], _build_ultrasonic(tool_cfg))
    return robot
