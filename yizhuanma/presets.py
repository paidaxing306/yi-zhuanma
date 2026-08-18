# -*- coding: utf-8 -*-
"""平台码率预设表（单位 kbps，H.264 MP4 AAC-LC）。

选档规则（按视频输出短边 = min(宽,高) 向上取覆盖档）：
    短边 <= 480   -> 480p 档
    短边 <= 720   -> 720p 档
    短边 <= 1080  -> 1080p 档
    短边 <= 1440  -> 1440p(2K) 档（B站/YouTube）
    其余          -> 2160p(4K) 档（B站/YouTube）
帧率 > 30fps 用高码率列，否则用低码率列。

抖音/小红书无 2K/4K 官方分发档位，最高 1080p：
短边超过 1080 的源按 1080p 档码率编码，并缩放到最长边 1080（cap_1080）。
"""

# 列头：fps_high_label 为高帧率列名（>30fps 档）
_PRESET_DEFS = {
    "B站": {
        "tiers": ["标准码率视频"],
        "fps_high_label": "60fps",
        "cap_1080": False,
        "table": [
            {"short_edge": 480,  "label": "≤480p",     "bitrate_30": 800,   "bitrate_gt30": 1500,  "audio": 128},
            {"short_edge": 720,  "label": "≤720p",     "bitrate_30": 2000,  "bitrate_gt30": 3000,  "audio": 128},
            {"short_edge": 1080, "label": "≤1080p",    "bitrate_30": 5500,  "bitrate_gt30": 8000,  "audio": 192},
            {"short_edge": 1440, "label": "≤1440p(2K)", "bitrate_30": 10000, "bitrate_gt30": 15000, "audio": 192},
            {"short_edge": 2160, "label": "≤2160p(4K)", "bitrate_30": 16000, "bitrate_gt30": 22000, "audio": 256},
        ],
    },
    "抖音": {
        "tiers": ["标准码率视频"],
        "fps_high_label": "60fps",
        "cap_1080": True,
        "table": [
            {"short_edge": 480,  "label": "≤480p",  "bitrate_30": 800,  "bitrate_gt30": 1500, "audio": 128},
            {"short_edge": 720,  "label": "≤720p",  "bitrate_30": 2000, "bitrate_gt30": 3000, "audio": 128},
            {"short_edge": 1080, "label": "≤1080p", "bitrate_30": 5500, "bitrate_gt30": 8000, "audio": 192},
        ],
    },
    "小红书": {
        "tiers": ["标准码率视频"],
        "fps_high_label": "60fps",
        "cap_1080": True,
        "table": [
            {"short_edge": 480,  "label": "≤480p",  "bitrate_30": 800,  "bitrate_gt30": 1500, "audio": 128},
            {"short_edge": 720,  "label": "≤720p",  "bitrate_30": 2000, "bitrate_gt30": 3000, "audio": 128},
            {"short_edge": 1080, "label": "≤1080p", "bitrate_30": 5500, "bitrate_gt30": 8000, "audio": 192},
        ],
    },
    "YouTube": {
        "tiers": ["标准码率视频"],
        "fps_high_label": ">30fps",
        "cap_1080": False,
        "table": [
            {"short_edge": 480,  "label": "≤480p",     "bitrate_30": 800,   "bitrate_gt30": 1800,  "audio": 128},
            {"short_edge": 720,  "label": "≤720p",     "bitrate_30": 2200,  "bitrate_gt30": 3200,  "audio": 128},
            {"short_edge": 1080, "label": "≤1080p",    "bitrate_30": 6000,  "bitrate_gt30": 9000,  "audio": 192},
            {"short_edge": 1440, "label": "≤1440p(2K)", "bitrate_30": 12000, "bitrate_gt30": 18000, "audio": 192},
            {"short_edge": 2160, "label": "≤2160p(4K)", "bitrate_30": 30000, "bitrate_gt30": 45000, "audio": 256},
        ],
    },
}

PRESET_NAMES = list(_PRESET_DEFS.keys())          # 预设顺序（下拉框顺序）
DEFAULT_PRESET = "YouTube"                        # 默认选中 YouTube

# 支持的视频扩展名（GUI 拖拽 / CLI 目录扫描共用，不依赖 Qt）
VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv",
              ".webm", ".ts", ".m4v", ".3gp", ".mpg", ".mpeg"}

# 兼容旧引用
PRESET_YOUTUBE = "YouTube"


def preset_tiers(preset: str) -> list:
    return _PRESET_DEFS[preset]["tiers"]


def preset_fps_high_label(preset: str) -> str:
    return _PRESET_DEFS[preset]["fps_high_label"]


def preset_cap_1080(preset: str) -> bool:
    """该预设是否最高只到 1080p（超高清源需缩放）"""
    return _PRESET_DEFS[preset]["cap_1080"]


def pick_profile(short_edge: int, fps: float, preset: str = DEFAULT_PRESET,
                 tier: str = "标准码率视频") -> dict:
    """按输出短边与帧率从指定预设表格中选码率档位。

    返回 {"label", "bitrate_kbps", "audio_kbps", "fps_class", "cap_1080"}
    """
    table = _PRESET_DEFS[preset]["table"]
    row = None
    for r in table:
        if short_edge <= r["short_edge"]:
            row = r
            break
    if row is None:  # 短边超过最大档，按最大档处理
        row = table[-1]
    fps_class = "gt30" if fps > 30 else "30"
    bitrate = row["bitrate_gt30"] if fps_class == "gt30" else row["bitrate_30"]
    return {
        "label": row["label"],
        "bitrate_kbps": bitrate,
        "audio_kbps": row["audio"],
        "fps_class": fps_class,
        "cap_1080": _PRESET_DEFS[preset]["cap_1080"],
    }


def table_html(preset: str = DEFAULT_PRESET) -> str:
    """指定预设的码率表 HTML（用于 hover 展示）"""
    d = _PRESET_DEFS[preset]
    head = (f"<tr><th>输出短边</th><th>≤30fps 视频码率</th>"
            f"<th>{d['fps_high_label']} 视频码率</th><th>音频码率</th></tr>")
    rows = []
    for r in d["table"]:
        rows.append(
            f"<tr><td>{r['label']}</td><td>{r['bitrate_30']}k</td>"
            f"<td>{r['bitrate_gt30']}k</td><td>{r['audio']}k</td></tr>"
        )
    body = "".join(rows)
    if d["cap_1080"]:
        body += ("<tr><td colspan='4' style='color:#6b7280;font-size:8.5pt;'>"
                 "注：该平台无 2K/4K 分发，超高清源自动缩至 1080p</td></tr>")
    return (f"<table cellspacing='0' cellpadding='6' "
            f"style='border-collapse:collapse;'>{head}{body}</table>")
