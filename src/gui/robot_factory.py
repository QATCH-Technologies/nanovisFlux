"""Builds a Robot from a config dict for a *transport the GUI already chose*.

This mirrors ``config.loader.load_robot`` almost exactly, but deliberately
does not use ``loader.build_transport`` / the YAML's own ``transport:``
section: the whole point of the connection bar is to let an operator pick
simulated vs. real (and which COM port) independently of whatever a given
config file happens to say, so the same configs/robot.yaml can be pointed
at either SimulatedTransport or a real SerialTransport.
"""

from __future__ import annotations

from ..config.loader import (
    build_axes,
    build_calibration,
    build_deck,
    build_labware,
    build_tips,
)
from ..core import MountSide
from ..robot import Robot
from ..tools import Pipette, PlungerModel, TouchProbe, UltrasonicSensor

_SIDES = {"left": MountSide.LEFT, "right": MountSide.RIGHT, "rear": MountSide.REAR}


def _pipette_from_cfg(cfg: dict, tip_calibrations: dict | None = None) -> Pipette:
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


def _ultrasonic_from_cfg(cfg: dict) -> UltrasonicSensor:
    return UltrasonicSensor(
        max_range_mm=cfg.get("max_range_mm", 4000.0),
        name=cfg.get("name", "ultrasonic"),
        brand=cfg.get("brand", ""),
    )


def _touch_probe_from_cfg(cfg: dict) -> TouchProbe:
    return TouchProbe(
        name=cfg.get("name", "touch-probe"),
        length_mm=cfg.get("length_mm", 0.0),
        brand=cfg.get("brand", ""),
    )


def build_robot(cfg: dict | None, transport) -> Robot:
    """``cfg`` is a parsed config dict (or None for a bare robot with no deck
    or calibration -- still enough to jog once axes are homed)."""
    cfg = cfg or {}
    calibration = build_calibration(cfg["calibration"]) if "calibration" in cfg else None
    deck = build_deck(cfg["deck"]) if "deck" in cfg else None

    robot = Robot(
        transport,
        calibration=calibration,
        deck=deck,
        travel_z_mm=cfg.get("travel_z_mm", 60.0),
        timeout=cfg.get("timeout", 30.0),
    )
    for a, ac in build_axes(cfg.get("axes", {})).items():
        robot.axes[a].config = ac
    robot.tips = build_tips(cfg.get("tips", []))
    for lw in cfg.get("labware", []):
        robot.load_labware(build_labware(lw), str(lw["slot"]), key=lw.get("instance"))
    pipette_tip_calibrations = cfg.get("_pipette_tip_calibrations", {})
    for side_name, tool_cfg in cfg.get("mounts", {}).items():
        if tool_cfg.get("type") == "pipette":
            robot.attach(
                _SIDES[side_name],
                _pipette_from_cfg(tool_cfg, pipette_tip_calibrations.get(side_name)),
            )
        elif tool_cfg.get("type") == "ultrasonic":
            robot.attach(_SIDES[side_name], _ultrasonic_from_cfg(tool_cfg))
        elif tool_cfg.get("type") == "touch_probe":
            robot.attach(_SIDES[side_name], _touch_probe_from_cfg(tool_cfg))
    return robot
