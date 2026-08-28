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
from ..transport import SerialTransport, SimulatedTransport

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT, "rear": MountSide.REAR}


def load_config(path: str) -> dict:
    """Load a YAML configuration file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        The parsed YAML document as a dictionary.
    """
    import yaml

    with open(path, "r") as fh:
        return yaml.safe_load(fh)


def calibration_sidecar_path(config_path) -> Path:
    """Return the path to the persisted calibration sidecar for a config.

    The sidecar uses the same directory and base filename as the source
    configuration, with ``.calibration`` inserted before the original
    suffix. For example, ``robot.yaml`` maps to
    ``robot.calibration.yaml``.

    Args:
        config_path: Path to the primary robot configuration file.

    Returns:
        Path where the corresponding calibration sidecar is stored.
    """
    p = Path(config_path)
    return p.with_suffix(f".calibration{p.suffix}")


def load_calibration_override(config_path) -> dict | None:
    """Load a persisted calibration override for a robot configuration.

    The override is read from the calibration sidecar associated with
    ``config_path``. If the sidecar contains a top-level ``calibration``
    section, that section is returned; otherwise the entire file contents
    are treated as the calibration configuration.

    Args:
        config_path: Path to the primary robot configuration file.

    Returns:
        The calibration configuration, or ``None`` if no sidecar exists.
    """
    sidecar = calibration_sidecar_path(config_path)
    if not sidecar.exists():
        return None
    cfg = load_config(str(sidecar))
    return cfg.get("calibration", cfg)


def _load_section_ref(base_dir: Path, value, wrapper_key: str):
    """Resolve an inline configuration section or a YAML file reference.

    Non-string values are returned unchanged. String values are interpreted
    as paths relative to ``base_dir`` and loaded as YAML. Referenced files
    may either contain the section directly or wrap it under ``wrapper_key``.

    Args:
        base_dir: Directory relative to which referenced paths are resolved.
        value: Inline section data or a relative YAML file path.
        wrapper_key: Optional top-level key under which the referenced
            section may be stored.

    Returns:
        The resolved configuration section.
    """
    if not isinstance(value, str):
        return value
    loaded = load_config(str(base_dir / value))
    return loaded.get(wrapper_key, loaded)


def _check_name_matches(declared_name, loaded: dict, file_path: Path, kind: str) -> None:
    """Validate that a referenced object's declared and loaded names agree.

    Args:
        declared_name: Name declared by the referencing configuration.
        loaded: Configuration loaded from the referenced file.
        file_path: Path to the referenced configuration file.
        kind: Human-readable configuration category used in the error
            message.

    Raises:
        ValueError: If both names are present and do not match.
    """
    actual_name = loaded.get("name")
    if declared_name is not None and actual_name is not None and declared_name != actual_name:
        raise ValueError(
            f"{kind} reference declares name {declared_name!r} but {file_path} is "
            f"itself named {actual_name!r} -- keep the two in sync"
        )


def _resolve_tips_refs(base_dir: Path, cfg_list: list) -> list:
    """Resolve inline and file-referenced tip configurations.

    Tip entries may be inline dictionaries, bare YAML paths, or dictionaries
    containing ``name`` and ``config`` fields. Referenced configurations are
    resolved relative to ``base_dir`` and may optionally be wrapped under a
    ``tip`` key.

    Args:
        base_dir: Directory containing the robot configuration.
        cfg_list: Tip configuration entries from the robot configuration.

    Returns:
        A list of fully resolved inline tip configuration dictionaries.
    """
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
    """Resolve reusable labware definition references.

    Referenced labware definitions are loaded relative to ``base_dir`` and
    merged with the placement-specific ``slot``. Optional instance names
    are preserved so the same labware definition can be placed multiple
    times.

    Args:
        base_dir: Directory containing the robot configuration.
        cfg_list: Labware configuration entries.

    Returns:
        A list of fully resolved labware configuration dictionaries.
    """
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
    """Resolve inline and file-referenced mounted tool configurations.

    Referenced tool definitions are loaded relative to ``base_dir``.
    Pipette references additionally cause any associated per-tip plunger
    calibrations to be discovered.

    Args:
        base_dir: Directory containing the robot configuration.
        cfg_dict: Mapping of mount side names to tool configurations.

    Returns:
        A tuple containing the resolved mount configuration mapping and a
        mapping of mount sides to discovered pipette tip calibrations.
    """
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
    """Load and fully resolve a robot configuration.

    Inline sections and sections referenced by separate YAML files are
    normalized into the same fully inline structure consumed by the object
    builders. Referenced paths are resolved relative to the robot
    configuration file rather than the process working directory.

    Args:
        path: Path to the primary robot YAML configuration.

    Returns:
        A fully resolved robot configuration dictionary.
    """
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


def build_transport(cfg: dict):
    """Construct a transport from its configuration.

    Args:
        cfg: Transport configuration containing the transport ``type`` and
            any type-specific connection parameters.

    Returns:
        A configured transport instance.

    Raises:
        NotImplementedError: If ``type`` is ``"tcp"``.
        ValueError: If the transport type is unknown.
    """
    kind = cfg.get("type", "simulated")
    if kind == "serial":
        return SerialTransport(cfg["port"], cfg.get("baudrate", 115200), cfg.get("timeout", 30.0))
    if kind == "simulated":
        return SimulatedTransport()
    if kind == "tcp":
        raise NotImplementedError("add a TCPTransport and wire it here")
    raise ValueError(f"unknown transport type: {kind}")


def _axis_resonance_warnings(cfg: AxisConfig) -> list:
    """Generate warnings for configured speeds inside resonance bands.

    The check considers the axis's steady-state travel and homing speeds,
    rather than transient speeds encountered during acceleration or
    deceleration.

    Args:
        cfg: Axis configuration to inspect.

    Returns:
        Human-readable warning messages for speeds that fall within one of
        the axis's configured resonance bands.
    """
    warnings = []
    for label, value in (("travel_speed", cfg.travel_speed), ("homing_speed", cfg.homing_speed)):
        band = feed_in_resonance_band(value, cfg.resonance_bands_hz)
        if band is not None:
            warnings.append(
                f"axis {cfg.axis.letter}: {label} ({value:g} microsteps/s) falls inside its "
                f"own configured resonance_bands_hz {band} Hz"
            )
    return warnings


def build_axes(cfg: dict) -> dict:
    """Build axis configurations from firmware defaults and YAML overrides.

    Args:
        cfg: Mapping of axis letters to per-axis configuration overrides.

    Returns:
        A mapping from :class:`AxisId` to fully populated
        :class:`AxisConfig` objects.
    """
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
    """Load a deck calibration from a YAML file.

    The file may contain a complete robot configuration with a
    ``calibration`` section or may consist solely of the calibration
    section.

    Args:
        path: Path to the calibration or robot configuration file.

    Returns:
        The constructed :class:`DeckCalibration`.
    """
    cfg = load_config(path)
    return build_calibration(cfg.get("calibration", cfg))


def build_calibration(cfg: dict) -> DeckCalibration:
    """Build a deck calibration from configuration data.

    An explicit affine transform is used when ``affine`` is provided.
    Otherwise, the XY transform is fitted from deck and motor calibration
    point pairs. The vertical scale and per-mount Z-zero values are then
    constructed from the corresponding configuration entries.

    Args:
        cfg: Deck calibration configuration.

    Returns:
        A configured :class:`DeckCalibration`.
    """
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
    """Load a pipette plunger calibration from a YAML file.

    The file may contain a complete configuration with a
    ``pipette_calibration`` section or may consist solely of that section.

    Args:
        path: Path to the pipette calibration file.

    Returns:
        The constructed :class:`PlungerCalibration`.
    """
    cfg = load_config(path)
    return build_pipette_calibration(cfg.get("pipette_calibration", cfg))


def build_pipette_calibration(cfg: dict) -> PlungerCalibration:
    """Build a pipette plunger calibration from measured volume pairs.

    Args:
        cfg: Configuration containing separate ``aspirate`` and ``dispense``
            microstep-to-volume calibration pairs.

    Returns:
        The constructed :class:`PlungerCalibration`.
    """
    return PlungerCalibration.from_pairs(
        aspirate=[(p["microsteps"], p["volume_ul"]) for p in cfg["aspirate"]],
        dispense=[(p["microsteps"], p["volume_ul"]) for p in cfg["dispense"]],
    )


def build_pipette_tip_calibrations(pipette_dir: Path, pipette_name: str) -> dict:
    """Load all measured tip-specific calibrations for a pipette.

    Calibration files are discovered from the pipette's
    ``calibrations`` directory. Each file may identify its pipette name;
    when present, that declaration must match ``pipette_name``.

    Args:
        pipette_dir: Directory containing the pipette's definition
            directory.
        pipette_name: Name of the pipette whose calibrations are loaded.

    Returns:
        A mapping from tip name to :class:`PlungerCalibration`. Returns an
        empty dictionary when no calibration directory exists.

    Raises:
        ValueError: If a calibration file declares a different pipette
            name from the directory in which it resides.
    """
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
    """Build slot obstacles from configuration data.

    Args:
        cfg: Sequence of obstacle dictionaries containing offsets, sizes,
            and heights.

    Returns:
        A list of :class:`SlotObstacle` instances.
    """
    return [
        SlotObstacle(offset=tuple(o["offset"]), size=tuple(o["size"]), height_mm=o["height_mm"])
        for o in (cfg or [])
    ]


def _build_calibration_marks(cfg: dict | None, slots: dict) -> dict:
    """Build named deck calibration marks from slot-relative definitions.

    Each mark is resolved from a named slot, corner, and configured inset,
    allowing calibration points to remain tied to the deck geometry rather
    than storing absolute coordinates.

    Args:
        cfg: Calibration-mark configuration, or ``None`` when marks are
            not configured.
        slots: Mapping of deck slot names to :class:`Slot` instances.

    Returns:
        A mapping from calibration-mark name to :class:`CalibrationMark`.
    """
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
    """Build a deck and its slots from configuration data.

    The configuration may describe either a regular slot grid or an
    explicit collection of slots. Optional margins, enclosure dimensions,
    obstacles, and calibration marks are also applied.

    Args:
        cfg: Deck configuration dictionary.

    Returns:
        A fully constructed :class:`Deck`.
    """
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
    """Build labware from its configuration dictionary.

    Args:
        cfg: Labware definition containing either a regular grid
            specification or explicit well definitions.

    Returns:
        The constructed :class:`Labware`.
    """
    return Labware.from_dict(cfg)


def build_tips(cfg: list) -> dict:
    """Build tip geometries from configuration data.

    Args:
        cfg: Sequence of tip definitions containing names, lengths, and
            optional volume, diameter, and brand information.

    Returns:
        A mapping from tip name to :class:`TipGeometry`.
    """
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
    """Build a pipette from its configuration.

    Args:
        cfg: Pipette configuration containing plunger characteristics,
            capacity, and optional metadata.
        tip_calibrations: Optional mapping of tip names to measured
            plunger calibrations.

    Returns:
        A configured :class:`Pipette`.
    """
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
    """Build an ultrasonic sensor from configuration data.

    Args:
        cfg: Ultrasonic sensor configuration.

    Returns:
        A configured :class:`UltrasonicSensor`.
    """
    return UltrasonicSensor(
        max_range_mm=cfg.get("max_range_mm", 4000.0),
        name=cfg.get("name", "ultrasonic"),
        brand=cfg.get("brand", ""),
    )


def _build_touch_probe(cfg: dict) -> TouchProbe:
    """Build a touch probe from configuration data.

    Args:
        cfg: Touch-probe configuration.

    Returns:
        A configured :class:`TouchProbe`.
    """
    return TouchProbe(
        name=cfg.get("name", "touch-probe"),
        length_mm=cfg.get("length_mm", 0.0),
        brand=cfg.get("brand", ""),
    )


def load_robot(path: str) -> Robot:
    """Load a complete robot configuration and construct a ready Robot.

    The configuration is first resolved into a fully inline representation.
    Any persisted calibration sidecar then overrides the calibration
    contained in the primary configuration. Transports, calibration,
    deck, axes, tips, labware, and mounted tools are subsequently
    constructed and attached to the robot.

    Args:
        path: Path to the primary robot YAML configuration.

    Returns:
        A fully configured :class:`Robot` ready for use.

    Raises:
        ValueError: If any configuration section contains an invalid or
            unsupported value.
        NotImplementedError: If the configuration requests an unsupported
            transport type.
    """
    cfg = resolve_robot_config(path)
    override = load_calibration_override(path)
    if override is not None:
        cfg = {**cfg, "calibration": override}
    transport = build_transport(cfg.get("transport", {"type": "simulated"}))
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
