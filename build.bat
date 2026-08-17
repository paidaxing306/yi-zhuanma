@echo off
rem ============================================================
rem  yizhuanma 打包脚本 (PyInstaller)
rem  产物: dist\yizhuanma.exe (单文件, 免安装, 客户零依赖)
rem
rem  说明:
rem   1. 首次使用先执行:  python -m pip install -r requirements.txt pyinstaller
rem   2. ffmpeg.exe / ffprobe.exe 会一并打入 exe
rem      (建议商用分发使用 LGPL 构建版, 如 BtbN 的 ffmpeg-latest-win64-lgpl)
rem   3. 若杀毒软件误报, 可去掉 --onefile 改为文件夹模式:
rem      把 --onefile 换成 --onedir, 产物在 dist\yizhuanma\
rem ============================================================
cd /d %~dp0

python -m PyInstaller --noconfirm --clean ^
  --name 易转码 ^
  --windowed ^
  --onefile ^
  --add-binary "C:/ffmpeg/bin/ffmpeg.exe;." ^
  --add-binary "C:/ffmpeg/bin/ffprobe.exe;." ^
  main.py

if errorlevel 1 (
  echo 打包失败, 请检查上方错误信息
  pause
) else (
  echo.
  echo 打包成功: dist\易转码.exe
  pause
)
