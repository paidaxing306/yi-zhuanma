# 易转码 (YiZhuanma)

> [English](README.en.md) | 中文

视频格式转换工具（Windows）：拖入视频自动按 YouTube 建议码率表转码，
有 NVIDIA/AMD/Intel 显卡优先走硬件编码，无显卡自动降级 CPU。

作者：黎超杰  联系方式：13567130573

## 功能

- 拖入/选择多个视频（mp4、avi、mkv、mov、wmv、flv、webm、ts、m4v 等）
- 输出目录可配置（留空 = 输出到视频所在目录，文件名为 `原名.mp4`；源文件本身是 mp4 时自动加序号避免覆盖）
- 预设：YouTube（标准码率视频，悬停 ℹ 查看码率表）
- 自动匹配码率：按视频短边与帧率从表格选档（H.264 + AAC，MP4 容器）
- 编码器自动选择：h264_nvenc（N 卡）→ h264_amf（A 卡）→ h264_qsv（Intel 核显）→ libx264（CPU 兜底）
- 硬件编码失败自动降级 CPU，不会中断任务

## 码率表（YouTube 标准码率视频）

| 输出短边 | ≤30fps 视频码率 | >30fps 视频码率 | 音频码率 |
|----------|----------------|----------------|---------|
| ≤480p    | 800k           | 1800k          | 128k    |
| ≤720p    | 2200k          | 3200k          | 128k    |
| ≤1080p   | 6000k          | 9000k          | 192k    |
| ≤1440p(2K) | 12000k       | 18000k         | 192k    |
| ≤2160p(4K) | 30000k       | 45000k         | 256k    |

选档规则：短边取覆盖当前分辨率的最小档（如 900p 取 1080p 档），
帧率 >30fps 取高码率列。

## 开发运行

```bash
python -m pip install -r requirements.txt
python main.py
```

依赖：Python 3.11+，本机需有 ffmpeg/ffprobe（开发时自动找 PATH 或 C:/ffmpeg/bin）。

## 打包分发

双击 `build.bat`，产物 `dist/易转码.exe`（单文件，客户免安装、零依赖）。

注意：
- 打包会把 ffmpeg.exe / ffprobe.exe 一起打入 exe
- **商用分发请把 C:/ffmpeg/bin 换成 LGPL 构建版 ffmpeg**（如 BtbN 的
  ffmpeg-latest-win64-lgpl），避免 GPL 许可证传染
- 若杀毒软件误报，把 build.bat 里 `--onefile` 改为 `--onedir`（文件夹模式，误报率低）

## 项目结构

```
main.py              入口
yizhuanma/
  __init__.py        版本/作者信息
  presets.py         YouTube 码率表 + 档位选择
  transcoder.py      ffprobe 探测、编码器选择、ffmpeg 调用、进度解析
  ffmpeg_util.py     ffmpeg/ffprobe 定位（开发/打包）
  ui.py              PySide6 界面（拖拽、任务列表、hover 码率表）
build.bat            PyInstaller 打包脚本
```
