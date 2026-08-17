# -*- coding: utf-8 -*-
"""yizhuanma 易转码 - 程序入口"""
import logging
import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from yizhuanma import APP_NAME
from yizhuanma.ui import MainWindow


def _setup_logging():
    log_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    log_file = os.path.join(log_dir, "yizhuanma.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    logging.getLogger("yizhuanma").info("yizhuanma 启动")


def main():
    _setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Microsoft YaHei", 10))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
