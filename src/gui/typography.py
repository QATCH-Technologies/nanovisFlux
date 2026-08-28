from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

from PyQt5 import QtGui

FONT_SANS_STACK = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
FONT_MONO_STACK = 'Consolas, "Courier New", monospace'

QT_SANS_FAMILIES = ["Segoe UI", "Roboto", "Helvetica", "Arial"]


class TypeSpec(NamedTuple):

    size: str
    weight: int = 400
    letter_spacing: Optional[str] = None
    transform: Optional[str] = None


TYPE_DISPLAY = TypeSpec("16pt", 600, "0.5px")
TYPE_TITLE = TypeSpec("14px", 700)
TYPE_CARD_TITLE = TypeSpec("14pt", 700)
TYPE_SECTION_TITLE = TypeSpec("13px", 600)
TYPE_BODY = TypeSpec("13px", 400)
TYPE_FIELD = TypeSpec("12.5px", 600)
TYPE_MONO_PREVIEW = TypeSpec("12.5px", 400)
TYPE_DESC = TypeSpec("12px", 400)
TYPE_CAPTION = TypeSpec("10px", 600, "0.5px", "uppercase")
TYPE_ERROR = TypeSpec("8.5pt", 600)
TYPE_TOOLTIP = TypeSpec("9pt", 400)
TYPE_TOOLTIP_SUB = TypeSpec("8pt", 400)


def font_css(spec: TypeSpec, *, family: Optional[str] = None) -> str:
    parts = []
    if family is not None:
        parts.append(f"font-family: {family};")
    parts.append(f"font-size: {spec.size};")
    if spec.weight != 400:
        parts.append(f"font-weight: {spec.weight};")
    if spec.transform:
        parts.append(f"text-transform: {spec.transform};")
    if spec.letter_spacing:
        parts.append(f"letter-spacing: {spec.letter_spacing};")
    return " ".join(parts)


def make_qfont(
    *,
    families: Sequence[str] = QT_SANS_FAMILIES,
    style_hint: QtGui.QFont.StyleHint = QtGui.QFont.SansSerif,
    pixel_size: Optional[int] = None,
    point_size: Optional[float] = None,
    weight: Optional[int] = None,
    italic: bool = False,
) -> QtGui.QFont:
    font = QtGui.QFont()
    font.setFamilies(list(families))
    font.setStyleHint(style_hint)
    if pixel_size is not None:
        font.setPixelSize(pixel_size)
    if point_size is not None:
        font.setPointSizeF(point_size)
    if weight is not None:
        font.setWeight(weight)
    if italic:
        font.setItalic(True)
    return font
