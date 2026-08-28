from __future__ import annotations

from pathlib import Path

from .tokens import TOKENS
from .typography import FONT_MONO_STACK, FONT_SANS_STACK, QT_SANS_FAMILIES

_QSS_PATH = Path(__file__).parent / "app_theme.qss"


def _tok_css(rgba) -> str:
    r, g, b, a = rgba
    if a == 255:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"rgba({r}, {g}, {b}, {a})"


PANEL = _tok_css(TOKENS["flat_surface"])
PANEL_ALT = _tok_css(TOKENS["flat_surface2"])
INK = _tok_css(TOKENS["flat_text"])
INK_MUTED = _tok_css(TOKENS["flat_text_muted"])
BORDER = _tok_css(TOKENS["flat_border"])
BORDER_STRONG = _tok_css(TOKENS["flat_border_strong"])
ACCENT_GREEN = _tok_css(TOKENS["flat_success"])
ACCENT_AMBER = _tok_css(TOKENS["flat_warning"])
ACCENT_RED = _tok_css(TOKENS["flat_error"])
UI_FONT = QT_SANS_FAMILIES[0]
MONO_FONT = "Consolas"


def load_stylesheet() -> str:
    qss = _QSS_PATH.read_text(encoding="utf-8")
    for key, value in TOKENS.items():
        qss = qss.replace(f"{{{{{key.upper()}}}}}", _tok_css(value))
    qss = qss.replace("{{FONT_SANS}}", FONT_SANS_STACK)
    qss = qss.replace("{{FONT_MONO}}", FONT_MONO_STACK)
    return qss
