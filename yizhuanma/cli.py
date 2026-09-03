# -*- coding: utf-8 -*-
"""易转码 Ubuntu 命令行版本（无界面）。

用法:
    yizhuanma <视频文件或文件夹> [输出目录]

- 入参可以是单个视频文件，也可以是包含视频的文件夹（递归扫描）
- 未指定输出目录：自动在输入目录下创建 transcoded 目录
  （输入是文件时，transcoded 建在文件所在目录）
- 指定输出目录：转码结果写入该目录
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from . import __version__
from .presets import DEFAULT_PRESET, VIDEO_EXTS
from .transcoder import TranscodeWorker

log = logging.getLogger("yizhuanma")


def collect_videos(input_path: str, exclude: str | None = None) -> list:
    """收集要转码的视频文件（文件直接返回；目录递归扫描支持的扩展名）。

    exclude: 排除该目录（如输出目录位于输入目录内时，避免扫到
    自己刚转出的文件造成重复转码）。
    """
    exclude_abs = os.path.abspath(exclude) if exclude else None
    if os.path.isfile(input_path):
        if os.path.splitext(input_path)[1].lower() in VIDEO_EXTS:
            return [os.path.abspath(input_path)]
        return []
    files = []
    for root, dirs, names in os.walk(input_path):
        root_abs = os.path.abspath(root)
        if exclude_abs and (root_abs == exclude_abs
                            or root_abs.startswith(exclude_abs + os.sep)):
            dirs[:] = []  # 剪枝：不进入输出目录
            continue
        for n in sorted(names):
            if os.path.splitext(n)[1].lower() in VIDEO_EXTS:
                files.append(os.path.join(root, n))
    return sorted(files)


def resolve_out_dir(input_path: str, out_dir: str | None) -> str:
    """输出目录：指定则用它；否则在输入目录下建 transcoded"""
    if out_dir:
        return os.path.abspath(out_dir)
    base = (os.path.dirname(input_path) if os.path.isfile(input_path)
            else input_path)
    return os.path.join(os.path.abspath(base), "transcoded")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yizhuanma",
        description="易转码命令行版：视频自动转码（无界面）")
    parser.add_argument("input", help="视频文件或包含视频的文件夹")
    parser.add_argument("output", nargs="?", default=None,
                        help="输出目录（默认：输入目录下的 transcoded）")
    parser.add_argument("--preset", default=DEFAULT_PRESET,
                        choices=["B站", "抖音", "小红书", "YouTube"],
                        help=f"平台预设（默认 {DEFAULT_PRESET}）")
    parser.add_argument("--version", action="version",
                        version=f"yizhuanma {__version__}")
    args = parser.parse_args(argv)

    if not os.path.exists(args.input):
        print(f"错误：路径不存在: {args.input}", file=sys.stderr)
        return 2

    out_dir = resolve_out_dir(args.input, args.output)
    os.makedirs(out_dir, exist_ok=True)

    files = collect_videos(args.input, exclude=out_dir)
    if not files:
        print(f"未找到支持的视频文件: {args.input}", file=sys.stderr)
        return 2

    print(f"易转码 v{__version__}  (预设: {args.preset})")
    print(f"发现 {len(files)} 个视频")
    print(f"输出目录: {out_dir}")

    worker = TranscodeWorker(
        [(p, os.path.basename(p)) for p in files],
        out_dir, args.preset, "标准码率视频")
    # 同步执行；信号在 CLI 主线程直接触发（无需事件循环）
    result = {}
    worker.file_started.connect(
        lambda i, name, desc: print(f"[{i + 1}/{len(files)}] {name}  {desc}"))
    worker.file_finished.connect(
        lambda i, ok_, msg: print(f"  {'✓' if ok_ else '✗'} {msg}"))
    worker.all_finished.connect(
        lambda ok_, fail_: result.update(ok=ok_, fail=fail_))
    worker.run()
    return 0 if result.get("fail", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
