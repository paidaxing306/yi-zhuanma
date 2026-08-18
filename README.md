# 易转码

视频格式转换工具（Windows）：拖入视频按平台码率表自动转码，
有 NVIDIA/AMD/Intel 显卡优先走硬件编码，无显卡自动降级 CPU。

作者：黎超杰  联系方式：xxxxwoai@qq.com

## 界面预览

![运行界面](screenshots/main-ui.png)

## 功能

- 拖入/选择多个视频（mp4、avi、mkv、mov、wmv、flv、webm、ts、m4v 等）
- 预设平台：**B站 / 抖音 / 小红书 / YouTube**（悬停 ℹ 查看对应码率表）
- 输出目录默认 = 第一个视频所在目录下的「已转码」文件夹（自动创建，可手动修改），
  转码完成后自动打开输出目录；文件名为 `原名.mp4`（源文件本身是 mp4 时自动加序号避免覆盖）
- 列表显示：文件名 / 大小 / **预计转码后大小** / 状态，单行 × 移除
- 自动匹配码率：按视频短边与帧率从预设表选档（H.264 + AAC-LC，MP4 容器）
- 抖音/小红书无 2K/4K 分发档，超高清源自动缩至 1080p（最高 1080p）
- 编码器自动选择：h264_nvenc（N 卡）→ h264_amf（A 卡）→ h264_qsv（Intel 核显）→ libx264（CPU 兜底）
- 硬件编码失败自动降级 CPU，不会中断任务
- 编码参数：VBR、关键帧间隔 2 秒、音频 AAC-LC 48kHz

## 码率表（单位 kbps）

### B站
| 输出短边 | ≤30fps | 60fps | 音频 |
|----------|--------|-------|------|
| ≤480p    | 800    | 1500  | 128  |
| ≤720p    | 2000   | 3000  | 128  |
| ≤1080p   | 5500   | 8000  | 192  |
| ≤1440p(2K) | 10000 | 15000 | 192 |
| ≤2160p(4K) | 16000 | 22000 | 256 |

### 抖音 / 小红书（最高 1080p，超高清源自动缩放）
| 输出短边 | ≤30fps | 60fps | 音频 |
|----------|--------|-------|------|
| ≤480p    | 800    | 1500  | 128  |
| ≤720p    | 2000   | 3000  | 128  |
| ≤1080p   | 5500   | 8000  | 192  |

### YouTube
| 输出短边 | ≤30fps | >30fps | 音频 |
|----------|--------|--------|------|
| ≤480p    | 800    | 1800   | 128  |
| ≤720p    | 2200   | 3200   | 128  |
| ≤1080p   | 6000   | 9000   | 192  |
| ≤1440p(2K) | 12000 | 18000 | 192 |
| ≤2160p(4K) | 30000 | 45000 | 256 |

选档规则：短边取覆盖当前分辨率的最小档（如 900p 取 1080p 档），
帧率 >30fps 取高码率列。

## 开发运行

```bash
python -m pip install -r requirements.txt
python main.py
```

依赖：Python 3.11+，本机需有 ffmpeg/ffprobe（开发时自动找 PATH 或 C:/ffmpeg/bin）。

## 打包分发

### Windows（图形界面版）

双击 `build.bat`，产物 `dist/易转码.exe`（单文件，客户免安装、零依赖）。

注意：
- 打包会把 ffmpeg.exe / ffprobe.exe 一起打入 exe
- **商用分发请把 C:/ffmpeg/bin 换成 LGPL 构建版 ffmpeg**（如 BtbN 的
  ffmpeg-latest-win64-lgpl），避免 GPL 许可证传染
- 若杀毒软件误报，把 build.bat 里 `--onefile` 改为 `--onedir`（文件夹模式，误报率低）

### Ubuntu（命令行版，无界面）

在 Ubuntu 上执行 `bash build_ubuntu.sh`，产物 `dist/yizhuanma`（单文件）。

用法：

```bash
./dist/yizhuanma <视频文件或文件夹> [输出目录] [--preset 平台]
```

- 入参为视频文件或包含视频的文件夹（递归扫描 mp4/avi/mkv/mov 等）
- 未指定输出目录：自动在输入目录下创建 `transcoded` 并输出到其中
- 指定输出目录：转码结果写入该目录
- `--preset` 可选：B站 / 抖音 / 小红书 / YouTube（默认 YouTube）

## 项目结构

```
main.py              入口
yizhuanma/
  __init__.py        版本/作者信息
  presets.py         平台码率表 + 档位选择
  transcoder.py      ffprobe 探测、编码器选择、ffmpeg 调用、进度解析
  ffmpeg_util.py     ffmpeg/ffprobe 定位（开发/打包）
  ui.py              PySide6 界面（拖拽、任务列表、hover 码率表）
build.bat            PyInstaller 打包脚本
```
