"""
Geometric and mechanical definitions for pipette-tip handling.

This module defines immutable physical metadata for disposable tips and
configurable motion parameters for mechanically seating tips during pickup.

:class:`TipGeometry` describes the physical dimensions that affect deck-space
motion and pipetting compatibility, while :class:`TipPickup` describes the
press, retract, and optional well-wall touch sequence used to seat a tip
securely on a pipette mount.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TipGeometry:
    """Describe the physical geometry and capacity of a pipette tip.

    `TipGeometry` contains the physical properties needed to account for a
    tip's geometry when positioning a mounted pipette. The tip length is
    measured from the pipette nozzle reference plane to the tip's contact end
    and therefore acts as the Z-axis offset applied after the tip is installed.

    Tip geometry is immutable because it represents a physical tip type rather
    than mutable state. Calibration remains tied to the nozzle reference
    system, so changing tips changes only the active tip geometry and does not
    require recalibrating the robot.

    Args:
        name: Identifier for the tip geometry or tip type.
        length_mm: Distance in millimeters from the pipette nozzle reference
            plane to the tip's contact end.
        max_volume_ul: Maximum nominal liquid volume in microliters. Defaults
            to `0.0` when capacity is unspecified.
        inner_diameter_mm: Tip inner diameter in millimeters. Defaults to
            `0.0` when unspecified.
        brand: Tip manufacturer or vendor name. May be empty when unknown or
            when the tip is custom.

    Attributes:
        name: Identifier for the tip geometry or tip type.
        length_mm: Tip length from the nozzle reference plane to the contact
            end, in millimeters.
        max_volume_ul: Maximum nominal tip volume in microliters.
        inner_diameter_mm: Tip inner diameter in millimeters.
        brand: Tip manufacturer or vendor name.
    """

    name: str
    length_mm: float
    max_volume_ul: float = 0.0
    inner_diameter_mm: float = 0.0
    brand: str = ""


@dataclass
class TipPickup:
    """Define the mechanical parameters for seating a pipette tip.

    `TipPickup` describes the motion sequence used to press a pipette nozzle
    into a tip and mechanically seat it. The nozzle first moves to
    `press_z_mm`, then performs the configured number of downward engagement
    strokes, lifting between strokes.

    An optional lateral touch pattern can then be used to square the seated
    tip against the walls of the tip-rack well. The pattern consists of
    sequential left, right, front, and back lateral movements. Setting
    `touch_offset_mm` to `0` disables this alignment step.

    The dataclass is mutable so pickup parameters can be adjusted for
    different tip racks, tip types, or mechanical conditions.

    Args:
        press_z_mm: Deck-space Z height of the top of the tip at first contact.
        engage_mm: Downward travel below `press_z_mm` for each seating
            stroke, in millimeters.
        retract_mm: Upward travel between seating strokes, in millimeters.
        presses: Number of downward seating strokes to perform.
        feed: Vertical motion feed rate used for seating and retract strokes,
            in controller units.
        touch_offset_mm: Lateral distance used for the optional four-direction
            well-wall touch pattern, in millimeters. Set to `0` to disable
            the touch pattern.
        touch_retract_mm: Distance to retract upward before performing the
            lateral touch pattern. If `None`, the pickup implementation
            should use half of `engage_mm`.
        touch_feed: Feed rate for the lateral touch pattern. If `None`,
            the pickup implementation should use `feed`.

    Attributes:
        press_z_mm: Deck-space Z height of initial tip contact.
        engage_mm: Downward seating distance per press.
        retract_mm: Vertical lift between seating presses.
        presses: Number of seating presses.
        feed: Feed rate for vertical pickup motions.
        touch_offset_mm: Lateral displacement for well-wall alignment.
        touch_retract_mm: Vertical retraction before the touch pattern, or
            `None` to derive it from `engage_mm`.
        touch_feed: Feed rate for the touch pattern, or `None` to reuse
            `feed`.
    """

    press_z_mm: float
    engage_mm: float = 3.0
    retract_mm: float = 2.0
    presses: int = 2
    feed: int = 9000
    touch_offset_mm: float = 1.5
    touch_retract_mm: float | None = None
    touch_feed: int | None = None
