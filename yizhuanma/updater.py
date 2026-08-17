# -*- coding: utf-8 -*-
"""自动更新检测：查询 GitHub 最新 release，与当前版本比较。

检测失败或网络不可用时静默返回 None，不影响程序正常使用。
"""
import json
import re
import urllib.request

REPO_URL = "https://github.com/paidaxing306/yi-zhuanma"
_API_LATEST = "https://api.github.com/repos/paidaxing306/yi-zhuanma/releases/latest"

_version_cache = None


def parse_version(tag: str) -> tuple | None:
    """从 tag（如 v1.2.3）解析版本号，失败返回 None"""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", tag or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def check_latest(timeout: float = 8.0) -> tuple | None:
    """查询最新 release。

    返回 (最新 tag, 下载页 URL)；网络失败/无 release 返回 None。
    """
    try:
        req = urllib.request.Request(
            _API_LATEST, headers={"User-Agent": "yizhuanma-updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        if not parse_version(tag):
            return None
        url = data.get("html_url") or f"{REPO_URL}/releases"
        return tag, url
    except Exception:  # noqa: BLE001 更新检测失败不影响使用
        return None


def has_update(current_version: str, latest_tag: str) -> bool:
    """当前版本 < 最新 tag 版本则返回 True"""
    cur = parse_version(current_version)
    latest = parse_version(latest_tag)
    if not cur or not latest:
        return False
    return cur < latest
