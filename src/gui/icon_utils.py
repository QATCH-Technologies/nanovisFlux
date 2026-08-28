from __future__ import annotations

from pathlib import Path

from PyQt5 import QtCore, QtGui

_ICONS_DIR = Path(__file__).parent / "icons"
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


def tinted_icon(
    path: Path | str, color: QtGui.QColor, size: int = 18, rotation: float = 0
) -> QtGui.QIcon:
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
    return tinted_icon(ICONS[name], color, size, rotation)
