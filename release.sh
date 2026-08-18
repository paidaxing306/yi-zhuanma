#!/usr/bin/env bash
# ============================================================
#  易转码 一键发布脚本 (在 Windows git-bash 中运行)
#  打包 Windows exe + Ubuntu Linux 包, 一并上传 GitHub Release
#
#  用法: bash release.sh <版本号> [Release 说明文件]
#    例: bash release.sh v1.3.0
#    例: bash release.sh v1.3.0 notes.md   (自定义 Release 说明)
#
#  前置:
#    1) Windows: python 已安装 PySide6 / PyInstaller
#    2) ffmpeg.exe / ffprobe.exe 位于 C:/ffmpeg/bin/
#    3) WSL 已安装 Ubuntu (脚本在 WSL 内打包 Linux 版)
#    4) GitHub 凭据: 设置 GH_TOKEN 环境变量, 或 git credential store 已存 github.com 凭据
#    5) 直连 GitHub 不通时: export HTTPS_PROXY=http://127.0.0.1:7890
# ============================================================
set -e
VERSION="${1:?用法: bash release.sh <版本号, 如 v1.2.0>}"
BODY_FILE="${2:-}"
cd "$(dirname "$0")"

REPO="paidaxing306/yi-zhuanma"
LINUX_ASSET="yizhuanma-ubuntu-x86_64-$VERSION.tar.gz"

# 工作区必须干净, 避免打包到旧代码
[ -z "$(git status --porcelain)" ] || { echo "错误: 工作区有未提交改动, 请先提交再发布"; exit 1; }

# GitHub 凭据: GH_TOKEN 环境变量优先, 否则读 git credential store
TOKEN="${GH_TOKEN:-$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | sed -n 's/^password=//p')}"
[ -n "$TOKEN" ] || { echo "错误: 未取得 GitHub 凭据 (设置 GH_TOKEN 或配置 git credential store)"; exit 1; }

echo "==> [1/4] 打包 Windows 版 易转码.exe"
python -m PyInstaller --noconfirm --clean --name 易转码 --onefile --windowed \
  --add-binary "C:/ffmpeg/bin/ffmpeg.exe:." \
  --add-binary "C:/ffmpeg/bin/ffprobe.exe:." \
  main.py

echo "==> [2/4] 打包 Ubuntu 版 (在 WSL 内)"
WIN_DIR="$(cygpath -w "$PWD")"
wsl bash -c "cd \"\$(wslpath '$WIN_DIR')\" && bash build_ubuntu.sh && chmod +x dist/yizhuanma && tar czf dist/$LINUX_ASSET -C dist yizhuanma && sha256sum dist/$LINUX_ASSET"

echo "==> [3/4] 打 tag 并推送 (直连不通时先 export HTTPS_PROXY=http://127.0.0.1:7890)"
git tag "$VERSION" 2>/dev/null || true
git push origin "$VERSION"

echo "==> [4/4] 创建 Release 并上传资产"
if [ -n "$BODY_FILE" ]; then
  BODY="$(cat "$BODY_FILE")"
else
  BODY="## 易转码 $VERSION

- Windows: \`易转码.exe\`
- Ubuntu x86_64: \`$LINUX_ASSET\`
"
fi
python - "$VERSION" "$BODY" > .release_body.json <<'PYEOF'
import json, sys
tag, body = sys.argv[1], sys.argv[2]
print(json.dumps({"tag_name": tag, "name": tag, "body": body}, ensure_ascii=False))
PYEOF

# Release 已存在则跳过创建 (只补传资产)
RELEASE_ID="$(curl -s -H "Authorization: token $TOKEN" "https://api.github.com/repos/$REPO/releases/tags/$VERSION" | python -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || true)"
if [ -z "$RELEASE_ID" ]; then
  RELEASE_ID="$(curl -s -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" -d @.release_body.json "https://api.github.com/repos/$REPO/releases" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")"
  echo "    已创建 Release $VERSION (id=$RELEASE_ID)"
else
  echo "    Release $VERSION 已存在 (id=$RELEASE_ID), 仅上传/更新资产"
fi
rm -f .release_body.json

for f in "dist/易转码.exe" "dist/$LINUX_ASSET"; do
  name="$(basename "$f")"
  echo "    上传 $name ($(du -h "$f" | cut -f1)) ..."
  curl -s --retry 3 --retry-delay 5 \
    -H "Authorization: token $TOKEN" -H "Content-Type: application/octet-stream" \
    --data-binary @"$f" \
    "https://uploads.github.com/repos/$REPO/releases/$RELEASE_ID/assets?name=$name" \
    | python -c "import sys,json; d=json.load(sys.stdin); print('    ok:', d.get('name'), '| size:', d.get('size'), '| state:', d.get('state'), '|', d.get('message') or '')"
done

echo ""
echo "发布完成: https://github.com/$REPO/releases/tag/$VERSION"
