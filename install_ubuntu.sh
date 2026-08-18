#!/usr/bin/env bash
# ============================================================
#  易转码 Ubuntu 一键安装脚本
#  从源码编译(PyInstaller 打包)并安装为系统命令 yizhuanma
#
#  用法: 在 Ubuntu 上执行  bash install_ubuntu.sh
#  安装后直接使用:  yizhuanma <视频文件或文件夹> [输出目录]
#  卸载:  sudo rm /usr/local/bin/yizhuanma
# ============================================================
set -e
cd "$(dirname "$0")"

echo "==> [1/4] 检查系统依赖 (ffmpeg / ffprobe / python3)"
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "    安装 ffmpeg ..."
  sudo apt update
  sudo apt install -y ffmpeg
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "    安装 python3 / pip ..."
  sudo apt install -y python3 python3-pip
fi

echo "==> [2/4] 安装 Python 依赖 (含 PyInstaller)"
python3 -m pip install -r requirements.txt pyinstaller

echo "==> [3/4] 源码编译打包"
bash build_ubuntu.sh

echo "==> [4/4] 安装到系统命令 /usr/local/bin/yizhuanma"
sudo install -m 755 dist/yizhuanma /usr/local/bin/yizhuanma

echo ""
echo "安装完成! 使用方法:"
echo "  yizhuanma <视频文件或文件夹> [输出目录]"
echo "  示例:"
echo "    yizhuanma ~/videos/abc.mp4                转单个文件, 输出到同目录 transcoded/"
echo "    yizhuanma ~/videos                       转整个文件夹(递归)"
echo "    yizhuanma ~/videos ~/output               指定输出目录"
echo "    yizhuanma ~/videos --preset 抖音          按抖音预设(默认 YouTube)"
