"""Launches the nanovisFlux control GUI (PyQt5) -- connect to a simulated
or real controller, visualize the deck, jog manually (keyboard/gamepad),
and build/run/step through routines.

Run with:  python -m scripts.run_gui
"""
from __future__ import annotations

from src.gui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
