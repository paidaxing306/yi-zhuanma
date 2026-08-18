# -*- coding: utf-8 -*-
"""yizhuanma CLI 打包入口（PyInstaller 打包 cli 版本用此文件）"""
import sys

from yizhuanma.cli import main

if __name__ == "__main__":
    sys.exit(main())
