"""
nanovisFlux.gui.tokens

Semantic color tokens for the app, ported from NanovisQ's
`QATCH.ui.styles.tokens` (see that file's own design note for the full
derived-ramp philosophy this is a trimmed descendant of). Two changes from
the source:

1. Single palette only -- nanovisFlux doesn't support dark mode, so every
   `if dark else` branch collapses to its light-mode value and the
   light/dark anchor pair becomes one.
2. Pruned to the ~20 tokens nanovisFlux's own widgets actually reference
   (page background, chrome, and the "flat control system" family that
   nanovisFlux's plain QPushButton/QLineEdit/QComboBox etc. draw from) --
   NanovisQ's own copy carries ~150 tokens for widgets (login screens,
   account popups, plot glass cards, menu bars, ...) this app doesn't have.

`flat_*` values are literal spec constants (not derived through the ramp
helpers below) -- carried over verbatim from NanovisQ's `_FLAT_LIGHT`.
"""

from __future__ import annotations

from typing import Tuple, TypedDict

RGBA = Tuple[int, int, int, int]
RGB = Tuple[int, int, int]

# Neutral ink/paper axis (text-ward / background-ward) driving the two
# derived tokens below (popup_border, scrollbar_handle*).
_INK: RGB = (38, 46, 58)
_PAPER: RGB = (255, 255, 255)


def _clamp(x: float) -> int:
    return max(0, min(255, int(round(x))))


def _mix(c1: RGB, c2: RGB, t: float) -> RGB:
    """Linear blend from c1 (t=0) to c2 (t=1) in RGB."""
    return (
        _clamp(c1[0] + (c2[0] - c1[0]) * t),
        _clamp(c1[1] + (c2[1] - c1[1]) * t),
        _clamp(c1[2] + (c2[2] - c1[2]) * t),
    )


def _a(c: RGB, alpha: int) -> RGBA:
    """Attach an alpha channel to an RGB triple."""
    return (c[0], c[1], c[2], _clamp(alpha))


def _fg(t: float) -> RGB:
    """Foreground/text ramp. t=0 = strongest (ink), t=1 = faintest (paper)."""
    return _mix(_INK, _PAPER, t)


def _line(t: float) -> RGB:
    """Border/separator/handle ramp. t=0 subtlest, t=1 strongest."""
    base = _mix(_PAPER, _INK, 0.36)
    top = _mix(_PAPER, _INK, 0.58)
    return _mix(base, top, t)


def _shade(base: RGB, amount: float) -> RGB:
    """Nudge `base` toward black (amount<0) or white (amount>0) -- hover/
    pressed feedback on a solid-fill button, where the fill itself is
    already a fixed spec color rather than something on the fg/line ramps."""
    return _mix(base, (0, 0, 0) if amount < 0 else (255, 255, 255), abs(amount))


class ColorTokens(TypedDict):
    # Page background gradient
    bg_gradient_start: RGBA
    bg_gradient_end: RGBA
    # Chrome
    scrollbar_handle: RGBA
    scrollbar_handle_hover: RGBA
    popup_border: RGBA
    ctrl_hairline: RGBA
    # Flat control system (buttons, inputs, panels, labels)
    flat_text: RGBA
    flat_text_muted: RGBA
    flat_text_hover: RGBA
    flat_surface: RGBA
    flat_surface2: RGBA
    flat_border: RGBA
    flat_border_strong: RGBA
    flat_on_accent: RGBA
    flat_accent: RGBA
    flat_accent_ring: RGBA
    flat_error: RGBA
    flat_error_hover: RGBA
    flat_error_weak: RGBA
    flat_error_ring: RGBA
    flat_success: RGBA
    flat_success_weak: RGBA
    flat_success_ring: RGBA
    flat_warning: RGBA
    flat_warning_weak: RGBA
    flat_warning_ring: RGBA


# Literal spec RGB anchors (not ramp-derived) for the two solid-fill
# buttons (#primary, #estop) that need a hover shade computed from them.
_FLAT_TEXT_RGB: RGB = (45, 52, 56)
_FLAT_ERROR_RGB: RGB = (201, 47, 51)

TOKENS: ColorTokens = {
    "bg_gradient_start": _a((228, 235, 241), 255),
    "bg_gradient_end": _a((244, 247, 249), 255),
    "scrollbar_handle": _a(_line(0.45), 100),
    "scrollbar_handle_hover": _a(_line(0.70), 180),
    "popup_border": _a(_fg(0.60), 255),
    "ctrl_hairline": _a((200, 210, 220), 130),
    # ---- Flat control system -- literal spec values, not ramp-derived ----
    "flat_text": _a(_FLAT_TEXT_RGB, 255),
    "flat_text_muted": (109, 114, 119, 255),
    "flat_text_hover": _a(_shade(_FLAT_TEXT_RGB, 0.15), 255),  # #primary hover -- lightens (near-black base)
    "flat_surface": (253, 253, 254, 255),
    "flat_surface2": (238, 240, 242, 255),
    "flat_border": (206, 209, 212, 255),
    "flat_border_strong": (165, 172, 177, 255),
    "flat_on_accent": (255, 255, 255, 255),
    "flat_accent": (0, 138, 195, 255),
    "flat_accent_ring": (0, 138, 195, 71),
    "flat_error": _a(_FLAT_ERROR_RGB, 255),
    "flat_error_hover": _a(_shade(_FLAT_ERROR_RGB, -0.12), 255),  # #estop hover -- darkens
    "flat_error_weak": (255, 235, 232, 255),
    "flat_error_ring": (201, 47, 51, 61),
    "flat_success": (22, 132, 74, 255),
    "flat_success_weak": (226, 247, 235, 255),
    "flat_success_ring": (22, 132, 74, 61),
    "flat_warning": (178, 111, 0, 255),
    "flat_warning_weak": (255, 244, 224, 255),
    "flat_warning_ring": (178, 111, 0, 61),
}
