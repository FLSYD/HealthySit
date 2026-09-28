"""
设置对话框组件
提供系统参数配置界面（包含各不良坐姿阈值独立调整）
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Dict, Any, Callable
import logging

logger = logging.getLogger(__name__)

THRESHOLD_CONFIG = {
    'neck_tilt': {
        'label': '头部侧倾阈值',
        'min': 5.0,
        'max': 25.0,
        'default': 15.0,
        'unit': '°',
        'desc': '头部侧倾超过此角度触发警告'
    },
    'shoulder': {
        'label': '肩膀倾斜阈值',
        'min': 5.0,
        'max': 25.0,
        'default': 15.0,
        'unit': '°',
        'desc': '肩膀倾斜超过此角度触发警告'
    },
    'head_forward': {
        'label': '头部前倾阈值',
        'min': 10.0,
        'max': 30.0,
        'default': 20.0,
        'unit': '°',
        'desc': '头部前倾超过此角度触发警告'
    },
    'torso': {
        'label': '躯干倾斜阈值',
        'min': 5.0,
        'max': 25.0,
        'default': 15.0,
        'unit': '°',
        'desc': '躯干倾斜超过此角度触发警告'
    },
}

DEFAULT_SETTINGS = {
    'neck_tilt_threshold': 15.0,
    'shoulder_threshold': 15.0,
    'head_forward_threshold': 20.0,
    'torso_threshold': 15.0,
    'sedentary_minutes': 60,
    'show_skeleton': True,
    'sound_enabled': True,
    'repeat_count': 1,
}


# ============ 自定义美化的复选框 ============
class FancyCheckbutton(tk.Frame):
    """自定义复化框组件，显示 ✓ 而非默认勾选符号"""

    def __init__(self, parent, text: str, variable: tk.BooleanVar,
                 font: tuple = ("Microsoft YaHei", 10),
                 fg: str = "#2C3E50", bg: str = "#FFFFFF",
                 checked_color: str = "#2980B9", **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self.variable = variable
        self.font = font
        self.fg = fg
        self.bg = bg
        self.checked_color = checked_color

        self._box = tk.Frame(self, width=18, height=18, bg="#E0E0E0", bd=0)
        self._box.pack(side=tk.LEFT, padx=(0, 8))
        self._box.pack_propagate(False)

        self._check_lbl = tk.Label(
            self._box, text="✓", font=("Arial", 11, "bold"),
            fg=checked_color, bg="#E0E0E0", anchor=tk.CENTER
        )
        self._check_lbl.pack(expand=True)

        self._text_lbl = tk.Label(
            self, text=text, font=font, fg=fg, bg=bg, anchor=tk.W
        )
        self._text_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 点击事件全部绑定到整个行
        for widget in (self._box, self._check_lbl, self._text_lbl):
            widget.bind("<Button-1>", lambda e: self._do_toggle())
        self.bind("<Button-1>", lambda e: self._do_toggle())

        self._update_display()

    def _do_toggle(self):
        """切换复选框状态"""
        new_val = not self.variable.get()
        self.variable.set(new_val)
        self._update_display()

    def _update_display(self):
        """根据 variable 当前值更新外观"""
        checked = self.variable.get()
        if checked:
            self._box.config(bg=self.checked_color)
            self._check_lbl.config(bg=self.checked_color, fg="#FFFFFF", text="✓")
        else:
            self._box.config(bg="#E0E0E0")
            self._check_lbl.config(bg="#E0E0E0", fg="#E0E0E0", text="")

    def refresh(self):
        """外部调用：重新同步显示状态（用于加载设置时）"""
        self._update_display()


# ============ 自定义美化的滑块行 ============
class ThresholdSlider(tk.Frame):
    """单个阈值滑块行"""

    def __init__(self, parent, key: str, cfg: Dict,
                 pending_vars: Dict, value_labels: Dict,
                 lock_trace_ref: list,
                 font: tuple = ("Microsoft YaHei", 10),
                 label_fg: str = "#2C3E50", value_color: str = "#2980B9",
                 desc_color: str = "#95A5A6", bg: str = "#FFFFFF", **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self.cfg = cfg
        self.key = key
        self.pending_vars = pending_vars
        self.value_labels = value_labels
        self.lock_trace = lock_trace_ref  # list 引用，可从外部修改
        self.font = font
        self.label_fg = label_fg
        self.value_color = value_color
        self.desc_color = desc_color
        self.bg = bg
        self.unit = cfg['unit']

        var = tk.DoubleVar()
        self.pending_vars[key] = var

        # 标签行
        header = tk.Frame(self, bg=bg)
        header.pack(fill=tk.X)

        tk.Label(
            header, text=cfg['label'], font=font, fg=label_fg, bg=bg
        ).pack(side=tk.LEFT)

        # 数值标签
        value_lbl = tk.Label(
            header, text="", font=("Consolas", 10, "bold"),
            fg=value_color, bg="#F0F4F8", padx=8, pady=2
        )
        value_lbl.pack(side=tk.RIGHT)
        self.value_labels[key] = value_lbl

        # 滑块
        slider = ttk.Scale(
            self, from_=cfg['min'], to=cfg['max'],
            orient=tk.HORIZONTAL, variable=var,
            command=lambda v: self._on_slider_move(v)
        )
        slider.pack(fill=tk.X, pady=(4, 0))

        # 拖动时更新标签
        def on_slider_interact(*args):
            if self.lock_trace[0]:
                return
            val = var.get()
            value_lbl.config(text=f"{val:.1f}{self.unit}")

        var.trace_add('write', on_slider_interact)

        # 描述文字
        tk.Label(
            self, text=cfg['desc'], font=("Microsoft YaHei", 8),
            fg=desc_color, bg=bg, anchor=tk.W
        ).pack(anchor=tk.W, pady=(2, 0))

    def _on_slider_move(self, v):
        """滑块拖动时更新数值显示"""
        val = float(v)
        self.value_labels[self.key].config(text=f"{val:.1f}{self.unit}")

    def set_value(self, val: float):
        """外部设置值（用于重置）"""
        self.pending_vars[self.key].set(val)
        self.value_labels[self.key].config(text=f"{val:.1f}{self.unit}")


class IntSlider(tk.Frame):
    """整数型滑块行，支持特殊值的自定义显示"""

    def __init__(self, parent, label: str, variable: tk.IntVar,
                 from_: int, to: int, step: int = 1, unit: str = "",
                 desc: str = "", font: tuple = ("Microsoft YaHei", 10),
                 label_fg: str = "#2C3E50", value_color: str = "#2980B9",
                 desc_color: str = "#95A5A6", bg: str = "#FFFFFF",
                 value_map: dict = None, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self.variable = variable
        self.unit = unit
        self.value_color = value_color
        self.desc_color = desc_color
        self.bg = bg
        self.value_map = value_map or {}

        header = tk.Frame(self, bg=bg)
        header.pack(fill=tk.X)

        tk.Label(header, text=label, font=font, fg=label_fg, bg=bg).pack(side=tk.LEFT)

        value_lbl = tk.Label(
            header, text="", font=("Consolas", 10, "bold"),
            fg=value_color, bg="#F0F4F8", padx=8, pady=2
        )
        value_lbl.pack(side=tk.RIGHT)

        def format_display(val):
            if val in self.value_map:
                return self.value_map[val]
            return f"{val}{unit}"

        def update_lbl(v):
            val = int(float(v))
            value_lbl.config(text=format_display(val))

        def on_interact(*args):
            update_lbl(variable.get())

        variable.trace_add('write', on_interact)
        update_lbl(variable.get())

        slider = ttk.Scale(
            self, from_=from_, to=to, orient=tk.HORIZONTAL,
            variable=variable, command=update_lbl
        )
        slider.pack(fill=tk.X, pady=(4, 0))

        if desc:
            tk.Label(
                self, text=desc, font=("Microsoft YaHei", 8),
                fg=desc_color, bg=bg, anchor=tk.W
            ).pack(anchor=tk.W, pady=(2, 0))


# ============ 主对话框 ============
class SettingsDialog(tk.Toplevel):
    DIALOG_W = 400
    DIALOG_H = 640
    CONTENT_H = 500  # 可滚动内容区高度

    def __init__(self, parent, current_settings: Dict[str, Any] = None,
                 on_apply: Optional[Callable[[Dict], None]] = None):
        super().__init__(parent)

        self.current_settings = current_settings or DEFAULT_SETTINGS.copy()
        self.default_settings = DEFAULT_SETTINGS.copy()
        self.on_apply_callback = on_apply
        self.result_settings = None

        self._pending_vars: Dict[str, tk.DoubleVar] = {}
        self._value_labels: Dict[str, tk.Label] = {}
        self._lock_trace = [False]
        self._slider_widgets: Dict[str, ThresholdSlider] = {}
        self._sedentary_var = tk.IntVar()
        self._repeat_count_var = tk.IntVar()
        self._sound_var = tk.BooleanVar()
        self._show_skeleton_var = tk.BooleanVar()
        self._sound_cb = None
        self._skeleton_cb = None

        self.title("系统设置")
        self.geometry(f"{self.DIALOG_W}x{self.DIALOG_H}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # 居中
        self.update_idletasks()
        pw = parent.winfo_x() + parent.winfo_width() // 2
        ph = parent.winfo_y() + parent.winfo_height() // 2
        self.geometry(f"+{pw - self.DIALOG_W // 2}+{ph - self.DIALOG_H // 2}")

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        # 整个窗口背景
        self.config(bg="#F5F7FA")

        # 标题栏
        title_bar = tk.Frame(self, bg="#2980B9", height=50)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        tk.Label(
            title_bar, text="系统设置",
            font=("Microsoft YaHei", 14, "bold"),
            fg="#FFFFFF", bg="#2980B9"
        ).pack(side=tk.LEFT, padx=16, pady=12)

        # 右侧留白（让关闭按钮有空间）
        tk.Frame(title_bar, width=30, bg="#2980B9").pack(side=tk.RIGHT)

        # 可滚动内容区（Canvas + Scrollbar）
        outer = tk.Frame(self, bg="#F5F7FA")
        outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 0))

        canvas = tk.Canvas(
            outer, bg="#F5F7FA", highlightthickness=0,
            width=self.DIALOG_W - 32, height=self.CONTENT_H
        )
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._content = tk.Frame(canvas, bg="#F5F7FA")
        canvas.create_window((0, 0), window=self._content, anchor=tk.NW, width=self.DIALOG_W - 32)

        def on_scroll(*args):
            canvas.yview(*args)

        def update_scrollregion(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 让内容帧宽度跟随 canvas 实际宽度
            canvas.itemconfig(canvas.find_all()[0], width=canvas.winfo_width())

        self._content.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", update_scrollregion)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(
            int(-1 * (e.delta / 120)), "units"
        ))

        # -------- 内容区 --------

        # 不良坐姿检测阈值卡片
        card1 = self._add_card("不良坐姿检测阈值")
        for key, cfg in THRESHOLD_CONFIG.items():
            sw = ThresholdSlider(
                card1, key, cfg,
                self._pending_vars, self._value_labels, self._lock_trace,
                bg="#FFFFFF"
            )
            sw.pack(fill=tk.X, padx=12, pady=(0, 6))
            self._slider_widgets[key] = sw

        # 提醒设置卡片
        self._add_spacer(8)
        card2 = self._add_card("提醒设置")
        IntSlider(
            card2, label="久坐提醒间隔",
            variable=self._sedentary_var,
            from_=0, to=120, step=1, unit=" 分钟",
            desc="设为0时不提醒，达到间隔倍数时触发提醒",
            bg="#FFFFFF"
        ).pack(fill=tk.X, padx=12, pady=(0, 6))

        IntSlider(
            card2, label="久坐提醒次数",
            variable=self._repeat_count_var,
            from_=0, to=11, step=1, unit=" 次",
            desc="设为0时不提醒，设为不限制时无限次提醒",
            bg="#FFFFFF",
            value_map={0: "不提醒", 11: "不限制"}
        ).pack(fill=tk.X, padx=12, pady=(0, 6))

        self._sound_cb = FancyCheckbutton(
            card2, text="启用声音提醒",
            variable=self._sound_var, bg="#FFFFFF"
        )
        self._sound_cb.pack(anchor=tk.W, padx=12, pady=4)

        # 显示设置卡片
        self._add_spacer(8)
        card3 = self._add_card("显示设置")
        self._skeleton_cb = FancyCheckbutton(
            card3, text="显示骨骼点",
            variable=self._show_skeleton_var, bg="#FFFFFF"
        )
        self._skeleton_cb.pack(anchor=tk.W, padx=12, pady=4)

        # 底部固定按钮栏
        self._add_spacer(12)
        self._setup_buttons()

    def _add_card(self, title: str):
        """添加卡片，返回内部 Frame"""
        card = tk.Frame(self._content, bg="#FFFFFF")
        card.pack(fill=tk.X)

        title_lbl = tk.Label(
            card, text=title,
            font=("Microsoft YaHei", 10, "bold"),
            fg="#2980B9", bg="#FFFFFF", anchor=tk.W
        )
        title_lbl.pack(anchor=tk.W, padx=12, pady=(10, 2))

        sep = tk.Frame(card, bg="#E8ECF0", height=1)
        sep.pack(fill=tk.X, padx=12, pady=(0, 8))

        inner = tk.Frame(card, bg="#FFFFFF")
        inner.pack(fill=tk.X, padx=0, pady=(0, 8))
        return inner

    def _add_spacer(self, h: int):
        tk.Frame(self._content, height=h, bg="#F5F7FA").pack(fill=tk.X)

    def _setup_buttons(self):
        btn_bar = tk.Frame(self, bg="#FFFFFF", height=56)
        btn_bar.pack(fill=tk.X, padx=16, pady=(8, 12))
        btn_bar.pack_propagate(False)

        # 阴影效果（用 Frame 模拟）
        shadow = tk.Frame(btn_bar, bg="#E0E0E0")
        shadow.place(x=0, y=0, relwidth=1, relheight=1, height=-1)

        btn_frame = tk.Frame(btn_bar, bg="#FFFFFF")
        btn_frame.pack(fill=tk.X, padx=4, pady=4)

        # 重置默认
        reset_btn = tk.Button(
            btn_frame, text="重置默认",
            font=("Microsoft YaHei", 10),
            fg="#7F8C8D", bg="#ECF0F1",
            activebackground="#D5DBDB", activeforeground="#7F8C8D",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._on_reset,
            width=9, height=2
        )
        reset_btn.pack(side=tk.LEFT, padx=(0, 6))

        right_frame = tk.Frame(btn_frame, bg="#FFFFFF")
        right_frame.pack(side=tk.RIGHT)

        # 取消
        cancel_btn = tk.Button(
            right_frame, text="取消",
            font=("Microsoft YaHei", 10),
            fg="#FFFFFF", bg="#95A5A6",
            activebackground="#7F8C8D", activeforeground="#FFFFFF",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._on_cancel,
            width=7, height=2
        )
        cancel_btn.pack(side=tk.LEFT, padx=(6, 0))

        # 应用
        apply_btn = tk.Button(
            right_frame, text="应用",
            font=("Microsoft YaHei", 10, "bold"),
            fg="#FFFFFF", bg="#2980B9",
            activebackground="#1A5276", activeforeground="#FFFFFF",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._on_apply,
            width=7, height=2
        )
        apply_btn.pack(side=tk.LEFT, padx=(6, 0))

    def _load_settings(self):
        for key, cfg in THRESHOLD_CONFIG.items():
            sk = f"{key}_threshold"
            val = self.current_settings.get(sk, cfg['default'])
            self._slider_widgets[key].set_value(val)

        self._sedentary_var.set(self.current_settings.get('sedentary_minutes', 60))
        self._repeat_count_var.set(self.current_settings.get('repeat_count', 1))
        self._show_skeleton_var.set(self.current_settings.get('show_skeleton', True))
        self._sound_var.set(self.current_settings.get('sound_enabled', True))

        # 刷新复选框显示
        if self._sound_cb:
            self._sound_cb.refresh()
        if self._skeleton_cb:
            self._skeleton_cb.refresh()

    def _collect_settings(self) -> Dict[str, Any]:
        return {
            'neck_tilt_threshold': self._pending_vars['neck_tilt'].get(),
            'head_forward_threshold': self._pending_vars['head_forward'].get(),
            'torso_threshold': self._pending_vars['torso'].get(),
            'shoulder_threshold': self._pending_vars['shoulder'].get(),
            'sedentary_minutes': self._sedentary_var.get(),
            'repeat_count': self._repeat_count_var.get(),
            'show_skeleton': self._show_skeleton_var.get(),
            'sound_enabled': self._sound_var.get(),
        }

    def _on_cancel(self):
        self.result_settings = None
        self.destroy()

    def _on_reset(self):
        self._lock_trace[0] = True
        try:
            for key, cfg in THRESHOLD_CONFIG.items():
                self._slider_widgets[key].set_value(cfg['default'])

            self._sedentary_var.set(self.default_settings['sedentary_minutes'])
            self._repeat_count_var.set(self.default_settings['repeat_count'])
            self._show_skeleton_var.set(self.default_settings['show_skeleton'])
            self._sound_var.set(self.default_settings['sound_enabled'])

            # 刷新复选框显示
            if self._sound_cb:
                self._sound_cb.refresh()
            if self._skeleton_cb:
                self._skeleton_cb.refresh()
        finally:
            self._lock_trace[0] = False

    def _on_apply(self):
        self.result_settings = self._collect_settings()
        if self.on_apply_callback:
            self.on_apply_callback(self.result_settings)
        logger.info("设置已应用: %s", self.result_settings)

    def show(self) -> Optional[Dict[str, Any]]:
        self.wait_window()
        return self.result_settings


def create_settings_dialog(parent, settings: Dict[str, Any] = None,
                          on_apply: Optional[Callable[[Dict], None]] = None) -> SettingsDialog:
    return SettingsDialog(parent, settings, on_apply)
