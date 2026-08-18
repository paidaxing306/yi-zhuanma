#!/usr/bin/env bash
# ============================================================
#  yizhuanma Ubuntu 打包脚本 (PyInstaller, 无界面 CLI 版本)
#  产物: dist/yizhuanma (单文件可执行)
#
#  用法: 在 Ubuntu 上执行  bash build_ubuntu.sh
#  前置: 1) sudo apt install -y ffmpeg python3-pip
#        2) python3 -m pip install -r requirements.txt pyinstaller
#  说明: ffmpeg/ffprobe 会一并打入单文件, 目标机器无需安装 ffmpeg
# ============================================================
set -e
cd "$(dirname "$0")"

FFMPEG_BIN="$(command -v ffmpeg || true)"
FFPROBE_BIN="$(command -v ffprobe || true)"
if [ -z "$FFMPEG_BIN" ] || [ -z "$FFPROBE_BIN" ]; then
  echo "错误: 未找到 ffmpeg/ffprobe, 请先安装: sudo apt install -y ffmpeg"
  exit 1
fi

python3 -m PyInstaller --noconfirm --clean \
  --name yizhuanma \
  --onefile \
  --add-binary "$FFMPEG_BIN:." \
  --add-binary "$FFPROBE_BIN:." \
  cli_main.py

echo "打包成功: dist/yizhuanma"
echo "用法: ./dist/yizhuanma <视频文件或文件夹> [输出目录]"
