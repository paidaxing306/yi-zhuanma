# -*- coding: utf-8 -*-
"""ffmpeg / ffprobe 定位：开发环境用系统 PATH 或 C:/ffmpeg/bin，
PyInstaller 打包后从 _MEIPASS 解压目录取随包携带的二进制。"""
import os
import shutil
import sys

# 打包时随附的二进制（build.bat / spec 里 --add-binary）
_BUNDLED = ["ffmpeg.exe", "ffprobe.exe"]

_FALLBACK_DIR = r"C:/ffmpeg/bin"


def _frozen_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return ""


def _find(binary: str) -> str:
    # 1) 打包环境：_MEIPASS 随附文件
    base = _frozen_dir()
    if base:
        p = os.path.join(base, binary)
        if os.path.isfile(p):
            return p
    # 2) 开发环境：系统 PATH
    p = shutil.which(binary)
    if p:
        return p
    # 3) 开发环境：本机固定路径
    p = os.path.join(_FALLBACK_DIR, binary)
    if os.path.isfile(p):
        return p
    return ""


def ffmpeg_path() -> str:
    return _find("ffmpeg.exe")


def ffprobe_path() -> str:
    return _find("ffprobe.exe")


def check_available() -> tuple:
    """返回 (ffmpeg 可用, ffprobe 可用)"""
    return bool(ffmpeg_path()), bool(ffprobe_path())
