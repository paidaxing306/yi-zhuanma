# -*- coding: utf-8 -*-
"""yizhuanma 主界面（PySide6）：拖拽添加视频、输出目录、YouTube 预设
（hover 展示码率表）、任务列表与进度。"""
import logging
import os

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import AUTHOR, CONTACT, APP_TITLE, __version__
from .presets import PRESETS, PRESET_YOUTUBE, table_html

log = logging.getLogger("yizhuanma")

_VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv",
               ".webm", ".ts", ".m4v", ".3gp", ".mpg", ".mpeg"}

_QSS = """
QMainWindow, QWidget { background: #f5f6fa; color: #1f2937;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif; font-size: 10pt; }
QFrame#card { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; }
QLabel#title { font-size: 20pt; font-weight: bold; color: #111827; }
QLabel#subtitle { color: #6b7280; font-size: 9.5pt; }
QLabel#dropHint { font-size: 12pt; color: #6b7280; }
QLabel#fieldLabel { color: #374151; font-weight: bold; }
QLabel#footer { color: #9ca3af; font-size: 9pt; }
QFrame#dropzone { background: #fafbff; border: 2px dashed #c7d2fe;
    border-radius: 12px; }
QFrame#dropzone[dragActive="true"] { background: #eef2ff;
    border: 2px dashed #3b82f6; }
QPushButton { background: #ffffff; border: 1px solid #d1d5db;
    border-radius: 6px; padding: 6px 14px; }
QPushButton:hover { border-color: #3b82f6; color: #3b82f6; }
QPushButton#primary { background: #3b82f6; color: white; border: none;
    font-weight: bold; font-size: 11pt; padding: 9px 26px; }
QPushButton#primary:hover { background: #2563eb; }
QPushButton#primary:disabled { background: #93c5fd; }
QLineEdit, QComboBox { background: #ffffff; border: 1px solid #d1d5db;
    border-radius: 6px; padding: 5px 8px; }
QLineEdit:focus, QComboBox:focus { border-color: #3b82f6; }
QTableWidget { background: #ffffff; border: 1px solid #e5e7eb;
    border-radius: 8px; gridline-color: #f3f4f6; }
QTableWidget::item { padding: 4px; }
QHeaderView::section { background: #f9fafb; border: none;
    border-bottom: 1px solid #e5e7eb; padding: 6px; font-weight: bold; }
QProgressBar { border: none; border-radius: 5px; background: #e5e7eb;
    height: 10px; text-align: center; }
QProgressBar::chunk { background: #3b82f6; border-radius: 5px; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #d1d5db; border-radius: 5px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class InfoLabel(QLabel):
    """悬停/点击显示码率表的 ℹ 图标"""

    def __init__(self, popup, parent=None):
        super().__init__("ℹ", parent)
        self.popup = popup
        self.setToolTip("")
        self.setStyleSheet(
            "color:#3b82f6; font-size:13pt; font-weight:bold;"
            "padding:0 4px;")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._show)
        self._visible = False

    def enterEvent(self, e):
        self._timer.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._timer.stop()
        if not self._visible:
            self.popup.hide()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        # 点击兜底：hover 失效的环境也能查看码率表
        if e.button() == Qt.MouseButton.LeftButton:
            self._timer.stop()
            if self._visible:
                self.popup.hide()
                self._visible = False
            else:
                self.popup.show_near_cursor()
                self._visible = True
        super().mouseReleaseEvent(e)

    def _show(self):
        self.popup.show_near_cursor()
        self._visible = True


class RateTablePopup(QFrame):
    """码率表悬浮卡片（鼠标穿透，不抢焦点）。

    注意：不使用 Qt.ToolTip 窗口标志 —— 在远程桌面等环境下
    ToolTip 窗口经常不显示；普通置顶窗口更可靠。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                          True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(
            "QFrame { background:#ffffff; border:1px solid #d1d5db;"
            "border-radius:8px; }"
            "QLabel { background:transparent; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        title = QLabel(f"{PRESET_YOUTUBE} · 标准码率视频")
        title.setStyleSheet("font-weight:bold; color:#111827;")
        note = QLabel("按输出短边与帧率自动匹配")
        note.setStyleSheet("color:#6b7280; font-size:9pt;")
        table = QLabel(table_html())
        table.setTextFormat(Qt.TextFormat.RichText)
        table.setStyleSheet(
            "font-size:9.5pt; "
            "td,th { border:1px solid #e5e7eb; padding:3px 10px; }")
        lay.addWidget(title)
        lay.addWidget(table)
        lay.addWidget(note)

    def show_near_cursor(self):
        gpos = QCursor.pos()
        self.adjustSize()
        scr = QGuiApplication.primaryScreen().availableGeometry()
        gx, gy = gpos.x() + 18, gpos.y() + 18
        if gx + self.width() > scr.right():
            gx = gpos.x() - self.width() - 18
        if gy + self.height() > scr.bottom():
            gy = gpos.y() - self.height() - 18
        target = QPoint(max(gx, scr.left()), max(gy, scr.top()))
        # 窗口带父窗口时 move() 使用相对父窗口坐标，需把全局坐标转换过去
        if self.parentWidget():
            self.move(self.parentWidget().mapFromGlobal(target))
        else:
            self.move(target)
        self.show()


class DropZone(QFrame):
    """可点击的拖拽区"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setProperty("dragActive", False)
        self.setMinimumHeight(130)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("⬇")
        icon.setStyleSheet("font-size:26pt; color:#93c5fd;"
                           "background:transparent;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("拖入视频文件，或点击此处选择")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("支持 mp4 / avi / mkv / mov / wmv / flv / webm 等")
        sub.setStyleSheet("color:#9ca3af; font-size:9pt;"
                          "background:transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)
        lay.addWidget(hint)
        lay.addWidget(sub)
        self.setAcceptDrops(True)

    def _set_drag(self, active: bool):
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._set_drag(True)
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._set_drag(False)
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        self._set_drag(False)
        urls = e.mimeData().urls()
        files = [u.toLocalFile() for u in urls
                 if u.isLocalFile() and u.toLocalFile().lower()
                 .endswith(tuple(_VIDEO_EXTS))]
        if files:
            self.on_files_dropped.emit(files)
        e.acceptProposedAction()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.on_files_dropped.emit(None)
        super().mouseReleaseEvent(e)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(920, 680)
        self.files = []          # [(abs_path, display_name, size)]
        self.worker = None
        self._build_ui()
        self._apply_qss()
        # 整个窗口都接受拖入视频（拖到列表/按钮区域也能添加）
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        files = [u.toLocalFile() for u in urls
                 if u.isLocalFile() and u.toLocalFile().lower()
                 .endswith(tuple(_VIDEO_EXTS))]
        if files:
            self._add_files(files)
        e.acceptProposedAction()

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 10)
        root.setSpacing(12)

        # 标题
        title_row = QHBoxLayout()
        left = QVBoxLayout()
        t = QLabel(APP_TITLE)
        t.setObjectName("title")
        st = QLabel("视频格式转换 · 自动匹配码率 · 有显卡优先硬件编码")
        st.setObjectName("subtitle")
        left.addWidget(t)
        left.addWidget(st)
        title_row.addLayout(left)
        title_row.addStretch()
        root.addLayout(title_row)

        # 拖拽区
        self.dropzone = DropZone()
        self.dropzone.on_files_dropped = _SignalForwarder(self._add_files)
        root.addWidget(self.dropzone)

        # 文件列表
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "状态", ""])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 44)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            self.table.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            self.table.SelectionBehavior.SelectRows)
        root.addWidget(self.table, stretch=1)

        # 输出目录 + 预设卡片
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(10)

        out_row = QHBoxLayout()
        lbl = QLabel("输出目录")
        lbl.setObjectName("fieldLabel")
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("留空 = 输出到视频所在目录")
        btn_out = QPushButton("选择…")
        btn_out.clicked.connect(self._choose_outdir)
        out_row.addWidget(lbl)
        out_row.addWidget(self.out_edit, stretch=1)
        out_row.addWidget(btn_out)
        cl.addLayout(out_row)

        preset_row = QHBoxLayout()
        pl = QLabel("预设")
        pl.setObjectName("fieldLabel")
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(PRESETS.keys()))
        self.preset_combo.setFixedWidth(150)
        self.tier_combo = QComboBox()
        self.tier_combo.addItems(PRESETS[PRESET_YOUTUBE]["tiers"])
        self.tier_combo.setFixedWidth(150)
        self.popup = RateTablePopup(self)
        self.info_label = InfoLabel(self.popup)
        tip = QLabel("悬停或点击 ℹ 查看码率表")
        tip.setStyleSheet("color:#9ca3af; font-size:9pt;")
        preset_row.addWidget(pl)
        preset_row.addWidget(self.preset_combo)
        preset_row.addWidget(self.tier_combo)
        preset_row.addWidget(self.info_label)
        preset_row.addWidget(tip)
        preset_row.addStretch()
        cl.addLayout(preset_row)
        root.addWidget(card)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("开始转码")
        self.btn_start.setObjectName("primary")
        self.btn_start.setFixedWidth(150)
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.clicked.connect(self._clear)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # 进度
        prog_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color:#6b7280;")
        prog_row.addWidget(self.progress, stretch=1)
        prog_row.addWidget(self.status)
        root.addLayout(prog_row)

        # footer 作者信息
        footer = QLabel(
            f"{APP_TITLE} v{__version__}  ·  作者：{AUTHOR}  ·  "
            f"联系方式：{CONTACT}")
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(footer)

    def _apply_qss(self):
        QApplication.instance().setStyleSheet(_QSS)

    # ---------- 文件 ----------
    def _add_files(self, paths):
        if paths is None:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "选择视频", "",
                "视频文件 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm "
                "*.ts *.m4v *.3gp *.mpg *.mpeg);;所有文件 (*)")
        if not paths:
            return
        existing = {p for p, _n, _s in self.files}
        added = 0
        for p in paths:
            p = os.path.abspath(p)
            if p in existing:
                continue
            try:
                size = os.path.getsize(p)
            except OSError:
                size = 0
            self.files.append((p, os.path.basename(p), size))
            existing.add(p)
            added += 1
        if added:
            self._refresh_table()
            self.status.setText(f"已添加 {added} 个视频")
            log.info("添加 %d 个视频: %s", added,
                     [os.path.basename(f[0]) for f in self.files[-added:]])

    def _refresh_table(self):
        self.table.setRowCount(len(self.files))
        for i, (_p, name, size) in enumerate(self.files):
            self.table.setItem(i, 0, QTableWidgetItem(name))
            it = QTableWidgetItem(_human_size(size))
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(i, 1, it)
            self.table.setItem(i, 2, QTableWidgetItem("等待中"))
            # 单行移除按钮
            btn = QPushButton("✕")
            btn.setFixedSize(26, 24)
            btn.setToolTip("移除该文件")
            btn.setStyleSheet(
                "QPushButton { background:transparent; border:none;"
                "color:#9ca3af; font-size:11pt; font-weight:bold; }"
                "QPushButton:hover { color:#dc2626; }")
            btn.clicked.connect(lambda _=False, idx=i: self._remove_file(idx))
            self.table.setCellWidget(i, 3, btn)

    def _remove_file(self, idx):
        if self.worker and self.worker.isRunning():
            return  # 转码中不允许移除
        if 0 <= idx < len(self.files):
            removed = self.files.pop(idx)[1]
            self._refresh_table()
            self.status.setText(
                f"已移除 {removed}，剩余 {len(self.files)} 个")

    def _choose_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.out_edit.setText(d)

    def _clear(self):
        if self.worker and self.worker.isRunning():
            return
        self.files.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.status.setText("就绪")

    # ---------- 转码 ----------
    def _start(self):
        if not self.files:
            log.warning("点击开始但无视频文件")
            QMessageBox.information(self, "提示", "请先添加视频文件")
            return
        from . import ffmpeg_util
        from .transcoder import TranscodeWorker

        has_ff, has_fp = ffmpeg_util.check_available()
        if not (has_ff and has_fp):
            log.error("ffmpeg/ffprobe 缺失: ffmpeg=%s ffprobe=%s",
                      has_ff, has_fp)
            QMessageBox.critical(
                self, "错误",
                "未找到 ffmpeg/ffprobe，无法转码。\n"
                "请确认软件文件完整（ffmpeg.exe、ffprobe.exe 需随程序一起分发）。")
            return

        out_dir = self.out_edit.text().strip()
        log.info("开始转码: %d 个文件, 输出目录=%r", len(self.files),
                 out_dir or "(视频同目录)")
        self.worker = TranscodeWorker(list(self.files), out_dir, self)
        self.worker.file_started.connect(self._on_file_started)
        self.worker.file_progress.connect(self._on_file_progress)
        self.worker.file_finished.connect(self._on_file_finished)
        self.worker.all_finished.connect(self._on_all_finished)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_clear.setEnabled(False)
        self.dropzone.setEnabled(False)
        self.progress.setValue(0)
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
            self.status.setText("正在取消…")

    def _set_row_status(self, i: int, text: str, color: str = "#374151"):
        item = self.table.item(i, 2)
        item.setText(text)
        item.setForeground(QColor(color))

    def _on_file_started(self, i, name, desc):
        self._set_row_status(i, f"转码中 0%", "#3b82f6")
        self.status.setText(f"[{i + 1}/{len(self.files)}] {name}  {desc}")

    def _on_file_progress(self, i, pct):
        if pct < 0:
            self._set_row_status(i, "转码中…", "#3b82f6")
            self.progress.setRange(0, 0)
        else:
            self._set_row_status(i, f"转码中 {pct}%", "#3b82f6")
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)

    def _on_file_finished(self, i, ok, msg):
        if ok:
            self._set_row_status(i, "✓ 完成", "#16a34a")
        else:
            self._set_row_status(i, "✗ " + msg, "#dc2626")

    def _on_all_finished(self, ok_count, fail_count):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_clear.setEnabled(True)
        self.dropzone.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if fail_count == 0 else self.progress.value())
        total = ok_count + fail_count
        if fail_count:
            self.status.setText(f"完成：成功 {ok_count} / 失败 {fail_count} / 共 {total}")
        else:
            self.status.setText(f"全部完成：{total} 个视频转码成功")


class _SignalForwarder:
    """极简信号转发：拖拽区回调触发 _add_files"""

    def __init__(self, cb):
        self.cb = cb

    def emit(self, *args):
        self.cb(*args)
