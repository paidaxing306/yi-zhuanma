# -*- coding: utf-8 -*-
"""图片转码核心：扫描目录、按大小阈值筛选、把图片压缩到指定大小区间。

规则（x = 过滤阈值，单位 MB）：
    列表只收原图大于 x MB 的图片；
    转码后大小必须小于 (x - 1) MB，并尽量不低于 x/2 MB。

压缩方式：JPEG 质量二分（在不超过上限的前提下取最高质量），
质量降到最低仍超标时按面积比例缩小分辨率后重试，直到落入区间。
输出统一为 .jpg（源图透明通道压白底），写入「已转码」目录。
"""
from __future__ import annotations

import logging
import math
import os
import struct
import threading

from PySide6.QtCore import QBuffer, QIODevice, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter

from .transcoder import unique_output_path

log = logging.getLogger("yizhuanma")

# 支持的图片扩展名（动图 gif 除外：逐帧转 JPG 会丢动画）
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

# 输出目录名（与视频模式保持一致）
OUTPUT_DIR_NAME = "已转码"

MB = 1024 * 1024

# JPEG 质量上限：100 时体积暴涨且肉眼收益极小，95 足够；
# 仅当结果低于目标下限时才试 100（只增加体积，不损失画质）
_MAX_QUALITY = 95

# 单张图解码内存上限（MB）：大图（1 亿像素以上）默认 256MB 会直接读取失败
_ALLOCATION_LIMIT_MB = 4096

# TIFF 标签值类型 -> 单值字节数（用于解析内嵌预览）
_TIFF_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2,
                   9: 4, 10: 8, 11: 4, 12: 8}


class ImageCompressError(Exception):
    """图片无法压缩到目标大小"""


class ImageCancelled(Exception):
    """用户取消"""


def target_range_bytes(threshold_mb: float) -> tuple[int, int]:
    """按阈值 x(MB) 计算目标大小区间（字节）。

    上限严格小于 (x-1) MB（这里减 1 字节，保证 ``<= upper`` 即 ``< (x-1)MB``）；
    下限为 x/2 MB；阈值过小时下限自动收敛到上限，区间退化为单点。
    """
    upper = max(1, int((threshold_mb - 1.0) * MB) - 1)
    lower = max(1, int(threshold_mb / 2.0 * MB))
    return min(lower, upper), upper


def fmt_mb(n_bytes: int) -> str:
    """字节数按 MB 显示（目标区间统一用 MB，避免 1024.0 KB 这类别扭写法）"""
    return f"{n_bytes / MB:.1f} MB"


def fmt_size(n_bytes: int) -> str:
    """图片大小显示：统一用 MB、两位小数（3.96 MB 不会被四舍五入成 4.0 MB）"""
    return f"{n_bytes / MB:.2f} MB"


def range_text(threshold_mb: float) -> str:
    """目标区间的人类可读描述，如「2.5 MB ~ <4.0 MB」"""
    lower, upper = target_range_bytes(threshold_mb)
    if lower >= upper:  # 阈值太小，区间退化为单一上限
        return f"<{fmt_mb(upper)}"
    return f"{fmt_mb(lower)} ~ <{fmt_mb(upper)}"


def scan_images(directory: str) -> list[tuple[str, str, int]]:
    """递归扫描目录内的图片，返回 [(绝对路径, 文件名, 字节数)]，按路径排序。

    跳过「已转码」输出目录，避免把上次的产物当成源图再次转码。
    """
    result: list[tuple[str, str, int]] = []
    if not directory or not os.path.isdir(directory):
        return result
    for root, dirs, names in os.walk(directory):
        dirs[:] = sorted(
            d for d in dirs
            if d != OUTPUT_DIR_NAME and not d.startswith("."))
        for n in sorted(names):
            if os.path.splitext(n)[1].lower() not in IMAGE_EXTS:
                continue
            p = os.path.join(root, n)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            result.append((os.path.abspath(p), n, size))
    return result


def _tiff_embedded_jpegs(path: str) -> list[bytes]:
    """提取 TIFF 容器（含 NEF/CR2 等 RAW）里的内嵌 JPEG 预览。

    Qt 的 TIFF 解码器只读第一个 IFD，而相机 RAW 的第一个 IFD 往往只是
    160×120 缩略图，真正的全尺寸预览在 SubIFD 中（Compression=6/7）。
    返回按字节数降序的 JPEG 流；不是 TIFF 或解析失败时返回空列表。
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        return []
    endian = "<" if data[:2] == b"II" else ">"
    try:
        if struct.unpack_from(endian + "H", data, 2)[0] != 42:
            return []
    except struct.error:
        return []

    def read_values(typ: int, count: int, entry_off: int) -> tuple:
        """读取 IFD 条目的值（inline 或指向数据的偏移）"""
        size = _TIFF_TYPE_SIZE.get(typ, 1) * count
        if size > 4:
            try:
                off = struct.unpack_from(endian + "I", data, entry_off)[0]
            except struct.error:
                return ()
            raw = data[off:off + size]
        else:
            raw = data[entry_off:entry_off + size]
        if len(raw) < size:
            return ()
        if typ == 3:  # SHORT
            return struct.unpack_from(endian + "%dH" % count, raw)
        if typ == 4:  # LONG
            return struct.unpack_from(endian + "%dI" % count, raw)
        return ()

    blobs: list[bytes] = []
    seen_ifd: set[int] = set()

    def walk(off: int, depth: int):
        if depth > 4 or off in seen_ifd or off <= 0 or off + 2 > len(data):
            return
        seen_ifd.add(off)
        try:
            n = struct.unpack_from(endian + "H", data, off)[0]
        except struct.error:
            return
        if n > 1024 or off + 2 + n * 12 > len(data):
            return
        tags: dict[int, tuple] = {}
        sub_ifds: tuple = ()
        for i in range(n):
            e = off + 2 + i * 12
            tag, typ, cnt = struct.unpack_from(endian + "HHI", data, e)
            if tag == 330:  # SubIFDs
                sub_ifds = read_values(typ, cnt, e + 8)
                continue
            if tag not in (256, 257, 259, 273, 279, 513, 514):
                continue
            vals = read_values(typ, cnt, e + 8)
            if vals:
                tags[tag] = vals
        comp = (tags.get(259) or (0,))[0]
        if comp in (6, 7):  # 6=旧式 JPEG, 7=新式 JPEG
            jpeg_off = (tags.get(513) or (0,))[0]
            jpeg_len = (tags.get(514) or (0,))[0]
            spans = []
            if jpeg_off and jpeg_len:
                spans.append((jpeg_off, jpeg_len))
            else:  # 有些 TIFF 用 StripOffsets/StripByteCounts 存 JPEG
                spans = list(zip(tags.get(273) or (), tags.get(279) or ()))
            for o, ln in spans:
                if o and ln and 0 < o < len(data):
                    blob = data[o:o + ln]
                    if blob[:2] == b"\xff\xd8":  # JPEG SOI
                        blobs.append(blob)
        for s in sub_ifds:
            walk(s, depth + 1)
        try:
            nxt = struct.unpack_from(endian + "I", data, off + 2 + n * 12)[0]
        except struct.error:
            nxt = 0
        if nxt:
            walk(nxt, depth + 1)

    try:
        walk(struct.unpack_from(endian + "I", data, 4)[0], 0)
    except struct.error:
        return []
    unique: list[bytes] = []
    for blob in sorted(blobs, key=len, reverse=True):
        if blob not in unique:
            unique.append(blob)
    return unique


def _decode_jpeg(blob: bytes) -> QImage:
    """解码内存中的 JPEG（带 EXIF 方向）"""
    buf = QBuffer()
    buf.setData(blob)
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    try:
        reader = QImageReader(buf)
        reader.setFormat(b"jpeg")
        reader.setAutoTransform(True)
        return reader.read()
    finally:
        buf.close()


def _best_tiff_preview(path: str, current: QImage) -> QImage | None:
    """取 TIFF/NEF 内嵌预览中像素面积最大的一张（需大于已解码图像）"""
    best = None
    best_area = current.width() * current.height()
    for blob in _tiff_embedded_jpegs(path):
        img = _decode_jpeg(blob)
        if img.isNull():
            continue
        area = img.width() * img.height()
        if area > best_area:
            best, best_area = img, area
    return best


def _flatten_alpha(img: QImage) -> QImage:
    """透明通道压白底（JPEG 不支持透明）；无透明通道原样返回"""
    if not img.hasAlphaChannel():
        return img
    out = QImage(img.size(), QImage.Format.Format_RGB32)
    out.fill(QColor(255, 255, 255))
    painter = QPainter(out)
    painter.drawImage(0, 0, img)
    painter.end()
    return out


def _jpeg_bytes(img: QImage, quality: int) -> bytes:
    """编码为 JPEG 字节流（不落盘，用于二分试算大小）"""
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        if not img.save(buf, "JPEG", quality):
            raise ImageCompressError("JPEG 编码失败")
        return bytes(buf.data())
    finally:
        buf.close()


def compress_to_target(img: QImage, lower: int, upper: int,
                       cancel=None) -> tuple[bytes, int]:
    """把图片压到不超过 ``upper`` 字节（尽量不低于 ``lower``）。

    返回 (JPEG 字节流, 质量)。质量优先：在上限内取最高质量；
    若最低质量仍超上限，按面积比例缩小分辨率后重试。
    ``cancel`` 为可选的无参回调，返回 True 时抛 ImageCancelled。
    压不进上限时抛 ImageCompressError。
    """
    def check_cancel():
        if cancel is not None and cancel():
            raise ImageCancelled()

    work = _flatten_alpha(img)
    for _ in range(8):
        check_cancel()
        cache: dict[int, bytes] = {}

        def encoded(quality: int) -> bytes:
            if quality not in cache:
                cache[quality] = _jpeg_bytes(work, quality)
            return cache[quality]

        best = encoded(_MAX_QUALITY)
        if len(best) <= upper:
            quality = _MAX_QUALITY
            # 体积低于下限时尝试满质量，尽量落回区间（不额外放大图片）
            if len(best) < lower:
                q100 = encoded(100)
                if len(q100) <= upper:
                    best, quality = q100, 100
            return best, quality

        smallest = encoded(1)
        if len(smallest) <= upper:
            # 二分找“体积不超上限”的最高质量
            lo, hi = 1, _MAX_QUALITY
            while lo < hi:
                mid = (lo + hi + 1) // 2
                check_cancel()
                if len(encoded(mid)) <= upper:
                    lo = mid
                else:
                    hi = mid - 1
            return encoded(lo), lo

        # 质量 1 仍超标：按 (上限 / 当前体积) 的面积比缩小分辨率
        factor = math.sqrt(upper / len(smallest)) * 0.95
        factor = min(0.97, max(0.15, factor))
        new_w = max(32, int(work.width() * factor))
        new_h = max(32, int(work.height() * factor))
        if new_w >= work.width() or new_h >= work.height():
            break
        work = work.scaled(
            new_w, new_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
    raise ImageCompressError("无法压缩到目标大小")


class ImageTranscodeWorker(QThread):
    """顺序转码图片（单线程，避免多张大图同时解码吃爆内存）"""

    file_started = Signal(int, str, str)      # index, filename, 目标说明
    file_progress = Signal(int, int)          # index, 百分比(-1=不确定)
    file_finished = Signal(int, bool, str)    # index, ok, 消息
    file_result = Signal(int, int, bool)      # index, 输出字节数, 是否达标
    all_finished = Signal(int, int)           # 成功数, 失败数

    def __init__(self, files: list, out_dir: str, threshold_mb: float,
                 parent=None):
        super().__init__(parent)
        # files 元素为 (路径, 显示名) 或 (路径, 显示名, 大小)
        self.files = [(f[0], f[1]) for f in files]
        self.out_dir = out_dir
        self.threshold_mb = float(threshold_mb)
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        lower, upper = target_range_bytes(self.threshold_mb)
        log.info("图片任务启动: %d 张, 阈值 %.1f MB, 目标 %s, 输出=%r",
                 len(self.files), self.threshold_mb,
                 range_text(self.threshold_mb), self.out_dir)
        ok_count = fail_count = 0
        for i, (path, name) in enumerate(self.files):
            if self._cancel.is_set():
                log.warning("取消: %s", name)
                self.file_finished.emit(i, False, "已取消")
                fail_count += 1
                continue
            self.file_started.emit(
                i, name, f"目标 {range_text(self.threshold_mb)}")
            self.file_progress.emit(i, -1)
            try:
                ok, msg = self._transcode_one(i, path, lower, upper)
            except ImageCancelled:
                log.warning("取消: %s", name)
                ok, msg = False, "已取消"
            except Exception as e:  # noqa: BLE001 界面线程统一转消息
                log.exception("图片任务异常: %s", name)
                ok, msg = False, f"失败: {e}"
            self.file_finished.emit(i, ok, msg)
            log.info("[%d/%d] %s -> %s", i + 1, len(self.files), name, msg)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
        log.info("图片任务结束: 成功 %d, 失败 %d", ok_count, fail_count)
        self.all_finished.emit(ok_count, fail_count)

    def _transcode_one(self, index: int, path: str,
                       lower: int, upper: int) -> tuple[bool, str]:
        out_dir = self.out_dir or os.path.dirname(path)
        QImageReader.setAllocationLimit(_ALLOCATION_LIMIT_MB)
        reader = QImageReader(path)
        reader.setAutoTransform(True)  # 按 EXIF 方向摆正，避免手机照片转向
        fmt = bytes(reader.format() or b"").lower()
        img = reader.read()
        if img.isNull():
            return False, f"无法读取图片: {reader.errorString()}"
        try:
            file_bytes = os.path.getsize(path)
        except OSError:
            file_bytes = 0
        # 相机 RAW（NEF/CR2 等）第一个 IFD 往往只是缩略图，全尺寸预览在
        # SubIFD 里；此时改用内嵌大图，避免压出一张几十 KB 的预览图。
        if (fmt in (b"tiff", b"tif") and file_bytes >= MB
                and img.width() * img.height() < file_bytes // 10):
            preview = _best_tiff_preview(path, img)
            if preview is not None:
                log.info("文件 %s 首个图像仅 %dx%d，改用内嵌预览 %dx%d",
                         path, img.width(), img.height(),
                         preview.width(), preview.height())
                img = preview
        pixels = img.width() * img.height()
        if pixels and file_bytes >= 5 * MB and pixels * 100 < file_bytes:
            return False, (
                f"只解码出 {img.width()}×{img.height()} 预览图"
                f"（文件 {fmt_size(file_bytes)}），可能是 RAW/特殊格式；"
                "请先用相机软件导出为 JPG 再转码")
        data, quality = compress_to_target(
            img, lower, upper, cancel=self._cancel.is_set)
        if self._cancel.is_set():
            raise ImageCancelled()
        if len(data) > upper:  # 双保险：压缩结果必须满足“小于 x-1 MB”
            return False, f"压缩后仍有 {fmt_size(len(data))}，超出目标上限"
        out_path = unique_output_path(out_dir, path, ".jpg")
        try:
            os.makedirs(out_dir, exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(data)
        except OSError as e:
            log.error("写入图片失败: %s (%s)", out_path, e)
            return False, f"写入失败: {e}"
        size = len(data)
        # 下限是质量期望；阈值过小导致区间退化时只看上限
        in_band = size >= lower or lower >= upper
        self.file_result.emit(index, size, in_band)
        note = "" if in_band else f"（低于目标下限 {fmt_mb(lower)}）"
        log.info("图片转码成功: %s -> %s (q%d, %s)",
                 path, out_path, quality, fmt_size(size))
        return True, (f"完成 {fmt_size(size)}（q{quality}{note}）-> "
                      f"{os.path.basename(out_path)}")
