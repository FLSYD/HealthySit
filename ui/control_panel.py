"""
控制面板组件
提供系统控制按钮和操作界面
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)


class ControlPanel(ttk.Frame):
    """控制面板组件"""

    BTN_SUCCESS_BG = "#27AE60"       # 绿色 - 开始
    BTN_WARNING_BG = "#E67E22"       # 橙色 - 暂停
    BTN_HISTORY_BG = "#8E44AD"      # 紫色 - 健康历史
    BTN_SECONDARY_BG = "#7F8C8D"     # 灰色 - 次要
    BTN_DANGER_BG = "#E74C3C"        # 红色 - 结束

    def __init__(self, parent):
        super().__init__(parent)

        self.on_start: Optional[Callable] = None
        self.on_pause: Optional[Callable] = None
        self.on_stop: Optional[Callable] = None
        self.on_settings: Optional[Callable] = None
        self.on_history: Optional[Callable] = None
        self.on_reset: Optional[Callable] = None

        self.monitoring_state = 0  # 0=未开始, 1=运行中, 2=已暂停

        self._setup_ui()
        self._update_button_states()

    def _setup_ui(self):
        """设置UI"""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.X, padx=20, pady=(12, 8))

        btn_container = tk.Frame(main_frame, bg='#FFFFFF')
        btn_container.pack(fill=tk.X, pady=(0, 8))

        btn_width = 14

        # 按钮顺序：开始监测 | 结束监测 | 重置统计 | 健康历史 | 系统设置
        buttons = [
            ("开始监测", self.BTN_SUCCESS_BG, self._on_start_click),
            ("结束监测", self.BTN_DANGER_BG, self._on_stop_click),
            ("重置统计", "#95A5A6", self._on_reset_click),
            ("健康历史", self.BTN_HISTORY_BG, self._on_history_click),
            ("系统设置", self.BTN_SECONDARY_BG, self._on_settings_click),
        ]

        buttons_widgets = []
        for i, (text, color, cmd) in enumerate(buttons):
            btn = self._create_button(
                btn_container,
                text=text,
                command=cmd,
                bg=color,
                width=btn_width
            )
            btn.pack(side=tk.LEFT, padx=(0, 8 if i < len(buttons) - 1 else 0), ipadx=12, ipady=4)
            buttons_widgets.append(btn)

        # 保存按钮引用
        self.start_btn = buttons_widgets[0]
        self.stop_btn = buttons_widgets[1]
        self.reset_btn = buttons_widgets[2]
        self.history_btn = buttons_widgets[3]
        self.settings_btn = buttons_widgets[4]

        self.hint_label = tk.Label(
            main_frame,
            text="提示: 请确保摄像头已连接且正对您的上半身",
            font=("Microsoft YaHei", 10),
            fg="#95A5A6",
            bg="#FFFFFF",
            anchor=tk.W
        )
        self.hint_label.pack(anchor=tk.W, pady=(4, 0))

    def _create_button(self, parent, text: str, command: Callable,
                      bg: str, width: int = 14) -> tk.Button:
        """创建样式化按钮"""
        btn = tk.Button(
            parent,
            text=text,
            font=("Microsoft YaHei", 11, "bold"),
            fg="#FFFFFF",
            bg=bg,
            activebackground=self._darken_color(bg),
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=command
        )
        def on_enter(e):
            btn._hover_bg = btn.cget('bg')
            btn.config(bg=self._darken_color(btn._hover_bg))
        def on_leave(e):
            self._update_button_states()
            if btn not in (self.start_btn, self.stop_btn):
                btn.config(bg=bg)
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    def _darken_color(self, hex_color: str, factor: float = 0.85) -> str:
        """使颜色变深"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _on_start_click(self):
        """开始/暂停/继续按钮点击处理"""
        if self.monitoring_state == 0:
            if self.on_start and self.on_start() is not False:
                self.set_monitoring_state(1)
        elif self.monitoring_state == 1:
            if self.on_pause:
                self.on_pause()
        elif self.monitoring_state == 2:
            if self.on_start and self.on_start() is not False:
                self.set_monitoring_state(1)

    def _on_stop_click(self):
        """结束监测按钮点击处理"""
        if self.monitoring_state != 0:
            if messagebox.askyesno("确认结束", "确定要结束当前监测会话吗？"):
                if self.on_stop:
                    self.on_stop()

    def set_monitoring_state(self, state: int):
        """由监测生命周期统一同步按钮状态。"""
        self.monitoring_state = state
        self._update_button_states()

    def set_busy(self, busy: bool):
        """等待后台资源释放时禁止重复启动或重置。"""
        state = tk.DISABLED if busy else tk.NORMAL
        self.start_btn.config(state=state)
        self.reset_btn.config(state=state)
        if busy:
            self.stop_btn.config(state=tk.DISABLED)
        else:
            self._update_button_states()

    def _update_button_states(self):
        """更新按钮状态"""
        if self.monitoring_state == 0:
            self.start_btn.config(text="开始监测", bg=self.BTN_SUCCESS_BG)
            self.stop_btn.config(state=tk.DISABLED)
        elif self.monitoring_state == 1:
            self.start_btn.config(text="暂停监测", bg=self.BTN_WARNING_BG)
            self.stop_btn.config(state=tk.NORMAL)
        elif self.monitoring_state == 2:
            self.start_btn.config(text="继续监测", bg=self.BTN_SUCCESS_BG)
            self.stop_btn.config(state=tk.NORMAL)

    def _on_settings_click(self):
        if self.on_settings:
            self.on_settings()

    def _on_history_click(self):
        if self.on_history:
            self.on_history()

    def _on_reset_click(self):
        if messagebox.askyesno("确认重置", "确定要重置当前会话的统计数据吗？"):
            if self.on_reset:
                self.on_reset()

    def set_on_reset(self, callback: Callable):
        self.on_reset = callback

    def show_hint(self, message: str):
        self.hint_label.config(text=message)

    def enable_settings(self, enabled: bool = True):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.settings_btn.config(state=state)

    def reset_to_initial(self):
        """重置到初始状态"""
        self.monitoring_state = 0
        self._update_button_states()


def create_control_panel(parent) -> ControlPanel:
    return ControlPanel(parent)
