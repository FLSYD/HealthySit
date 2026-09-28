"""
状态面板组件
显示实时姿态数据和统计信息
四个角度数据始终全量显示，未检测到时显示 --
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class StatusPanel(ttk.Frame):
    """状态面板组件"""

    COLOR_NORMAL = "#00D084"
    COLOR_WARNING = "#FFA500"
    COLOR_DANGER = "#FF4757"
    COLOR_INFO = "#3498DB"
    COLOR_BG = "#FFFFFF"
    COLOR_TEXT = "#2C3E50"
    COLOR_CARD_BG = "#F8F9FA"
    COLOR_FRONT = "#2980B9"   # 正坐模式
    COLOR_SIDE = "#8E44AD"    # 侧坐模式
    COLOR_WAITING = "#95A5A6" # 等待监测

    def __init__(self, parent):
        super().__init__(parent)

        self.current_status = "等待开始"
        self.status_color = self.COLOR_INFO
        self.current_view = "waiting"  # waiting | front | side

        # 角度数据变量
        self.neck_angle_var = tk.StringVar(value="--")
        self.head_forward_angle_var = tk.StringVar(value="--")
        self.torso_angle_var = tk.StringVar(value="--")
        self.shoulder_diff_var = tk.StringVar(value="--")
        self.sitting_time_var = tk.StringVar(value="00:00:00")
        self.violations_var = tk.StringVar(value="0")
        self.view_indicator_var = tk.StringVar(value="等待监测")

        self._setup_ui()

    def _setup_ui(self):
        """设置UI"""
        main_frame = ttk.Frame(self, style='Card.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # 标题
        ttk.Label(
            main_frame,
            text="监测状态",
            font=("Microsoft YaHei", 13, "bold"),
            foreground="#1E3A5F"
        ).pack(anchor=tk.W, pady=(0, 8))

        # 视角指示器（放大并放在状态上方）
        self._create_view_indicator(main_frame)

        # 状态卡片（视角指示器下方）
        self.status_card = self._create_status_card(main_frame)

        # 角度数据卡片（始终全量显示四个数据）
        angle_card = tk.Frame(main_frame, bg=self.COLOR_CARD_BG, relief=tk.FLAT, bd=0)
        angle_card.pack(fill=tk.X, pady=(12, 0))

        self._create_data_labels(angle_card)

        # 数据统计卡片（下方）
        stats_card = tk.Frame(main_frame, bg=self.COLOR_CARD_BG, relief=tk.FLAT, bd=0)
        stats_card.pack(fill=tk.X, pady=(12, 0))

        self._create_stats_labels(stats_card)

    def _create_status_card(self, parent):
        """创建状态卡片"""
        card = tk.Frame(parent, bg=self.COLOR_CARD_BG, relief=tk.FLAT, bd=0)
        card.pack(fill=tk.X)

        indicator_frame = tk.Frame(card, bg=self.status_color, width=8)
        indicator_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        status_frame = tk.Frame(card, bg=self.COLOR_CARD_BG)
        status_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.status_label = tk.Label(
            status_frame,
            text=self.current_status,
            font=("Microsoft YaHei", 20, "bold"),
            fg=self.status_color,
            bg=self.COLOR_CARD_BG,
            anchor=tk.W
        )
        self.status_label.pack(anchor=tk.W)

        self.status_desc_label = tk.Label(
            status_frame,
            text="点击「开始监测」启动系统",
            font=("Microsoft YaHei", 10),
            fg="#7F8C8D",
            bg=self.COLOR_CARD_BG,
            anchor=tk.W
        )
        self.status_desc_label.pack(anchor=tk.W)

        return card

    def _create_view_indicator(self, parent):
        """创建视角指示器（放大版）"""
        card = tk.Frame(parent, bg=self.COLOR_CARD_BG, relief=tk.FLAT, bd=0)
        card.pack(fill=tk.X, pady=(0, 6))

        view_icon = tk.Frame(card, bg=self.COLOR_WAITING, width=8)
        view_icon.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        view_icon.pack_propagate(False)

        view_label = tk.Label(
            card,
            textvariable=self.view_indicator_var,
            font=("Microsoft YaHei", 13, "bold"),
            fg=self.COLOR_WAITING,
            bg=self.COLOR_CARD_BG,
            anchor=tk.W
        )
        view_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._view_indicator_icon = view_icon

    def _create_data_labels(self, parent):
        """创建角度数据标签（始终全量显示四个数据）"""
        ttk.Label(
            parent,
            text="角度数据",
            font=("Microsoft YaHei", 11, "bold"),
            foreground="#1E3A5F"
        ).pack(anchor=tk.W, padx=12, pady=(8, 4))

        self._create_data_row(parent, "头部侧倾:", self.neck_angle_var, unit="°")
        self._create_data_row(parent, "肩膀倾斜:", self.shoulder_diff_var, unit="°")
        self._create_data_row(parent, "头部前倾:", self.head_forward_angle_var, unit="°")
        self._create_data_row(parent, "躯干倾斜:", self.torso_angle_var, unit="°")

    def _create_data_row(self, parent, label_text, variable, unit: str = ""):
        """创建数据行"""
        row = tk.Frame(parent, bg=self.COLOR_CARD_BG)
        row.pack(fill=tk.X, padx=12, pady=3)

        tk.Label(
            row,
            text=label_text,
            font=("Microsoft YaHei", 11),
            fg="#7F8C8D",
            bg=self.COLOR_CARD_BG,
            width=10,
            anchor=tk.W
        ).pack(side=tk.LEFT)

        value_frame = tk.Frame(row, bg=self.COLOR_CARD_BG)
        value_frame.pack(side=tk.LEFT)

        tk.Label(
            value_frame,
            textvariable=variable,
            font=("Consolas", 16, "bold"),
            fg=self.COLOR_TEXT,
            bg=self.COLOR_CARD_BG,
            anchor=tk.W
        ).pack(side=tk.LEFT)

        if unit:
            tk.Label(
                value_frame,
                text=unit,
                font=("Microsoft YaHei", 10),
                fg="#95A5A6",
                bg=self.COLOR_CARD_BG,
                anchor=tk.W
            ).pack(side=tk.LEFT, padx=(2, 0))

    def _create_stats_labels(self, parent):
        """创建统计标签"""
        ttk.Label(
            parent,
            text="数据统计",
            font=("Microsoft YaHei", 11, "bold"),
            foreground="#1E3A5F"
        ).pack(anchor=tk.W, padx=12, pady=(8, 4))

        self._create_data_row(parent, "久坐时间:", self.sitting_time_var)
        self._create_data_row(parent, "违规次数:", self.violations_var)

    def _update_view_indicator(self, view: str):
        """更新视角指示器"""
        if view == self.current_view:
            return
        self.current_view = view

        if view == "waiting":
            self.view_indicator_var.set("等待监测")
            self._view_indicator_icon.config(bg=self.COLOR_WAITING)
            lbl = self._find_view_label()
            if lbl is not None:
                lbl.config(fg=self.COLOR_WAITING)
        elif view == "front":
            self.view_indicator_var.set("正坐模式")
            self._view_indicator_icon.config(bg=self.COLOR_FRONT)
            lbl = self._find_view_label()
            if lbl is not None:
                lbl.config(fg=self.COLOR_FRONT)
        else:
            self.view_indicator_var.set("侧坐模式")
            self._view_indicator_icon.config(bg=self.COLOR_SIDE)
            lbl = self._find_view_label()
            if lbl is not None:
                lbl.config(fg=self.COLOR_SIDE)

    def _find_view_label(self):
        """找到视角指示器文字标签（用于更新颜色）"""
        card = self._view_indicator_icon.master
        for child in card.winfo_children():
            if isinstance(child, tk.Label) and str(child.cget('textvariable')) == str(self.view_indicator_var):
                return child
        return None

    def update_status(self, status: str, description: str = ""):
        """更新状态显示"""
        self.current_status = status
        self.status_label.config(text=status)

        if description:
            self.status_desc_label.config(text=description)

        if "正常" in status or "healthy" in status.lower():
            color = self.COLOR_NORMAL
        elif "肩膀" in status or "前倾" in status:
            color = self.COLOR_WARNING   # 肩膀倾斜/头部前倾：橙色
        elif "侧倾" in status or "驼背" in status:
            color = self.COLOR_DANGER    # 头部侧倾/躯干倾斜：红色
        elif "等待" in status or "暂停" in status:
            color = self.COLOR_INFO
        else:
            color = self.COLOR_WARNING

        self.status_color = color
        self.status_label.config(fg=color)

        for widget in self.status_card.winfo_children():
            if isinstance(widget, tk.Frame) and widget.cget('bg') in [
                    self.COLOR_NORMAL, self.COLOR_DANGER,
                    self.COLOR_INFO, self.COLOR_WARNING]:
                widget.config(bg=color)

    def update_data(self, neck_angle: Optional[float] = None,
                   head_forward_angle: Optional[float] = None,
                   torso_angle: Optional[float] = None,
                   shoulder_diff: Optional[float] = None,
                   sitting_time: int = 0,
                   violations: int = 0,
                   fps: float = 0,
                   sitting_view: str = "front"):
        """更新数据显示（始终全量显示四个数据，未检测到显示 --）"""
        self._update_view_indicator(sitting_view)

        # 四个角度数据始终全量显示，无数据时显示 --
        if neck_angle is not None:
            self.neck_angle_var.set(f"{abs(neck_angle):.1f}")
        else:
            self.neck_angle_var.set("--")

        if head_forward_angle is not None:
            self.head_forward_angle_var.set(f"{head_forward_angle:.1f}")
        else:
            self.head_forward_angle_var.set("--")

        if torso_angle is not None:
            self.torso_angle_var.set(f"{abs(torso_angle):.1f}")
        else:
            self.torso_angle_var.set("--")

        if shoulder_diff is not None:
            self.shoulder_diff_var.set(f"{abs(shoulder_diff):.1f}")
        else:
            self.shoulder_diff_var.set("--")

        hours = sitting_time // 3600
        minutes = (sitting_time % 3600) // 60
        seconds = sitting_time % 60
        self.sitting_time_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

        self.violations_var.set(str(violations))

    def set_waiting(self):
        """设置等待状态"""
        self.update_status("等待开始", "点击「开始监测」启动系统")
        self.neck_angle_var.set("--")
        self.head_forward_angle_var.set("--")
        self.torso_angle_var.set("--")
        self.shoulder_diff_var.set("--")
        self._update_view_indicator("waiting")

    def set_running(self):
        """设置运行状态"""
        self.update_status("监测中", "正在分析坐姿...")

    def set_paused(self):
        """设置暂停状态"""
        self.update_status("已暂停", "点击「继续监测」恢复")
        self._update_view_indicator("waiting")

    def set_error(self, message: str):
        """设置错误状态"""
        self.update_status("连接错误", message)
