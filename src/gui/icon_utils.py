"""Tinted SVG icons for the GUI, replacing inline emoji/unicode glyphs.

`tinted_icon` ports NanovisQ's `QATCH.ui.components.icon_utils.tinted_icon`:
render the source SVG to a pixmap, then recolor every opaque pixel via
`QPainter.CompositionMode_SourceAtop`. This works regardless of whatever
color is baked into the SVG file itself (all 13 icons under `icons/` are
plain stroke="#1C274C" line art from SVG Repo), so a single icon file can
be tinted differently per call site -- ink on a plain panel button, white
on the red e-stop button, muted grey for a "disconnected" state -- without
maintaining multiple colored copies of each asset.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5 import QtCore, QtGui

_ICONS_DIR = Path(__file__).parent / "icons"

#: semantic name -> SVG path. Add new icons here as they're dropped into
#: icons/, rather than scattering _ICONS_DIR joins across call sites.
ICONS: dict[str, Path] = {
    "gamepad": _ICONS_DIR / "gamepad.svg",
    "keyboard": _ICONS_DIR / "keyboard.svg",
    "home": _ICONS_DIR / "home.svg",
    "power": _ICONS_DIR / "power.svg",
    "usb": _ICONS_DIR / "usb.svg",
    "settings": _ICONS_DIR / "settings.svg",
    "minus_circle": _ICONS_DIR / "minus-circle.svg",
    "add_circle": _ICONS_DIR / "add-circle.svg",
    "star_circle": _ICONS_DIR / "star-circle.svg",
    "chevron": _ICONS_DIR / "chevron.svg",
    "restart_circle": _ICONS_DIR / "restart-circle.svg",
    "controller_connect": _ICONS_DIR / "controller-connect.svg",
    "square_circle": _ICONS_DIR / "square-circle.svg",
}


def tinted_icon(path: Path | str, color: QtGui.QColor, size: int = 18, rotation: float = 0) -> QtGui.QIcon:
    """Solid-color, optionally-rotated version of an icon.

    `rotation` (degrees, clockwise) is applied to the source pixmap before
    tinting -- e.g. reusing chevron.svg (one drawn "down" arrow) as up/down/
    left/right by rotating 0/180/270/90, instead of needing four separate
    directional assets.
    """
    src = QtGui.QIcon(str(path)).pixmap(size, size)
    if rotation:
        src = src.transformed(QtGui.QTransform().rotate(rotation), QtCore.Qt.SmoothTransformation)
    dst = QtGui.QPixmap(src.size())
    dst.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(dst)
    p.drawPixmap(0, 0, src)
    p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
    p.fillRect(dst.rect(), color)
    p.end()
    return QtGui.QIcon(dst)


def icon(name: str, color: QtGui.QColor, size: int = 18, rotation: float = 0) -> QtGui.QIcon:
    """`tinted_icon` looked up by the semantic name in `ICONS`."""
    return tinted_icon(ICONS[name], color, size, rotation)
