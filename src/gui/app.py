from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication

from . import style as S
from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(S.load_stylesheet())
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
