# -*- coding: utf-8 -*-
"""码率预设：YouTube 建议码率表（标准码率视频档）。

档位选择规则（按视频输出短边 = min(宽,高) 向上取覆盖档）：
    短边 <= 480   -> 480p 档
    短边 <= 720   -> 720p 档
    短边 <= 1080  -> 1080p 档
    短边 <= 1440  -> 1440p(2K) 档
    其余          -> 2160p(4K) 档
帧率 > 30fps 用高码率列，否则用低码率列。
"""

PRESET_YOUTUBE = "YouTube"

# 标准码率视频档位表：short_edge 为该档最大输出短边（像素），
# bitrate_30 / bitrate_gt30 单位 kbps，audio 单位 kbps
YOUTUBE_STANDARD_TABLE = [
    {"short_edge": 480,  "label": "≤480p",     "bitrate_30": 800,   "bitrate_gt30": 1800,  "audio": 128},
    {"short_edge": 720,  "label": "≤720p",     "bitrate_30": 2200,  "bitrate_gt30": 3200,  "audio": 128},
    {"short_edge": 1080, "label": "≤1080p",    "bitrate_30": 6000,  "bitrate_gt30": 9000,  "audio": 192},
    {"short_edge": 1440, "label": "≤1440p(2K)", "bitrate_30": 12000, "bitrate_gt30": 18000, "audio": 192},
    {"short_edge": 2160, "label": "≤2160p(4K)", "bitrate_30": 30000, "bitrate_gt30": 45000, "audio": 256},
]

# 预设定义：目前只有 YouTube，档位目前只有"标准码率视频"
PRESETS = {
    PRESET_YOUTUBE: {
        "tiers": ["标准码率视频"],
        "tables": {"标准码率视频": YOUTUBE_STANDARD_TABLE},
    }
}


def pick_profile(short_edge: int, fps: float, preset: str = PRESET_YOUTUBE,
                 tier: str = "标准码率视频") -> dict:
    """根据输出短边与帧率，从表格中选取对应码率档位。

    返回 {"label", "bitrate_kbps", "audio_kbps", "fps_class"}
    """
    table = PRESETS[preset]["tables"][tier]
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
    }


def table_html() -> str:
    """码率表 HTML（用于 hover 展示）"""
    head = ("<tr><th>输出短边</th><th>≤30fps 视频码率</th>"
            "<th>&gt;30fps 视频码率</th><th>音频码率</th></tr>")
    rows = []
    for r in YOUTUBE_STANDARD_TABLE:
        rows.append(
            f"<tr><td>{r['label']}</td><td>{r['bitrate_30']}k</td>"
            f"<td>{r['bitrate_gt30']}k</td><td>{r['audio']}k</td></tr>"
        )
    return (f"<table cellspacing='0' cellpadding='6' style='border-collapse:collapse;'>"
            f"<tr style='background:#3b82f6;color:#fff;'>{head[4:]}</tr>"
            + "".join(rows) + "</table>")
