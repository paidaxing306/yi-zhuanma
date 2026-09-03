#!/usr/bin/env bash
# ============================================================
# 易转码 macOS 图形界面打包脚本（PyInstaller）
#
# 用法:
#   bash build_macos.sh arm64
#   bash build_macos.sh x86_64
#
# 构建产物:
#   dist/yizhuanma-v<version>-macos-<architecture>.dmg
# ============================================================
set -euo pipefail

TARGET_ARCH="${1:-}"
case "$TARGET_ARCH" in
  arm64|x86_64) ;;
  *)
    echo "用法: bash build_macos.sh <arm64|x86_64>"
    exit 1
    ;;
esac

cd "$(dirname "$0")"

VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' yizhuanma/__init__.py)"
[ -n "$VERSION" ] || { echo "错误: 未能读取应用版本"; exit 1; }

PYTHON_ARCH="$(python3 -c 'import platform; print(platform.machine())')"
[ "$PYTHON_ARCH" = "aarch64" ] && PYTHON_ARCH="arm64"
if [ "$PYTHON_ARCH" != "$TARGET_ARCH" ]; then
  echo "错误: 当前 python3 是 $PYTHON_ARCH 架构，不能构建 $TARGET_ARCH 包"
  echo "请使用 $TARGET_ARCH 架构的 Python 和终端环境后重试。"
  exit 1
fi

FFMPEG_BIN="$(command -v ffmpeg || true)"
FFPROBE_BIN="$(command -v ffprobe || true)"
if [ -z "$FFMPEG_BIN" ] || [ -z "$FFPROBE_BIN" ]; then
  echo "错误: 未找到 ffmpeg/ffprobe，请先安装: brew install ffmpeg"
  exit 1
fi

check_binary_arch() {
  local binary="$1"
  local binary_archs
  binary_archs="$(lipo -archs "$binary" 2>/dev/null || true)"
  case " $binary_archs " in
    *" $TARGET_ARCH "*) ;;
    *)
      echo "错误: $binary 不包含 $TARGET_ARCH 架构（实际: ${binary_archs:-未知}）"
      exit 1
      ;;
  esac
}

check_binary_arch "$FFMPEG_BIN"
check_binary_arch "$FFPROBE_BIN"

APP_NAME="易转码"
APP_PATH="dist/$APP_NAME.app"
DMG_PATH="dist/yizhuanma-v$VERSION-macos-$TARGET_ARCH.dmg"

python3 -m pip install -r requirements.txt pyinstaller
python3 -m PyInstaller --noconfirm --clean \
  --name "$APP_NAME" \
  --windowed \
  --onedir \
  --add-binary "$FFMPEG_BIN:." \
  --add-binary "$FFPROBE_BIN:." \
  main.py

# 让未配置开发者证书的本机构建可正常启动；正式发布应替换为 Developer ID 签名并公证。
codesign --force --deep --sign - "$APP_PATH"

# 打包为 dmg（拖拽安装窗口：打开后可见 .app 和 Applications 链接）
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
cp -R "$APP_PATH" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
rm -f "$DMG_PATH"
hdiutil create -volname "$APP_NAME" \
  -srcfolder "$STAGING" \
  -ov -format UDZO \
  "$DMG_PATH"

echo "打包成功: $DMG_PATH"
