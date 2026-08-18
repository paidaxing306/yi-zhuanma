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

# 国内镜像源 (apt / pip), 可通过环境变量覆盖, 例如:
#   APT_MIRROR=http://mirrors.aliyun.com/ubuntu PIP_MIRROR=https://mirrors.aliyun.com/pypi/simple bash install_ubuntu.sh
APT_MIRROR="${APT_MIRROR:-http://mirrors.tuna.tsinghua.edu.cn/ubuntu}"
PIP_MIRROR="${PIP_MIRROR:-https://pypi.tuna.tsinghua.edu.cn/simple}"

# 将 apt 源切换到国内镜像 (自动跳过已使用国内源的系统, 原配置备份为 .bak)
setup_apt_mirror() {
  local files="" f
  for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources; do
    [ -f "$f" ] && files="$files $f"
  done
  if grep -rEq 'mirrors\.(tuna|aliyun|ustc|huaweicloud|163)' $files 2>/dev/null; then
    echo "    已使用国内 apt 源, 跳过切换"
    return 0
  fi
  echo "    切换 apt 源为 $APT_MIRROR (原配置备份为 .bak)"
  for f in $files; do
    sudo cp -a "$f" "$f.bak.$(date +%s)"
    sudo sed -i \
      -e 's|http://archive\.ubuntu\.com/ubuntu|'"$APT_MIRROR"'|g' \
      -e 's|http://security\.ubuntu\.com/ubuntu|'"$APT_MIRROR"'|g' \
      "$f"
  done
}

echo "==> [1/4] 检查系统依赖 (ffmpeg / ffprobe / python3)"
setup_apt_mirror
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "    安装 ffmpeg ..."
  sudo apt update
  sudo apt install -y ffmpeg
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "    安装 python3 / pip ..."
  sudo apt install -y python3 python3-pip
fi

echo "==> [2/4] 安装 Python 依赖 (含 PyInstaller, 使用国内 pip 源)"
python3 -m pip install -i "$PIP_MIRROR" -r requirements.txt pyinstaller

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
