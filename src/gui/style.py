"""Palette and QSS for the nanovisFlux control GUI.

Kept monochrome (warm off-white ground, near-black ink) with exactly two
semantic accents -- red for the e-stop, green for "connected" -- so those two
things are the only color a operator's eye needs to find fast. Everything
else (mount markers, step-block colors) uses muted, low-saturation tints so
it never competes with the accents.
"""
from __future__ import annotations

BG = "#EDEAE2"            # page ground -- warm, not pure grey
PANEL = "#FBFAF7"         # card/panel surface
PANEL_ALT = "#F2EFE8"     # recessed surface (console, disabled fields)
BORDER = "#D9D4C7"
BORDER_STRONG = "#3A382F"
INK = "#232019"
INK_MUTED = "#6B6858"
ACCENT_RED = "#C13B2E"
ACCENT_RED_HOVER = "#A62F24"
ACCENT_GREEN = "#3E8E5B"
ACCENT_AMBER = "#B18A3E"
MONO_FONT = "Consolas"
UI_FONT = "Segoe UI"

QSS = f"""
* {{
    font-family: "{UI_FONT}";
    color: {INK};
}}

QWidget {{
    background: transparent;
}}

/* Qt Style Sheets break ties between equally-specific type selectors by
   source order, and QDialog IS-A QWidget -- so this rule MUST come after
   the generic QWidget background-transparent rule above, or that one wins
   for every QDialog too and the window renders with no background at all.
   Top-level windows (QDialog and subclasses, e.g. QMessageBox) don't
   inherit the app stylesheet's palette from Windows dark mode automatically
   -- without an explicit background they show the OS's dark window
   background while text stays the app's dark ink, i.e. unreadable. This app
   commits to one light look regardless of OS theme, so every dialog and
   combo popup gets that look forced explicitly. */
QMainWindow, QWidget#centralRoot, QDialog {{
    background: {BG};
}}
QComboBox QAbstractItemView {{
    background: {PANEL};
    color: {INK};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: {INK};
    selection-color: {PANEL};
}}

QFrame.panel, QWidget.panel {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}

QFrame.card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}

QLabel.eyebrow {{
    color: {INK_MUTED};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}}

QLabel.h1 {{
    font-size: 15px;
    font-weight: 700;
}}

QLabel.pill {{
    background: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 10px;
    font-weight: 600;
    color: {INK_MUTED};
}}
QLabel.pill-live {{
    background: #E3F0E7;
    border: 1px solid {ACCENT_GREEN};
    color: {ACCENT_GREEN};
}}
QLabel.pill-warn {{
    background: #F5EADC;
    border: 1px solid {ACCENT_AMBER};
    color: {ACCENT_AMBER};
}}

QLabel.mono {{
    font-family: "{MONO_FONT}";
}}

QPushButton {{
    background: {PANEL};
    border: 1px solid {BORDER_STRONG};
    border-radius: 4px;
    padding: 5px 12px;
}}
QPushButton:hover {{ background: {PANEL_ALT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {INK_MUTED}; border-color: {BORDER}; }}
QPushButton:checked {{ background: {INK}; color: {PANEL}; border-color: {INK}; }}

QPushButton#estop {{
    background: {ACCENT_RED};
    color: white;
    border: 1px solid {ACCENT_RED_HOVER};
    border-radius: 4px;
    font-weight: 700;
    padding: 6px 18px;
}}
QPushButton#estop:hover {{ background: {ACCENT_RED_HOVER}; }}
QPushButton#estop:disabled {{ background: #D9A79F; border-color: #D9A79F; color: #FBFAF7; }}

QPushButton#primary {{
    background: {INK};
    color: {PANEL};
    border-color: {INK};
}}
QPushButton#primary:hover {{ background: #3A362B; }}
QPushButton#primary:disabled {{ background: {BORDER}; color: {INK_MUTED}; border-color: {BORDER}; }}

QPushButton.jog {{
    min-width: 40px;
    min-height: 34px;
    font-weight: 600;
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {PANEL};
    border: 1px solid {BORDER_STRONG};
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: {INK};
}}

QPlainTextEdit#console {{
    background: {PANEL_ALT};
    border: 1px solid {BORDER_STRONG};
    font-family: "{MONO_FONT}";
    font-size: 11px;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    padding: 6px 14px;
    color: {INK_MUTED};
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {INK};
    border-bottom: 2px solid {INK};
    font-weight: 600;
}}

QListWidget {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}
QListWidget::item {{
    border-bottom: 1px solid {BORDER};
    padding: 2px;
}}
QListWidget::item:selected {{
    background: {PANEL_ALT};
    color: {INK};
}}

QSplitter::handle {{
    background: {BORDER};
}}

QScrollBar:vertical {{ width: 10px; background: transparent; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 5px; min-height: 24px; }}
QScrollBar:horizontal {{ height: 10px; background: transparent; }}
QScrollBar::handle:horizontal {{ background: {BORDER_STRONG}; border-radius: 5px; min-width: 24px; }}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {INK_MUTED};
}}
"""
