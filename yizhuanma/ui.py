# -*- coding: utf-8 -*-
"""yizhuanma 主界面（PySide6）：拖拽添加视频、输出目录、YouTube 预设
（hover 展示码率表）、任务列表与进度。"""
import logging
import os
import time as _time

from PySide6.QtCore import QPoint, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QKeySequence, QShortcut


def _now() -> float:
    return _time.monotonic()
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import AUTHOR, CONTACT, APP_TITLE, __version__
from .presets import DEFAULT_PRESET, PRESET_NAMES, VIDEO_EXTS, table_html

log = logging.getLogger("yizhuanma")

_VIDEO_EXTS = VIDEO_EXTS

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
    """悬停/点击显示码率表的 ℹ 图标。

    悬停显示：鼠标移开自动消失；点击显示：再点一次关闭。
    """

    def __init__(self, popup, parent=None):
        super().__init__("ℹ", parent)
        self.popup = popup
        self.setToolTip("")
        self.setStyleSheet(
            "color:#3b82f6; font-size:13pt; font-weight:bold;"
            "padding:0 4px;")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._show)
        self._shown_by = None  # 'hover' | 'click'

    def enterEvent(self, e):
        # 窗口刚打开时鼠标可能恰好停在 ℹ 上（Qt 会补发 enter 事件），
        # 此处直接拦截，避免"一打开就弹码率表"
        win = self.window()
        if getattr(win, "_hover_ready_at", 0.0) > _now():
            return
        self._timer.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._timer.stop()
        if self._shown_by == "hover":
            self.popup.hide()
            self._shown_by = None
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        # 点击兜底：hover 失效的环境也能查看码率表；再点一次关闭
        if e.button() == Qt.MouseButton.LeftButton:
            self._timer.stop()
            if self._shown_by:
                self.popup.hide()
                self._shown_by = None
            else:
                self.popup.show_below(self)
                self._shown_by = "click"
        super().mouseReleaseEvent(e)

    def _show(self):  # hover 定时器触发
        # 窗口刚显示 1.5 秒内忽略 hover，避免"一打开就弹窗"
        win = self.window()
        if getattr(win, "_hover_ready_at", 0.0) > _now():
            self._shown_by = None
            return
        self.popup.show_below(self)
        self._shown_by = "hover"


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
        self.title_label = QLabel("")
        self.title_label.setStyleSheet("font-weight:bold; color:#111827;")
        self.note_label = QLabel("按输出短边与帧率自动匹配")
        self.note_label.setStyleSheet("color:#6b7280; font-size:9pt;")
        self.table_label = QLabel("")
        self.table_label.setTextFormat(Qt.TextFormat.RichText)
        self.table_label.setStyleSheet(
            "font-size:9.5pt; "
            "td,th { border:1px solid #e5e7eb; padding:3px 10px; }")
        lay.addWidget(self.title_label)
        lay.addWidget(self.table_label)
        lay.addWidget(self.note_label)
        # 注意：不要在这里调用 hide()——对未显示的 Qt.Window 子窗口
        # hide() 在 Windows 平台会触发 quitOnLastWindowClosed 导致程序退出。
        # QFrame 构造后默认即隐藏，无需额外处理。

    def set_preset(self, preset: str):
        """切换预设时更新标题与码率表"""
        self.title_label.setText(f"{preset} · 标准码率视频")
        self.table_label.setText(table_html(preset))

    def show_below(self, anchor):
        """定位到触发控件（ℹ）正下方显示，不跟随鼠标。"""
        # 内容未设置则不显示（防止空白框）
        if not self.table_label.text():
            return
        self.adjustSize()
        scr = QGuiApplication.primaryScreen().availableGeometry()
        anchor_bottom = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        gx, gy = anchor_bottom.x(), anchor_bottom.y()
        if gx + self.width() > scr.right():
            gx = scr.right() - self.width()
        if gy + self.height() > scr.bottom():
            gy = anchor.mapToGlobal(QPoint(0, 0)).y() - self.height() - 4
        target = QPoint(max(gx, scr.left()), max(gy, scr.top()))
        # 弹窗为无父窗口的独立顶层窗口，move 直接用全局坐标
        self.move(target)
        self.show()
        self.raise_()


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
        self._estimates = {}     # path -> 预计字节数 / -1(无法估算)
        self.worker = None
        self.est_worker = None
        self._hover_ready_at = 0.0
        self._build_ui()
        self._apply_qss()
        # 整个窗口都接受拖入视频（拖到列表/按钮区域也能添加）
        self.setAcceptDrops(True)
        # 延迟 3 秒后台检测更新（不阻塞启动，失败静默不影响使用）
        QTimer.singleShot(3000, self._check_update)

    def _check_update(self):
        if getattr(self, "_update_worker", None) and \
                self._update_worker.isRunning():
            return
        self._update_worker = UpdateWorker(self)
        self._update_worker.update_found.connect(self._on_update_found)
        self._update_worker.start()

    def _on_update_found(self, latest_tag: str, url: str):
        """发现新版本：询问是否前往下载；跳过不影响使用"""
        from .updater import has_update

        if not has_update(__version__, latest_tag):
            return
        box = QMessageBox(self)
        box.setWindowTitle("发现新版本")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            f"发现新版本 {latest_tag}（当前 {__version__}）\n\n"
            "是否前往 GitHub 下载更新？\n"
            "下载后关闭本程序，用新版本替换即可。")
        btn_dl = box.addButton("去下载", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("跳过", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is btn_dl:
            import webbrowser
            webbrowser.open(url)

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

    def closeEvent(self, e):
        # 弹窗是无父窗口的独立顶层窗口，主窗口关闭时需一并关闭
        self.popup.close()
        super().closeEvent(e)

    def showEvent(self, e):
        # 窗口刚显示时鼠标可能恰好停在 ℹ 上（Qt 会补发 enter 事件），
        # 会导致弹窗"一打开就出现"。设置 2 秒的 hover 冷却期。
        self._hover_ready_at = _now() + 2.0
        super().showEvent(e)

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 10)
        root.setSpacing(12)

        # 拖拽区
        self.dropzone = DropZone()
        self.dropzone.on_files_dropped = _SignalForwarder(self._add_files)
        root.addWidget(self.dropzone)

        # 文件列表
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["文件名", "大小", "预计转码后大小", "状态", "操作"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, self.table.horizontalHeader().ResizeMode.Stretch)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 200)
        self.table.setColumnWidth(4, 52)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            self.table.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            self.table.SelectionBehavior.SelectRows)
        # Alt+A 全选列表；右键弹菜单（仅"移除"）
        QShortcut(QKeySequence("Alt+A"), self.table, self.table.selectAll)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            self._show_table_menu)
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
        self.out_edit.setPlaceholderText("默认：第一个视频旁的 已转码 目录")
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
        self.preset_combo.addItems(PRESET_NAMES)
        self.preset_combo.setCurrentText(DEFAULT_PRESET)  # 默认 YouTube
        self.preset_combo.setFixedWidth(150)
        self.popup = RateTablePopup()  # 无父窗口：不随主窗口自动显示
        self.popup.set_preset(DEFAULT_PRESET)
        self.info_label = InfoLabel(self.popup)
        tip = QLabel("悬停或点击 ℹ 查看码率表")
        tip.setStyleSheet("color:#9ca3af; font-size:9pt;")
        preset_row.addWidget(pl)
        preset_row.addWidget(self.preset_combo)
        preset_row.addWidget(self.info_label)
        preset_row.addWidget(tip)
        preset_row.addStretch()
        cl.addLayout(preset_row)
        root.addWidget(card)
        # 切换平台 -> 更新 hover 码率表 + 重新估算
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)

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

        # footer 作者信息 + 仓库地址（不显眼的小字）
        footer = QLabel(
            f"{APP_TITLE} v{__version__}  ·  作者：{AUTHOR}  ·  "
            f"联系方式：{CONTACT}\n"
            "项目地址：github.com/paidaxing306/yi-zhuanma")
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(footer)

    def _on_preset_changed(self, idx):
        preset = self.preset_combo.itemText(idx) or DEFAULT_PRESET
        self.popup.set_preset(preset)
        self._start_estimate()

    def _apply_qss(self):
        QApplication.instance().setStyleSheet(_QSS)

    # ---------- 文件 ----------
    _FILE_DIALOG_FILTER = (
        "视频文件 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm "
        "*.ts *.m4v *.3gp *.mpg *.mpeg);;所有文件 (*)")

    def _add_files(self, paths):
        if paths is None:
            # 弹出菜单：选视频文件 / 选文件夹（导入目录内全部视频）
            menu = QMenu(self)
            act_file = menu.addAction("选择视频文件…")
            act_dir = menu.addAction("选择文件夹（导入目录内全部视频）…")
            chosen = menu.exec(QCursor.pos())
            if chosen is act_file:
                paths = QFileDialog.getOpenFileNames(
                    self, "选择视频", "", self._FILE_DIALOG_FILTER)[0]
            elif chosen is act_dir:
                d = QFileDialog.getExistingDirectory(self, "选择文件夹")
                paths = self._videos_in_dir(d) if d else []
            else:
                return
        else:
            # 拖拽进来的可能是目录：展开为其中的视频文件
            expanded = []
            for p in paths:
                if os.path.isdir(p):
                    expanded.extend(self._videos_in_dir(p))
                else:
                    expanded.append(p)
            paths = expanded
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
            # 输出目录 = 第一个视频所在目录下的「已转码」子目录
            self._set_output_dir_from_first_video()
            self._refresh_table()
            self.status.setText(f"已添加 {added} 个视频")
            log.info("添加 %d 个视频: %s", added,
                     [os.path.basename(f[0]) for f in self.files[-added:]])
            self._start_estimate()

    def _videos_in_dir(self, d: str) -> list:
        """递归列出目录内所有视频文件（按文件名排序）"""
        exts = tuple(_VIDEO_EXTS)
        result = []
        for root, _dirs, names in os.walk(d):
            for n in sorted(names):
                if n.lower().endswith(exts):
                    result.append(os.path.join(root, n))
        return result

    def _set_output_dir_from_first_video(self):
        """在第一个视频所在目录创建「已转码」子目录并设为输出目录"""
        if not self.files:
            return
        first_dir = os.path.dirname(self.files[0][0])
        out_dir = os.path.join(first_dir, "已转码")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError:
            log.warning("创建输出目录失败: %s", out_dir)
            return
        self.out_edit.setText(out_dir)

    def _refresh_table(self):
        self.table.setRowCount(len(self.files))
        for i, (p, name, size) in enumerate(self.files):
            self.table.setItem(i, 0, QTableWidgetItem(name))
            it = QTableWidgetItem(_human_size(size))
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(i, 1, it)
            est = self._estimates.get(p)
            if est is None:
                est_text = "计算中…"
            elif est == -1:
                est_text = "—"
            else:
                est_text = _human_size(est)
            eit = QTableWidgetItem(est_text)
            eit.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                 | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(i, 2, eit)
            self.table.setItem(i, 3, QTableWidgetItem("等待中"))
            # 单行移除按钮（大写 X；必须 padding:0，否则全局按钮样式的
            # padding 会把 26px 宽按钮里的文字挤出可视区，显示为空白）
            btn = QPushButton("X")
            btn.setFixedSize(26, 24)
            btn.setToolTip("移除该文件")
            btn.setStyleSheet(
                "QPushButton { background:transparent; border:none;"
                "padding:0; color:#6b7280; font-size:12pt;"
                "font-weight:bold; }"
                "QPushButton:hover { color:#dc2626; }")
            btn.clicked.connect(lambda _=False, idx=i: self._remove_file(idx))
            self.table.setCellWidget(i, 4, btn)

    def _remove_file(self, idx):
        if self.worker and self.worker.isRunning():
            return  # 转码中不允许移除
        if 0 <= idx < len(self.files):
            removed = self.files.pop(idx)[1]
            self._estimates.pop(removed, None)
            self._refresh_table()
            self.status.setText(
                f"已移除 {removed}，剩余 {len(self.files)} 个")
            self._start_estimate()

    def _show_table_menu(self, pos):
        """右键文件列表：菜单里只有"移除"，移除当前选中（单个或多个）"""
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            return
        menu = QMenu(self.table)
        act = menu.addAction("移除" if len(rows) == 1
                             else f"移除选中（{len(rows)} 个）")
        if menu.exec(self.table.viewport().mapToGlobal(pos)) is act:
            self._remove_rows(rows)

    def _remove_rows(self, rows):
        if self.worker and self.worker.isRunning():
            return  # 转码中不允许移除
        for idx in sorted(rows, reverse=True):
            if 0 <= idx < len(self.files):
                path, _name, _size = self.files.pop(idx)
                self._estimates.pop(path, None)
        self._refresh_table()
        self.status.setText(f"已移除，剩余 {len(self.files)} 个")
        self._start_estimate()

    def _choose_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.out_edit.setText(d)

    def _clear(self):
        if self.worker and self.worker.isRunning():
            return
        self.files.clear()
        self._estimates.clear()
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.status.setText("就绪")

    # ---------- 预计大小估算 ----------
    def _start_estimate(self):
        if self.est_worker and self.est_worker.isRunning():
            self.est_worker.requestInterruption()
        self.est_worker = EstimateWorker(
            [(p, n) for p, n, _s in self.files],
            self.preset_combo.currentText(), self)
        self.est_worker.estimate_ready.connect(self._on_estimate)
        self.est_worker.start()

    def _on_estimate(self, idx, est_bytes):
        if 0 <= idx < len(self.files):
            p = self.files[idx][0]
            self._estimates[p] = est_bytes if est_bytes is not None else -1
            item = self.table.item(idx, 2)
            if item:
                item.setText(_human_size(est_bytes)
                             if est_bytes is not None else "—")

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
        log.info("开始转码: %d 个文件, 输出目录=%r, 预设=%s", len(self.files),
                 out_dir or "(视频同目录)", self.preset_combo.currentText())
        self.worker = TranscodeWorker(
            list(self.files), out_dir,
            self.preset_combo.currentText(), "标准码率视频",
            self)
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
        # 转码完成后默认打开输出目录，让用户直接看到结果
        self._open_output_dir()

    def _open_output_dir(self):
        """在系统文件管理器中打开输出目录"""
        import subprocess
        import sys as _sys

        out_dir = self.out_edit.text().strip()
        if not out_dir or not os.path.isdir(out_dir):
            return
        try:
            if _sys.platform == "win32":
                os.startfile(out_dir)  # noqa: S606
            elif _sys.platform == "darwin":
                subprocess.Popen(["open", out_dir])
            else:
                subprocess.Popen(["xdg-open", out_dir])
            log.info("已打开输出目录: %s", out_dir)
        except OSError:
            log.warning("打开输出目录失败: %s", out_dir)


class EstimateWorker(QThread):
    """后台探测视频并估算转码后大小（每个文件一次 ffprobe）"""

    estimate_ready = Signal(int, object)  # index, 字节数或 None

    def __init__(self, files: list, preset: str = DEFAULT_PRESET,
                 parent=None):
        super().__init__(parent)
        self.files = files  # [(path, name)]
        self.preset = preset

    def run(self):
        from .transcoder import estimate_output_size, probe
        for i, (path, _name) in enumerate(self.files):
            if self.isInterruptionRequested():
                return
            try:
                est = estimate_output_size(probe(path), self.preset)
            except Exception:  # noqa: BLE001 探测失败按无法估算处理
                est = None
            self.estimate_ready.emit(i, est)


class UpdateWorker(QThread):
    """后台查询 GitHub 最新 release（不阻塞界面，失败静默）"""

    update_found = Signal(str, str)  # latest_tag, 下载页URL

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        from .updater import check_latest
        result = check_latest()
        if result:
            self.update_found.emit(result[0], result[1])


class _SignalForwarder:
    """极简信号转发：拖拽区回调触发 _add_files"""

    def __init__(self, cb):
        self.cb = cb

    def emit(self, *args):
        self.cb(*args)
