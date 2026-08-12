"""Loads and resolves app_theme.qss for the nanovisFlux control GUI.

The QSS itself lives in app_theme.qss (colors/typography as {{PLACEHOLDER}}
tokens); this module is the substitution step -- mirrors NanovisQ's
StyleLoader._substitute_tokens, scaled down for a single-theme app (no
runtime theme switching, so no cache invalidation/reload machinery, and no
icon-path substitution -- icons are loaded directly in Python via
icon_utils.icon(), not through QSS).
"""
from __future__ import annotations

from pathlib import Path

from .tokens import TOKENS
from .typography import FONT_MONO_STACK, FONT_SANS_STACK, QT_SANS_FAMILIES

_QSS_PATH = Path(__file__).parent / "app_theme.qss"


def _tok_css(rgba) -> str:
    """(r, g, b, a) -> a literal CSS color -- hex when fully opaque (the
    common case; QSS `border-color`/selector shorthand reads better as hex),
    rgba(...) otherwise."""
    r, g, b, a = rgba
    if a == 255:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"rgba({r}, {g}, {b}, {a})"


# Plain hex/name constants for call sites that paint directly with QPainter
# (deck_view.py, slot_detail_view.py) rather than through QSS -- QColor/QFont
# need a literal string, not a {{PLACEHOLDER}}, so these are the same
# tokens.TOKENS values pre-rendered once at import time.
PANEL = _tok_css(TOKENS["flat_surface"])
PANEL_ALT = _tok_css(TOKENS["flat_surface2"])
INK = _tok_css(TOKENS["flat_text"])
INK_MUTED = _tok_css(TOKENS["flat_text_muted"])
BORDER = _tok_css(TOKENS["flat_border"])
BORDER_STRONG = _tok_css(TOKENS["flat_border_strong"])
ACCENT_GREEN = _tok_css(TOKENS["flat_success"])
ACCENT_AMBER = _tok_css(TOKENS["flat_warning"])
ACCENT_RED = _tok_css(TOKENS["flat_error"])
UI_FONT = QT_SANS_FAMILIES[0]  # "Segoe UI" -- a single Qt-actionable family, not the whole CSS stack
MONO_FONT = "Consolas"  # first entry of typography.FONT_MONO_STACK, same reasoning as UI_FONT


def load_stylesheet() -> str:
    """Reads app_theme.qss and substitutes every {{TOKEN}} placeholder --
    color tokens from tokens.TOKENS, plus FONT_SANS/FONT_MONO from
    typography's font stacks -- into the literal CSS QApplication.
    setStyleSheet() expects."""
    qss = _QSS_PATH.read_text(encoding="utf-8")
    for key, value in TOKENS.items():
        qss = qss.replace(f"{{{{{key.upper()}}}}}", _tok_css(value))
    # FONT_SANS_STACK / FONT_MONO_STACK are already complete, validly-quoted
    # CSS font-family values (e.g. "system-ui, ..., 'Segoe UI', ..."), so
    # substituting as-is -- not wrapped in another quote pair -- is correct.
    qss = qss.replace("{{FONT_SANS}}", FONT_SANS_STACK)
    qss = qss.replace("{{FONT_MONO}}", FONT_MONO_STACK)
    return qss
