"""Build the whole object graph from a YAML file, so nothing is hard-coded.

Every builder takes a plain dict (one YAML section) and returns domain
objects, and ``load_robot`` wires them into a ready Robot. PyYAML is imported
lazily, so importing this module never requires it.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from ..core import AxisId, MountSide
from ..deck import (
    CalibrationMark,
    Corner,
    Deck,
    Labware,
    Slot,
    SlotObstacle,
    inset_corner_point,
)
from ..geometry import AffineTransform2D, AxisScale, DeckCalibration, DeckPoint
from ..motion.axis import AxisConfig, default_axis_configs
from ..motion.resonance import feed_in_resonance_band
from ..robot import Robot
from ..tools import (
    Pipette,
    PlungerCalibration,
    PlungerModel,
    TipGeometry,
    TouchProbe,
    UltrasonicSensor,
)
from ..transport import FakeTransport, SerialTransport

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT, "rear": MountSide.REAR}


def load_config(path: str) -> dict:
    import yaml  # lazy dependency

    with open(path, "r") as fh:
        return yaml.safe_load(fh)


def calibration_sidecar_path(config_path) -> Path:
    """Where a calibration persisted from the GUI's "Save calibration..."
    button (see gui/calibration_dialog.py) lives for ``config_path`` --
    e.g. "robot.yaml" -> "robot.calibration.yaml", sitting right next to
    it. Deliberately a separate file rather than writing back into the
    config itself: config files like configs/robot.yaml are hand-authored
    and heavily commented, and round-tripping one through yaml.safe_load /
    safe_dump to patch in a new calibration would silently strip every
    comment. Connecting with the same config_path picks this sidecar up
    automatically (see load_calibration_override) if one exists, so a
    recalibration persists across reconnects without ever touching the
    original file."""
    p = Path(config_path)
    return p.with_suffix(f".calibration{p.suffix}")


def load_calibration_override(config_path) -> dict | None:
    """The ``calibration:`` section from config_path's sidecar file (see
    calibration_sidecar_path), or None if there isn't one yet -- the normal
    case before the deck has ever been calibrated from the GUI."""
    sidecar = calibration_sidecar_path(config_path)
    if not sidecar.exists():
        return None
    cfg = load_config(str(sidecar))
    return cfg.get("calibration", cfg)


# -- split-file config resolution --------------------------------------------
#
# A robot config's axes/calibration/deck/tips/labware/mounts sections can
# each be given two ways:
#   - inline (a dict, or for tips/labware a list of dicts) -- the original,
#     single-file convention; an existing single-file config keeps working
#     with zero edits (see test_split_config_loader.py's
#     test_resolve_robot_config_leaves_inline_sections_untouched).
#   - as a path (string, resolved relative to the referencing file's own
#     directory -- NOT the process cwd) to that section's own YAML file, so
#     one axes/calibration/deck/tool/tip/labware profile can be measured
#     once and reused by name across multiple robot configs instead of
#     copy-pasted. See configs/robot.yaml for the split-file convention
#     this enables.
#
# resolve_robot_config() is the only entry point that needs to know about
# this: it turns any mix of inline/referenced sections into the fully-inline
# dict shape build_transport/build_axes/build_calibration/build_deck/
# build_labware/build_tips/load_robot's mounts loop have always consumed, so
# nothing downstream (including the GUI's build_robot) needs to change.


def _load_section_ref(base_dir: Path, value, wrapper_key: str):
    """``value`` is either an inline section (returned as-is) or a path to a
    standalone YAML file for it, resolved against ``base_dir``. A standalone
    file may itself wrap the section under ``wrapper_key:`` (self-documenting,
    and consistent with how a calibration sidecar file reads) or just BE the
    section at the top level -- same fallback convention as
    load_calibration_override/load_calibration already use."""
    if not isinstance(value, str):
        return value
    loaded = load_config(str(base_dir / value))
    return loaded.get(wrapper_key, loaded)


def _check_name_matches(declared_name, loaded: dict, file_path: Path, kind: str) -> None:
    """A reference entry (in robot.yaml's tips:/labware:/mounts:) may declare
    the ``name:`` it expects to find -- enforced here so the object (the
    referenced file's own ``name:``), the config (this declared name), and
    the file name stay in sync by construction rather than by convention:
    a rename on one side without the other fails loudly instead of quietly
    drifting."""
    actual_name = loaded.get("name")
    if declared_name is not None and actual_name is not None and declared_name != actual_name:
        raise ValueError(
            f"{kind} reference declares name {declared_name!r} but {file_path} is "
            f"itself named {actual_name!r} -- keep the two in sync"
        )


def _resolve_tips_refs(base_dir: Path, cfg_list: list) -> list:
    """Each entry is an inline tip dict (has its own ``name``/``length_mm``,
    no ``config``), a bare path string, or ``{name, config}`` -- the latter
    two load the tip's own file (resolved against ``base_dir``); ``{name,
    config}`` additionally checks that declared ``name`` against the file's
    own, so the tip's identity can't silently drift out of sync between
    robot.yaml and the file it points at."""
    resolved = []
    for item in cfg_list or []:
        if isinstance(item, str):
            loaded = load_config(str(base_dir / item))
            resolved.append(loaded.get("tip", loaded))
        elif isinstance(item, dict) and "config" in item:
            file_path = base_dir / item["config"]
            loaded = load_config(str(file_path))
            loaded = loaded.get("tip", loaded)
            _check_name_matches(item.get("name"), loaded, file_path, "tips:")
            resolved.append(loaded)
        else:
            resolved.append(item)
    return resolved


def _resolve_labware_refs(base_dir: Path, cfg_list: list) -> list:
    """Each entry is either an old-style inline labware dict (already
    carrying its own ``slot:``), or ``{slot, config, name?, instance?}``
    naming a reusable labware definition file -- the file itself holds no
    slot (matching Labware.from_dict, which never reads one), so the same
    tiprack/plate definition can sit in a different slot on a different
    robot, or in more than one slot on the same robot.

    ``instance`` (when given) carries through as the key Robot.load_labware
    registers this placement under -- needed only when the same reusable
    definition is placed more than once (each placement's ``.name`` would
    otherwise collide in ``robot.labware``); a single placement can omit it
    and fall back to the labware's own ``name``, as before. ``name`` (when
    given) is checked against the definition file's own -- see
    _check_name_matches."""
    resolved = []
    for item in cfg_list or []:
        if isinstance(item, dict) and "config" in item:
            file_path = base_dir / item["config"]
            loaded = load_config(str(file_path))
            loaded = loaded.get("labware", loaded)
            _check_name_matches(item.get("name"), loaded, file_path, "labware:")
            merged = {**loaded, "slot": item["slot"]}
            if "instance" in item:
                merged["instance"] = item["instance"]
            resolved.append(merged)
        else:
            resolved.append(item)
    return resolved


def _resolve_mounts_refs(base_dir: Path, cfg_dict: dict) -> tuple:
    """Each mount's value is an inline tool dict (has its own ``type``, no
    ``config``), a bare path string, or ``{name, config}`` -- the latter two
    load the tool's own file; ``{name, config}`` additionally checks the
    declared ``name`` against the file's own (see _check_name_matches).

    Returns ``(resolved, tip_calibrations)``: ``resolved`` is the same
    plain inline-tool-dict shape an inline mount would already produce
    (mounts: itself never carries calibration data, so a resolved split
    config and an inline one still compare equal -- see
    resolve_robot_config's own docstring/tests). ``tip_calibrations`` is a
    side dict-of-dicts, populated only for pipette mounts loaded from a
    file reference (see build_pipette_tip_calibrations) -- kept as a
    separate return value rather than smuggled into ``resolved`` itself."""
    resolved = {}
    tip_calibrations = {}
    for side, value in (cfg_dict or {}).items():
        file_path = None
        if isinstance(value, str):
            file_path = base_dir / value
            loaded = load_config(str(file_path))
            resolved[side] = loaded.get("mount", loaded)
        elif isinstance(value, dict) and "config" in value:
            file_path = base_dir / value["config"]
            loaded = load_config(str(file_path))
            loaded = loaded.get("mount", loaded)
            _check_name_matches(value.get("name"), loaded, file_path, "mounts:")
            resolved[side] = loaded
        else:
            resolved[side] = value
        if file_path is not None and resolved[side].get("type") == "pipette":
            tip_calibrations[side] = build_pipette_tip_calibrations(
                file_path.resolve().parent, resolved[side]["name"]
            )
    return resolved, tip_calibrations


def resolve_robot_config(path: str) -> dict:
    """Load ``path`` and follow any file-reference sections, returning the
    same fully-inline dict shape a single monolithic config has always
    produced. Both load_robot and the GUI's connect flow go through this so
    a split-file config and an inline, single-file one behave identically
    from here down."""
    cfg = load_config(path)
    base_dir = Path(path).resolve().parent
    resolved = dict(cfg)
    if "axes" in cfg:
        resolved["axes"] = _load_section_ref(base_dir, cfg["axes"], "axes")
    if "calibration" in cfg:
        resolved["calibration"] = _load_section_ref(base_dir, cfg["calibration"], "calibration")
    if "deck" in cfg:
        resolved["deck"] = _load_section_ref(base_dir, cfg["deck"], "deck")
    if "tips" in cfg:
        resolved["tips"] = _resolve_tips_refs(base_dir, cfg["tips"])
    if "labware" in cfg:
        resolved["labware"] = _resolve_labware_refs(base_dir, cfg["labware"])
    if "mounts" in cfg:
        resolved["mounts"], resolved["_pipette_tip_calibrations"] = _resolve_mounts_refs(
            base_dir, cfg["mounts"]
        )
    return resolved


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


def _axis_resonance_warnings(cfg: AxisConfig) -> list:
    """Human-readable warnings for any of ``cfg``'s own steady-state speeds
    (travel_speed, homing_speed) that sit inside its own configured
    resonance_bands_hz -- i.e. this axis's normal operating speed IS the
    bad-sounding frequency, not just something a jog might transiently pass
    through. A pure function (no logging here) so it's testable without
    intercepting loguru; build_axes logs whatever this returns."""
    warnings = []
    for label, value in (("travel_speed", cfg.travel_speed), ("homing_speed", cfg.homing_speed)):
        band = feed_in_resonance_band(value, cfg.resonance_bands_hz)
        if band is not None:
            warnings.append(
                f"axis {cfg.axis.letter}: {label} ({value:g} microsteps/s) falls inside its "
                f"own configured resonance_bands_hz {band} Hz -- every move at this speed "
                "will ring; reconfigure travel_speed/homing_speed or the band"
            )
    return warnings


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
            resonance_bands_hz=tuple(
                tuple(band) for band in over.get("resonance_bands_hz", base.resonance_bands_hz)
            ),
        )
    for axis_cfg in axes.values():
        for warning in _axis_resonance_warnings(axis_cfg):
            logger.warning(warning)
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


def load_pipette_calibration(path: str) -> PlungerCalibration:
    """Load a pipette_calibration: section either from a full robot config
    or a standalone file -- as written by scripts/calibrate_pipette.py."""
    cfg = load_config(path)
    return build_pipette_calibration(cfg.get("pipette_calibration", cfg))


def build_pipette_calibration(cfg: dict) -> PlungerCalibration:
    return PlungerCalibration.from_pairs(
        aspirate=[(p["microsteps"], p["volume_ul"]) for p in cfg["aspirate"]],
        dispense=[(p["microsteps"], p["volume_ul"]) for p in cfg["dispense"]],
    )


def build_pipette_tip_calibrations(pipette_dir: Path, pipette_name: str) -> dict:
    """Every measured calibration for ``pipette_name``, one per
    characterized tip -- see configs/tools/pipettes/<pipette_name>/
    calibrations/*.yaml (written by scripts/calibrate_pipette.py or
    scripts/calibration_recovery.py), one file per tip, each holding a
    ``pipette_calibration:`` section in the same shape
    build_pipette_calibration reads.

    ``pipette_name`` is its own top-level directory (a sibling of that
    pipette's own <pipette_name>.yaml, both directly under
    configs/tools/pipettes/) rather than being nested inside one shared
    calibrations/ folder -- there are enough distinct pipettes in practice
    (gen1 vs. gen2, single- vs. multi-channel, ...) that each needs to be
    unambiguously its own top-level grouping, not one more entry filed
    under a generic bucket.

    Mount side doesn't affect a plunger's steps<->volume mapping (see
    PlungerCalibration) -- a pipette's calibrations are the same wherever
    it's mounted, so unlike ``mounts:`` these are never split by side.

    ``pipette_dir`` is the directory the pipette's OWN tool file lives in
    (e.g. configs/tools/pipettes/), not the robot config's -- calibrations
    stay colocated with the pipette definition they belong to, so they're
    found the same way regardless of which robot config references it.

    Returns {} if this pipette has no calibrations directory yet (the
    normal case before it's ever been characterized -- Pipette then falls
    back to its linear PlungerModel; see
    Pipette._calibration_for_current_tip)."""
    calib_dir = pipette_dir / pipette_name / "calibrations"
    if not calib_dir.is_dir():
        return {}
    calibrations = {}
    for file_path in sorted(calib_dir.glob("*.yaml")):
        section = load_config(str(file_path))
        section = section.get("pipette_calibration", section)
        declared = section.get("pipette")
        if declared is not None and declared != pipette_name:
            raise ValueError(
                f"{file_path} declares pipette {declared!r} but lives under "
                f"{pipette_name}/calibrations/ -- keep the two in sync"
            )
        calibrations[section["tip"]] = build_pipette_calibration(section)
    return calibrations


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
        marks[m["name"]] = CalibrationMark(
            name=m["name"], slot=slot.name, corner=corner, point=point
        )
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
            brand=t.get("brand", ""),
        )
    return tips


def _build_pipette(cfg: dict, tip_calibrations: dict | None = None) -> Pipette:
    return Pipette(
        name=cfg["name"],
        plunger=PlungerModel(
            microsteps_per_ul=cfg["microsteps_per_ul"],
            bottom_microsteps=cfg.get("bottom_microsteps", 0),
        ),
        max_volume_ul=cfg["max_volume_ul"],
        tip_calibrations=tip_calibrations,
        brand=cfg.get("brand", ""),
        channels=cfg.get("channels", 1),
    )


def _build_ultrasonic(cfg: dict) -> UltrasonicSensor:
    return UltrasonicSensor(
        max_range_mm=cfg.get("max_range_mm", 4000.0),
        name=cfg.get("name", "ultrasonic"),
        brand=cfg.get("brand", ""),
    )


def _build_touch_probe(cfg: dict) -> TouchProbe:
    return TouchProbe(
        name=cfg.get("name", "touch-probe"),
        length_mm=cfg.get("length_mm", 0.0),
        brand=cfg.get("brand", ""),
    )


# -- top level --------------------------------------------------------------
def load_robot(path: str) -> Robot:
    cfg = resolve_robot_config(path)
    # A calibration persisted from the GUI (see calibration_sidecar_path)
    # always wins over whatever the config file itself says -- the whole
    # point is that recalibrating from the dialog, then reconnecting with
    # this same config, never needs the operator to redo it.
    override = load_calibration_override(path)
    if override is not None:
        cfg = {**cfg, "calibration": override}
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
        robot.load_labware(build_labware(lw), str(lw["slot"]), key=lw.get("instance"))
    # mounted tools
    pipette_tip_calibrations = cfg.get("_pipette_tip_calibrations", {})
    for side_name, tool_cfg in cfg.get("mounts", {}).items():
        if tool_cfg.get("type") == "pipette":
            robot.attach(
                _SIDES[side_name],
                _build_pipette(tool_cfg, pipette_tip_calibrations.get(side_name)),
            )
        elif tool_cfg.get("type") == "ultrasonic":
            robot.attach(_SIDES[side_name], _build_ultrasonic(tool_cfg))
        elif tool_cfg.get("type") == "touch_probe":
            robot.attach(_SIDES[side_name], _build_touch_probe(tool_cfg))
    return robot
