"""Entry point for the nanovisFlux control GUI.

Run with:  python -m scripts.run_gui
(module mode puts the repo root on sys.path, so ``from ..core import ...``
-style imports inside src/gui resolve -- same convention every other script
in this repo uses.)
"""
from __future__ import annotations
import sys

from PyQt5.QtWidgets import QApplication

from .main_window import MainWindow
from . import style as S


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(S.load_stylesheet())
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
