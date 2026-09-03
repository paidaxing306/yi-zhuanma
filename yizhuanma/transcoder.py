# -*- coding: utf-8 -*-
"""FFmpeg 探测与转码核心：ffprobe 取视频信息，自动选档、选编码器，转码并上报进度。

编码器优先级：有显卡优先硬件（h264_nvenc -> h264_amf -> h264_qsv），硬件初始化失败自动降级 libx264（CPU）。
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import threading

from PySide6.QtCore import QThread, Signal

from . import ffmpeg_util
from .presets import DEFAULT_PRESET, pick_profile

log = logging.getLogger("yizhuanma")

# 硬件编码器链（按优先级），libx264 永远兜底
_ENCODER_CHAIN = ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]

# 硬件编码器初始化失败的典型特征（用于自动降级）
_HW_FAIL_PATTERNS = [
    re.compile(r"error initializing", re.I),
    re.compile(r"cannot load nvcuda|no capable devices|cuda", re.I),
    re.compile(r"cannot load amfrt64|cannot load amf", re.I),
    re.compile(r"mfx|qsv.*(fail|error|not support)", re.I),
]


class ProbeError(Exception):
    pass


def probe(path: str) -> dict:
    """ffprobe 探测：返回 {width, height, short_edge, fps, duration}"""
    ffprobe = ffmpeg_util.ffprobe_path()
    if not ffprobe:
        raise ProbeError("未找到 ffprobe.exe")
    cmd = [
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120,
                          creationflags=getattr(subprocess,
                                                "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0:
        raise ProbeError(f"ffprobe 读取失败: {proc.stderr.strip()[:300]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v:
        raise ProbeError("文件中未找到视频流")
    width = int(v.get("width", 0))
    height = int(v.get("height", 0))
    if not width or not height:
        raise ProbeError("无法读取视频分辨率")
    # 帧率: avg_frame_rate 形如 "30000/1001"
    fps = 0.0
    rate = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
    try:
        num, _, den = rate.partition("/")
        if float(den):
            fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    duration = 0.0
    dur = data.get("format", {}).get("duration")
    if dur:
        try:
            duration = float(dur)
        except ValueError:
            duration = 0.0
    return {
        "width": width,
        "height": height,
        "short_edge": min(width, height),
        "fps": fps,
        "duration": duration,
    }


def _available_encoders() -> list:
    """读取 ffmpeg 支持的编码器列表（编码器名集合）"""
    ffmpeg = ffmpeg_util.ffmpeg_path()
    if not ffmpeg:
        return []
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return []
    names = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        # 格式: " V....D <编码器名>  <描述>"；首行图例 " V..... = Video" 需跳过
        if len(parts) >= 2 and line.startswith(" V") and parts[1] != "=":
            names.append(parts[1])
    return names


def pick_encoder() -> str:
    """按优先级返回可用编码器；全部不可用返回空串"""
    supported = set(_available_encoders())
    for enc in _ENCODER_CHAIN:
        if enc in supported:
            return enc
    return ""


def _is_hw_failure(stderr: str, encoder: str) -> bool:
    return encoder != "libx264" and any(
        p.search(stderr) for p in _HW_FAIL_PATTERNS)


def build_command(in_path: str, out_path: str, encoder: str,
                  profile: dict, fps: float = 0.0, vf: str | None = None) -> list:
    """构造 ffmpeg 转码命令。

    profile: pick_profile() 的返回值
    fps: 源帧率，用于关键帧间隔（GOP = 2 秒）
    vf: 可选视频滤镜（如 1080p 封顶缩放）
    """
    br = profile["bitrate_kbps"]
    abr = profile["audio_kbps"]
    cmd = [
        ffmpeg_util.ffmpeg_path(),
        "-y", "-hide_banner", "-nostdin",
        "-i", in_path,
    ]
    if vf:
        cmd += ["-vf", vf]
    cmd += [
        "-sn",                                   # 忽略字幕
        "-c:v", encoder,
        "-b:v", f"{br}k", "-maxrate", f"{br}k",
        "-bufsize", f"{br * 2}k",
        "-pix_fmt", "yuv420p",
    ]
    if encoder == "h264_nvenc":
        cmd += ["-rc", "vbr", "-preset", "p5"]
    elif encoder == "h264_amf":
        cmd += ["-rc", "vbr_peak", "-quality", "balanced"]
    elif encoder == "h264_qsv":
        cmd += ["-preset", "medium"]
    else:  # libx264
        cmd += ["-preset", "medium"]
    # 关键帧间隔 2 秒（建议的分发参数）
    if fps > 0:
        cmd += ["-g", str(max(1, int(round(fps * 2))))]
    cmd += [
        "-c:a", "aac", "-b:a", f"{abr}k", "-ar", "48000",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        out_path,
    ]
    return cmd


def _parse_progress_line(line: str) -> float | None:
    """解析 ffmpeg -progress 输出行，返回进度秒数或 None"""
    line = line.strip()
    if not line:
        return None
    key, _, value = line.partition("=")
    if key == "out_time_us":
        try:
            return int(value) / 1_000_000.0
        except ValueError:
            return None
    if key == "out_time":
        m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", value)
        if m:
            h, mi, s = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(s)
    return None


def unique_output_path(out_dir: str, in_path: str) -> str:
    """生成不冲突的输出路径：原名.mp4。

    源文件本身就是 mp4 且与输出同目录时，为避免覆盖源文件，
    自动加序号：原名(1).mp4 / 原名(2).mp4 ...
    """
    stem = os.path.splitext(os.path.basename(in_path))[0]
    target = os.path.join(out_dir, f"{stem}.mp4")
    if os.path.abspath(target) == os.path.abspath(in_path):
        target = os.path.join(out_dir, f"{stem}(1).mp4")
    i = 1
    while os.path.exists(target):
        target = os.path.join(out_dir, f"{stem}({i}).mp4")
        i += 1
    return target


def estimate_output_size(info: dict, preset: str = DEFAULT_PRESET) -> int | None:
    """按选档码率估算转码后文件大小（字节）。info 为 probe() 返回值。"""
    if not info.get("duration"):
        return None
    try:
        profile = pick_profile(info["short_edge"], info["fps"], preset)
    except Exception:  # noqa: BLE001
        return None
    total_kbps = profile["bitrate_kbps"] + profile["audio_kbps"]
    return int(total_kbps * 1000 / 8 * info["duration"])


class TranscodeWorker(QThread):
    """顺序转码任务队列（单线程，避免 CPU 竞争）"""

    file_started = Signal(int, str, str)      # index, filename, 档位说明
    file_progress = Signal(int, int)          # index, 百分比(-1=不确定)
    file_finished = Signal(int, bool, str)    # index, ok, 消息
    all_finished = Signal(int, int)           # 成功数, 失败数

    def __init__(self, files: list, out_dir: str,
                 preset: str = DEFAULT_PRESET, tier: str = "标准码率视频",
                 parent=None):
        super().__init__(parent)
        # files 元素为 (路径, 显示名) 或 (路径, 显示名, 大小)，统一为 2 元组
        self.files = [(f[0], f[1]) for f in files]
        self.out_dir = out_dir
        self.preset = preset
        self.tier = tier
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        log.info("任务队列启动: %d 个文件, 输出目录=%r", len(self.files),
                 self.out_dir or "(视频同目录)")
        ok_count = fail_count = 0
        for i, (path, name) in enumerate(self.files):
            if self._cancel.is_set():
                log.warning("取消: %s", name)
                self.file_finished.emit(i, False, "已取消")
                fail_count += 1
                continue
            try:
                info = probe(path)
                profile = pick_profile(info["short_edge"], info["fps"],
                                       self.preset, self.tier)
                desc = (f"{info['width']}x{info['height']} {info['fps']:.2f}fps "
                        f"-> {self.preset} {profile['label']} "
                        f"{profile['bitrate_kbps']}k")
                log.info("[%d/%d] %s: %s", i + 1, len(self.files), name, desc)
                self.file_started.emit(i, name, desc)
                ok, msg = self._transcode_one(path, info, profile, i)
            except Exception as e:  # noqa: BLE001 界面线程收尾，异常统一转消息
                log.exception("任务异常: %s", name)
                ok, msg = False, f"失败: {e}"
            self.file_finished.emit(i, ok, msg)
            log.info("[%d/%d] %s -> %s", i + 1, len(self.files), name, msg)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
        log.info("任务队列结束: 成功 %d, 失败 %d", ok_count, fail_count)
        self.all_finished.emit(ok_count, fail_count)

    def _transcode_one(self, path: str, info: dict, profile: dict,
                       index: int) -> tuple:
        # 输出目录留空 = 输出到视频所在目录
        out_dir = self.out_dir or os.path.dirname(path)
        out_path = unique_output_path(out_dir, path)
        # 抖音/小红书等 1080p 封顶预设：超高清源缩到最长边 1080
        vf = None
        if profile.get("cap_1080") and \
                max(info["width"], info["height"]) > 1080:
            vf = ("scale=-2:1080" if info["width"] >= info["height"]
                  else "scale=1080:-2")
            log.info("超高清源 %.0fx%.0f, %s 预设封顶 1080p, 滤镜: %s",
                     info["width"], info["height"], self.preset, vf)
        encoder = pick_encoder() or "libx264"
        attempts = [encoder] + (["libx264"] if encoder != "libx264" else [])
        for enc in attempts:
            cmd = build_command(path, out_path, enc, profile,
                                fps=info["fps"], vf=vf)
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            # 关键：stderr 必须实时读取，否则管道写满/ffmpeg 退出流程
            # 会被阻塞（Windows 上表现为 ffmpeg 编码完不退出）
            stderr_q = queue.Queue()

            def _stderr_reader():
                for line in proc.stderr:
                    stderr_q.put(line)

            threading.Thread(target=_stderr_reader, daemon=True).start()

            duration = info.get("duration") or 0.0
            last_pct = -2
            while True:
                if self._cancel.is_set():
                    proc.kill()
                    try:
                        os.remove(out_path)
                    except OSError:
                        pass
                    return False, "已取消"
                line = proc.stdout.readline()
                if not line:
                    break
                t = _parse_progress_line(line)
                if t is None:
                    continue
                if duration > 0:
                    pct = min(99, int(t / duration * 100))
                else:
                    pct = -1
                if pct != last_pct:
                    last_pct = pct
                    self.file_progress.emit(index, pct)
            proc.wait()
            err_lines = []
            while not stderr_q.empty():
                err_lines.append(stderr_q.get_nowait())
            err = "".join(err_lines)
            if proc.returncode == 0:
                log.info("转码成功: %s (编码器 %s)", out_path, enc)
                return True, f"完成 -> {os.path.basename(out_path)}"
            if enc != "libx264" and _is_hw_failure(err, enc):
                log.warning("硬件编码 %s 失败, 降级 libx264: %s",
                            enc, err.strip()[-200:])
                continue  # 硬件编码失败，降级 CPU 重试
            log.error("转码失败(编码器 %s): %s", enc, err.strip()[-300:])
            return False, f"转码失败: {err.strip()[-300:]}"
        return False, "转码失败: 编码器均不可用"
