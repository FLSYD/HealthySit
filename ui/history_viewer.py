"""
健康历史查看器组件
直观展示坐姿数据与历史会话，支持一键导出
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
import logging

import matplotlib
matplotlib.use('Agg')
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import MaxNLocator
import matplotlib.font_manager as fm

# 配置中文字体（确保 matplotlib 文本能正确渲染中文）
_fonts = [f.name for f in fm.fontManager.ttflist]
_cn_fonts = [f for f in _fonts if any(c in f for c in ('YaHei', 'Hei', 'Ming', 'Song', 'Fang', 'Kai', 'SimSun', 'Microsoft'))]
if _cn_fonts:
    plt.rcParams['font.sans-serif'] = [_cn_fonts[0]] + plt.rcParams['font.sans-serif']
else:
    # 未检测到中文字体时，强制指定微软雅黑
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei'] + plt.rcParams['font.sans-serif']
plt.rcParams['axes.unicode_minus'] = False
_CN_FONT = _cn_fonts[0] if _cn_fonts else 'Microsoft YaHei'

logger = logging.getLogger(__name__)

COLOR_BG = "#F5F7FA"
COLOR_CARD = "#FFFFFF"
COLOR_TEXT = "#2C3E50"
COLOR_TEXT_SEC = "#7F8C8D"
COLOR_ACCENT = "#2980B9"
COLOR_SUCCESS = "#27AE60"
COLOR_WARNING = "#E67E22"
COLOR_DANGER = "#E74C3C"
COLOR_INFO = "#3498DB"

LEVEL_COLORS = {
    'excellent': '#27AE60',
    'good': '#2ECC71',
    'fair': '#E67E22',
    'poor': '#E74C3C',
    'bad': '#C0392B',
}

LEVEL_LABELS_CN = {
    'excellent': '优秀',
    'good': '良好',
    'fair': '一般',
    'poor': '较差',
    'bad': '差',
}


class HistoryViewer(tk.Toplevel):
    """健康历史查看器"""

    WIN_W = 1000
    WIN_H = 660

    def __init__(self, parent, data_manager, current_settings: Dict[str, Any] = None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_settings = current_settings or {}
        self._sessions_cache: List[Dict] = []
        self._selected_idx = -1
        self._card_widgets: List = []
        self._poll_after_id = None
        self._scroll_after_id = None

        self.title("健康历史")
        self.geometry(f"{self.WIN_W}x{self.WIN_H}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        try:
            px = parent.winfo_x() + parent.winfo_width() // 2
            py = parent.winfo_y() + parent.winfo_height() // 2
            self.geometry(f"+{px - self.WIN_W // 2}+{py - self.WIN_H // 2}")
        except:
            pass

        self._setup_ui()
        self._load_data()

        # 启动数据轮询：有新会话时自动刷新
        self._last_session_count = len(self._sessions_cache)
        self._poll_data()

        logger.info("健康历史查看器已打开")

    def _setup_ui(self):
        """构建 UI"""
        self.configure(bg=COLOR_BG)

        # ---- 顶部标题栏 ----
        header = tk.Frame(self, bg=COLOR_ACCENT, height=52)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="健康历史",
            font=("Microsoft YaHei", 15, "bold"),
            fg="#FFFFFF", bg=COLOR_ACCENT
        ).pack(side=tk.LEFT, padx=20, pady=14)

        tk.Label(
            header,
            text="查看坐姿历史数据与统计报告",
            font=("Microsoft YaHei", 9),
            fg="#AACCEE", bg=COLOR_ACCENT
        ).pack(side=tk.LEFT, pady=16)

        # ---- 主内容区 ----
        content = tk.Frame(self, bg=COLOR_BG)
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # 左列
        left = tk.Frame(content, bg=COLOR_BG, width=540)
        left.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 12))
        left.pack_propagate(False)

        self._build_posture_summary(left)
        self._build_trend(left)

        # 右列
        right = tk.Frame(content, bg=COLOR_BG)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self._build_session_list(right)

        # ---- 底部操作栏 ----
        self._build_action_bar()

        # ---- 详情弹窗（独立窗口，首次点击会话时显示） ----
        self._detail_win: Optional[tk.Toplevel] = None

    # ================================================================
    #  坐姿概况
    # ================================================================

    def _build_posture_summary(self, parent):
        """坐姿概况——四个白色统计卡片"""
        card = tk.Frame(parent, bg=COLOR_CARD, relief=tk.FLAT, bd=0)
        card.pack(fill=tk.X, pady=10)

        tk.Label(
            card, text="坐姿概况",
            font=("Microsoft YaHei", 12, "bold"),
            fg=COLOR_TEXT, bg=COLOR_CARD, anchor=tk.W
        ).pack(anchor=tk.W, padx=16, pady=12)

        self._summary_items: Dict[str, tk.Label] = {}

        items = [
            ('score', '坐姿评分', '分', COLOR_SUCCESS),
            ('time', '坐姿时长', '', COLOR_ACCENT),
            ('violations', '违规次数', '次', COLOR_WARNING),
            ('sessions', '总会话', '次', COLOR_INFO),
        ]

        # 外层行容器
        row = tk.Frame(card, bg=COLOR_CARD)
        row.pack(fill=tk.X, padx=16, pady=14)

        for key, label, unit, color in items:
            cell = tk.Frame(row, bg="#F7F9FB", relief=tk.GROOVE, bd=1)
            cell.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=4)

            # 顶部色条
            bar = tk.Frame(cell, bg=color, height=3)
            bar.pack(fill=tk.X)
            bar.pack_propagate(False)

            tk.Label(
                cell, text=label,
                font=("Microsoft YaHei", 10),
                fg=COLOR_TEXT_SEC, bg="#F7F9FB"
            ).pack(fill=tk.X, pady=10)

            val_lbl = tk.Label(
                cell, text="--",
                font=("Microsoft YaHei", 20, "bold"),
                fg=color, bg="#F7F9FB"
            )
            val_lbl.pack(pady=2)
            self._summary_items[key] = val_lbl

            tk.Label(
                cell, text=unit,
                font=("Microsoft YaHei", 9),
                fg=COLOR_TEXT_SEC, bg="#F7F9FB"
            ).pack(pady=10)

    # ================================================================
    #  坐姿趋势
    # ================================================================

    def _build_trend(self, parent):
        """坐姿趋势——最近10次会话折线图"""
        card = tk.Frame(parent, bg=COLOR_CARD, relief=tk.FLAT, bd=0)
        card.pack(fill=tk.BOTH, expand=True, pady=0)

        tk.Label(
            card, text="坐姿趋势",
            font=("Microsoft YaHei", 12, "bold"),
            fg=COLOR_TEXT, bg=COLOR_CARD, anchor=tk.W
        ).pack(anchor=tk.W, padx=16, pady=2)

        tk.Label(
            card, text="最近 10 次会话的坐姿评分趋势",
            font=("Microsoft YaHei", 9),
            fg=COLOR_TEXT_SEC, bg=COLOR_CARD, anchor=tk.W
        ).pack(anchor=tk.W, padx=16, pady=4)

        self._trend_empty_hint = tk.Label(
            card,
            text="暂无会话数据，开始监测后即可查看趋势",
            font=("Microsoft YaHei", 10),
            fg="#8BA4BC",
            bg=COLOR_CARD,
            anchor=tk.W,
            justify=tk.LEFT
        )
        self._trend_empty_hint.pack(anchor=tk.W, padx=16, pady=(0, 4))

        # matplotlib Figure 画布
        fig = Figure(figsize=(6.6, 3.6), dpi=100)
        fig.patch.set_facecolor(COLOR_CARD)
        fig.subplots_adjust(left=0.02, right=0.95, top=0.93, bottom=0.20)
        self._ax_trend = fig.add_subplot(111)
        self._ax_trend.set_facecolor("#EEF5FB")
        self._ax_trend.tick_params(axis='x', labelsize=10, colors=COLOR_TEXT_SEC)
        self._ax_trend.tick_params(axis='y', length=0, labelcolor=COLOR_CARD)
        self._ax_trend.spines['top'].set_visible(False)
        self._ax_trend.spines['right'].set_visible(False)
        self._ax_trend.spines['left'].set_visible(False)
        self._ax_trend.spines['bottom'].set_color('#D0D7DE')
        self._ax_trend.grid(axis='y', color='#E0EAF4', linewidth=0.8, linestyle='--')
        self._ax_trend.set_yticks([0, 25, 50, 75, 100])

        self._canvas_trend = FigureCanvasTkAgg(fig, master=card)
        self._canvas_trend.draw()
        self._canvas_trend.get_tk_widget().pack(fill=tk.X, padx=10, pady=0)

    def _load_trend(self):
        """加载并绘制坐姿趋势折线图"""
        try:
            trend = self.data_manager.get_recent_trend(count=10)
            self._update_trend_chart(trend)
        except Exception as e:
            logger.error(f"加载坐姿趋势失败: {e}")

    def _update_trend_chart(self, trend: List[Dict]):
        ax = self._ax_trend
        ax.clear()

        # 极简背景：左上角微渐变感
        ax.set_facecolor("#EEF5FB")
        ax.tick_params(axis='x', labelsize=10, colors=COLOR_TEXT_SEC)
        ax.tick_params(axis='y', length=0, labelcolor=COLOR_CARD)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_color('#C5D5E8')
        ax.grid(axis='y', color='#DAE8F5', linewidth=0.8, linestyle='--')
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_ylim(-5, 115)

        # 固定 x 轴，始终显示 10 格
        ax.set_xlim(-0.4, 9.4)
        ax.set_xticks(range(10))
        ax.set_xticklabels([str(i) for i in range(1, 11)], fontsize=10, color=COLOR_TEXT_SEC)

        if not trend:
            self._trend_empty_hint.pack(anchor=tk.W, padx=16, pady=(0, 4))
            ax.set_facecolor("#EEF5FB")
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.grid(False)
            self._canvas_trend.draw()
            return

        self._trend_empty_hint.pack_forget()

        scores = [d.get('posture_score') or 0 for d in trend]
        n = len(trend)
        x_pos = list(range(n))

        # 柔和渐变面积填充（到基线 0）
        ax.fill_between(x_pos, scores, alpha=0.22, color=COLOR_ACCENT, zorder=2)

        # 平滑曲线
        if n >= 4:
            try:
                from scipy.interpolate import make_interp_spline
                x_smooth = np.linspace(0, n - 1, 300)
                spl = make_interp_spline(x_pos, scores, k=min(3, n - 1))
                y_smooth = spl(x_smooth)
                ax.plot(x_smooth, y_smooth, color=COLOR_ACCENT, linewidth=3.5,
                        zorder=3, solid_capstyle='round', solid_joinstyle='round', alpha=0.90)
            except Exception:
                ax.plot(x_pos, scores, color=COLOR_ACCENT, linewidth=3.0,
                        zorder=3, solid_capstyle='round')
        else:
            ax.plot(x_pos, scores, color=COLOR_ACCENT, linewidth=3.0,
                    zorder=3, solid_capstyle='round')

        # 数据点：外发光白圈 + 内实心圆（按评分着色）
        point_colors = [
            COLOR_SUCCESS if s >= 80 else COLOR_WARNING if s >= 60 else COLOR_DANGER
            for s in scores
        ]
        for xi, yi, ci in zip(x_pos, scores, point_colors):
            # 外发光环（半透明大圆）
            ax.scatter(xi, yi, c=ci, s=200, zorder=4,
                       edgecolors='none', marker='o', alpha=0.15)
            # 主圆白底描边
            ax.scatter(xi, yi, c=ci, s=110, zorder=6,
                       edgecolors='#FFFFFF', linewidths=2.5, marker='o')
            # 中心实心点
            ax.scatter(xi, yi, c=ci, s=45, zorder=7,
                       edgecolors='none', marker='o')

        # 评分文字标签（白底无边框，现代简约风格）
        for xi, yi in zip(x_pos, scores):
            ax.annotate(f"{yi:.0f}", xy=(xi, yi),
                        xytext=(0, 14),
                        textcoords='offset points',
                        ha='center', va='bottom',
                        fontsize=10, color='#2C3E50', fontweight='bold',
                        zorder=8)

        self._canvas_trend.draw()

    def refresh_chart(self):
        """由外部调用：当会话数据更新时同步刷新折线图"""
        self._load_trend()

    # ================================================================
    #  历史会话
    # ================================================================

    def _build_session_list(self, parent):
        """历史会话列表——卡片式布局"""
        card = tk.Frame(parent, bg=COLOR_CARD, relief=tk.FLAT, bd=0)
        card.pack(fill=tk.BOTH, expand=True)

        title_row = tk.Frame(card, bg=COLOR_CARD)
        title_row.pack(fill=tk.X, padx=16, pady=4)

        tk.Label(
            title_row, text="历史会话",
            font=("Microsoft YaHei", 12, "bold"),
            fg=COLOR_TEXT, bg=COLOR_CARD, anchor=tk.W
        ).pack(side=tk.LEFT)

        self._session_count_lbl = tk.Label(
            title_row, text="",
            font=("Microsoft YaHei", 9),
            fg=COLOR_TEXT_SEC, bg=COLOR_CARD, anchor=tk.E
        )
        self._session_count_lbl.pack(side=tk.RIGHT)

        # ---- 可滚动画布 ----
        list_row = tk.Frame(card, bg=COLOR_CARD)
        list_row.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        self._session_canvas = tk.Canvas(
            list_row, bg=COLOR_CARD,
            highlightthickness=0, bd=0,
        )
        self._session_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._session_scrollbar = ttk.Scrollbar(
            list_row, orient=tk.VERTICAL, command=self._session_canvas.yview
        )
        self._session_canvas.configure(yscrollcommand=self._session_scrollbar.set)
        # 滚动条始终隐藏，依赖鼠标滚轮滚动
        self._session_scrollbar.pack_forget()

        self._session_inner = tk.Frame(self._session_canvas, bg=COLOR_CARD)
        self._session_window = self._session_canvas.create_window(
            (0, 0), window=self._session_inner, anchor=tk.NW
        )

        self._session_inner.bind(
            "<Configure>",
            lambda e: self._session_canvas.configure(scrollregion=self._session_canvas.bbox(tk.ALL))
        )
        self._session_canvas.bind("<Configure>", self._on_canvas_resize)
        self.bind(
            "<MouseWheel>",
            lambda e: self._session_canvas.yview_scroll(int(-1 * (e.delta / 120)), tk.UNITS)
        )

    def _on_canvas_resize(self, event):
        self._session_canvas.itemconfig(self._session_window, width=event.width)

    def _on_card_click(self, idx: int):
        """选中卡片（仅更新颜色，不重建 DOM，保持滚动位置不变）"""
        old_idx = getattr(self, '_selected_idx', -1)
        self._selected_idx = idx

        # 只更新颜色，card/inner/top_row/bottom_row 都可能需要更新
        for i, card in enumerate(self._card_widgets):
            session = self._sessions_cache[i]
            level = session.get('posture_level', 'fair')
            level_color = LEVEL_COLORS.get(level, COLOR_TEXT_SEC)
            is_selected = (i == idx)
            card_bg = "#EEF4FB" if is_selected else "#F8FAFB"
            border_color = level_color if is_selected else "#E0E8F0"
            card.configure(bg=border_color)
            inner = card.winfo_children()[0] if card.winfo_children() else None
            if inner:
                inner.configure(bg=card_bg)
                for child in inner.winfo_children():
                    child.configure(bg=card_bg)

        # 展示详情
        if 0 <= idx < len(self._sessions_cache):
            self._show_session_detail(self._sessions_cache[idx])

    def _render_session_cards(self):
        """渲染会话卡片列表"""
        # 保存当前滚动位置，重绘后恢复
        saved_scroll = self._session_canvas.yview() if hasattr(self, '_session_scroll_y') else (0, 1)

        for w in self._session_inner.winfo_children():
            w.destroy()
        self._card_widgets = []
        self._selected_idx = getattr(self, '_selected_idx', -1)

        sessions = self._sessions_cache
        if not sessions:
            tk.Label(
                self._session_inner, text="暂无会话记录",
                font=("Microsoft YaHei", 11), fg=COLOR_TEXT_SEC, bg=COLOR_CARD,
                anchor=tk.W, padx=8, pady=14
            ).pack(fill=tk.X, padx=6, pady=6)
        else:
            for i, s in enumerate(sessions):
                is_selected = (i == self._selected_idx)
                self._build_session_card(self._session_inner, s, i, is_selected)

        # 重绘完成后恢复滚动位置（先更新 scrollregion，再恢复位置）
        def _restore_scroll():
            self._session_canvas.configure(
                scrollregion=self._session_canvas.bbox(tk.ALL)
            )
            self._session_canvas.yview_moveto(saved_scroll[0])

        if self._scroll_after_id is not None:
            self.after_cancel(self._scroll_after_id)
        self._scroll_after_id = self.after_idle(_restore_scroll)

    def _build_session_card(self, parent, session: Dict, idx: int, is_selected: bool):
        """构建单个会话卡片"""
        level = session.get('posture_level', 'fair')
        score = session.get('posture_score', 0) or 0
        level_text = LEVEL_LABELS_CN.get(level, level)
        level_color = LEVEL_COLORS.get(level, COLOR_TEXT_SEC)

        # 卡片背景色：选中时用浅色高亮
        card_bg = "#EEF4FB" if is_selected else "#F8FAFB"
        border_color = level_color if is_selected else "#E0E8F0"

        card = tk.Frame(parent, bg=border_color, relief=tk.FLAT, bd=0)
        card.pack(fill=tk.X, padx=4, pady=5)

        inner = tk.Frame(card, bg=card_bg, relief=tk.FLAT, bd=0)
        inner.pack(fill=tk.X, padx=2, pady=2)

        # 第一行：日期时间 + 评分标签
        top_row = tk.Frame(inner, bg=card_bg)
        top_row.pack(fill=tk.X, padx=14, pady=4)

        start = session.get('start_time', '')
        date_str = start[:19].replace('T', ' ') if start else 'N/A'

        # 日期时间
        tk.Label(
            top_row, text=date_str,
            font=("Microsoft YaHei", 11, "bold"),
            fg=COLOR_TEXT, bg=card_bg, anchor=tk.W
        ).pack(side=tk.LEFT)

        # 评分 + 等级
        score_lbl = tk.Label(
            top_row, text=f"坐姿评分 {level_text} {score:.0f}分",
            font=("Microsoft YaHei", 11),
            fg="#FFFFFF", bg=level_color, anchor=tk.W
        )
        score_lbl.pack(side=tk.RIGHT)

        # 第二行：时长 / 违规
        bottom_row = tk.Frame(inner, bg=card_bg)
        bottom_row.pack(fill=tk.X, padx=14, pady=10)

        total_dur = session.get('total_duration', 0) or 0
        viol = session.get('total_violations', 0) or 0

        dur_text = self._fmt_dur(total_dur)
        tk.Label(
            bottom_row, text=f"时长 {dur_text}  违规 {viol}次",
            font=("Microsoft YaHei", 10),
            fg=COLOR_TEXT_SEC, bg=card_bg, anchor=tk.W
        ).pack(side=tk.LEFT)

        # 点击提示
        tk.Label(
            bottom_row, text="点击查看详情 ›",
            font=("Microsoft YaHei", 10),
            fg=level_color if is_selected else COLOR_TEXT_SEC, bg=card_bg, anchor=tk.E
        ).pack(side=tk.RIGHT)

        # 点击事件：给 card 内的所有 widget（Frame + Label）绑定点击，无死角
        def _on_click(event, i=idx):
            self._on_card_click(i)
        for widget in card.winfo_children() + list(inner.winfo_children()):
            widget.bind("<Button-1>", _on_click)
            for child in widget.winfo_children():
                child.bind("<Button-1>", _on_click)

        self._card_widgets.append(card)

    # ================================================================
    #  底部操作栏
    # ================================================================

    def _build_action_bar(self):
        bar = tk.Frame(self, bg=COLOR_CARD, height=54)
        bar.pack(fill=tk.X, side=tk.BOTTOM, padx=16, pady=10)
        bar.pack_propagate(False)

        btn_frame = tk.Frame(bar, bg=COLOR_CARD)
        btn_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=6)

        export_all_btn = tk.Button(
            btn_frame, text="导出全部会话",
            font=("Microsoft YaHei", 10, "bold"),
            fg="#FFFFFF", bg=COLOR_ACCENT,
            activebackground=self._darken(COLOR_ACCENT), activeforeground="#FFFFFF",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._do_export_all_sessions,
            padx=16, pady=7
        )
        export_all_btn.pack(side=tk.LEFT)

        export_daily_btn = tk.Button(
            btn_frame, text="导出每日统计",
            font=("Microsoft YaHei", 10, "bold"),
            fg="#FFFFFF", bg=COLOR_SUCCESS,
            activebackground=self._darken(COLOR_SUCCESS), activeforeground="#FFFFFF",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._do_export_daily_stats,
            padx=16, pady=7
        )
        export_daily_btn.pack(side=tk.LEFT, padx=(10, 0))

        export_violations_btn = tk.Button(
            btn_frame, text="导出违规日志",
            font=("Microsoft YaHei", 10, "bold"),
            fg="#FFFFFF", bg=COLOR_WARNING,
            activebackground=self._darken(COLOR_WARNING), activeforeground="#FFFFFF",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._do_export_violations,
            padx=16, pady=7
        )
        export_violations_btn.pack(side=tk.LEFT, padx=(10, 0))

        clear_btn = tk.Button(
            btn_frame, text="清除历史记录",
            font=("Microsoft YaHei", 10, "bold"),
            fg="#FFFFFF", bg=COLOR_DANGER,
            activebackground=self._darken(COLOR_DANGER), activeforeground="#FFFFFF",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._do_clear_all_sessions,
            padx=16, pady=7
        )
        clear_btn.pack(side=tk.RIGHT)

    # ================================================================
    #  数据加载
    # ================================================================

    def _load_data(self):
        try:
            self._load_summary()
            self._load_trend()
            self._load_sessions()
        except Exception as e:
            logger.error(f"加载历史数据失败: {e}", exc_info=True)

    def _load_summary(self):
        """加载坐姿概况：所有会话的汇总"""
        try:
            stats = self.data_manager.get_all_stats()
            total_sess = stats.get('total_sessions', 0)

            if total_sess == 0:
                for key in self._summary_items:
                    self._summary_items[key].config(text="--")
            else:
                score = stats.get('avg_score', 100.0)
                self._summary_items['score'].config(text=f"{score:.0f}")

                total_time = stats.get('total_time', 0)
                self._summary_items['time'].config(text=self._fmt_dur(total_time))

                viol = stats.get('total_violations', 0)
                self._summary_items['violations'].config(text=str(viol))

                self._summary_items['sessions'].config(text=str(total_sess))

        except Exception as e:
            logger.error(f"加载坐姿概况失败: {e}")
            for key in self._summary_items:
                self._summary_items[key].config(text="--")

    def _load_trend(self):
        """加载并绘制坐姿趋势折线图"""
        try:
            trend = self.data_manager.get_recent_trend(count=10)
            self._update_trend_chart(trend)
        except Exception as e:
            logger.error(f"加载坐姿趋势失败: {e}")

    def _load_sessions(self):
        """加载历史会话列表（status=completed，按 start_time DESC）"""
        try:
            sessions = self.data_manager.get_session_history(limit=100)
            self._sessions_cache = sessions
            self._selected_idx = -1

            self._session_count_lbl.config(text=f"共 {len(sessions)} 条记录")

            # 渲染卡片
            self._card_widgets = []
            self._render_session_cards()

        except Exception as e:
            logger.error(f"加载会话列表失败: {e}", exc_info=True)
            self._session_count_lbl.config(text="加载失败")

    def _poll_data(self):
        """每 2 秒轮询数据库，有变化时同步刷新会话列表和折线图"""
        try:
            sessions = self.data_manager.get_session_history(limit=100)
            if sessions != self._sessions_cache:
                self._last_session_count = len(sessions)
                self._sessions_cache = sessions
                self._selected_idx = -1
                self._session_count_lbl.config(text=f"共 {len(sessions)} 条记录")
                self._card_widgets = []
                self._render_session_cards()
                self._load_summary()
                self._load_trend()
        except Exception:
            pass
        finally:
            # 窗口存在时才继续轮询
            if self.winfo_exists():
                self._poll_after_id = self.after(2000, self._poll_data)

    def destroy(self):
        """关闭历史窗口时取消轮询，避免销毁后回调访问 Tk 控件。"""
        if self._poll_after_id is not None:
            self.after_cancel(self._poll_after_id)
            self._poll_after_id = None
        if self._scroll_after_id is not None:
            self.after_cancel(self._scroll_after_id)
            self._scroll_after_id = None
        super().destroy()

    # ================================================================
    #  事件处理
    # ================================================================

    def _show_session_detail(self, session: Dict):
        """展示会话详细数据（弹出独立窗口）"""
        if self._detail_win is not None:
            try:
                self._detail_win.destroy()
            except Exception:
                pass

        level = session.get('posture_level', 'fair')
        score = session.get('posture_score', 0) or 0
        level_text = LEVEL_LABELS_CN.get(level, level)
        level_color = LEVEL_COLORS.get(level, COLOR_TEXT_SEC)

        total_dur = session.get('total_duration', 0) or 0
        viol = session.get('total_violations', 0) or 0
        normal_dur = session.get('normal_duration', 0) or 0
        viol_dur = session.get('violation_duration', 0) or 0

        start = session.get('start_time', '')
        end = session.get('end_time', '')
        start_str = start[:19].replace('T', ' ') if start else 'N/A'
        end_str = end[:19].replace('T', ' ') if end else '进行中'
        session_id = session.get('id', 0)

        win = tk.Toplevel(self)
        win.title(f"会话详情  {start_str}")
        win.configure(bg=COLOR_BG)
        win.resizable(False, False)
        win.transient(self)
        self._detail_win = win
        self._detail_session = session

        win.update_idletasks()
        w, h = 540, 540
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        px = (sw - w) // 2
        py = (sh - h) // 2
        win.geometry(f"{w}x{h}+{px}+{py}")

        def _on_close():
            self._detail_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        # ===== 内容区域（弹性填满） =====
        content = tk.Frame(win, bg=COLOR_BG)
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 0))

        # ===== 顶部标题栏 =====
        header = tk.Frame(content, bg=level_color)
        header.pack(fill=tk.X)

        header_inner = tk.Frame(header, bg=level_color)
        header_inner.pack(fill=tk.X, padx=20, pady=12)

        tk.Label(
            header_inner, text="会话详情",
            font=("Microsoft YaHei", 13, "bold"),
            fg="#FFFFFF", bg=level_color
        ).pack(anchor=tk.W)

        tk.Label(
            header_inner, text=start_str,
            font=("Microsoft YaHei", 9),
            fg="#D0D0D0", bg=level_color
        ).pack(anchor=tk.W, pady=2)

        # ===== 主信息卡片 =====
        info_card = tk.Frame(content, bg=COLOR_CARD)
        info_card.pack(fill=tk.X, pady=(12, 6))

        # 左侧：评分大字
        score_left = tk.Frame(info_card, bg=COLOR_CARD)
        score_left.pack(side=tk.LEFT, padx=16, pady=16, anchor=tk.W)

        tk.Label(
            score_left, text="综合评分",
            font=("Microsoft YaHei", 10),
            fg=COLOR_TEXT_SEC, bg=COLOR_CARD
        ).pack(anchor=tk.W)

        score_val_lbl = tk.Label(
            score_left, text=f"{score:.0f}",
            font=("Microsoft YaHei", 52, "bold"),
            fg=level_color, bg=COLOR_CARD
        )
        score_val_lbl.pack(anchor=tk.W, pady=2)

        grade_lbl = tk.Label(
            score_left,
            text=f"  {level_text}  ",
            font=("Microsoft YaHei", 11, "bold"),
            fg="#FFFFFF", bg=level_color
        )
        grade_lbl.pack(anchor=tk.W, pady=4)

        # 右侧：四条统计数据
        stats_right = tk.Frame(info_card, bg="#F5F7FA", relief=tk.GROOVE, bd=1)
        stats_right.pack(side=tk.RIGHT, padx=16, pady=12, anchor=tk.E)

        for lbl_txt, val_txt, color in [
            ("总时长", self._fmt_dur(total_dur), COLOR_TEXT),
            ("正常时长", self._fmt_dur(normal_dur), COLOR_SUCCESS),
            ("违规时长", self._fmt_dur(viol_dur), COLOR_DANGER),
            ("违规次数", f"{viol} 次", COLOR_DANGER),
        ]:
            row = tk.Frame(stats_right, bg="#F5F7FA")
            row.pack(anchor=tk.E, padx=14, pady=6)
            tk.Label(
                row, text=lbl_txt,
                font=("Microsoft YaHei", 11),
                fg=COLOR_TEXT_SEC, bg="#F5F7FA", width=8, anchor=tk.W
            ).pack(side=tk.LEFT)
            tk.Label(
                row, text=val_txt,
                font=("Microsoft YaHei", 14, "bold"),
                fg=color, bg="#F5F7FA", width=10, anchor=tk.E
            ).pack(side=tk.LEFT)

        # ===== 四个角度数据 =====
        angle_title = tk.Frame(content, bg=COLOR_BG)
        angle_title.pack(fill=tk.X, pady=(8, 2))
        tk.Label(
            angle_title, text="姿态角度分析",
            font=("Microsoft YaHei", 11, "bold"),
            fg=COLOR_TEXT, bg=COLOR_BG
        ).pack(anchor=tk.W)

        angles_row = tk.Frame(content, bg=COLOR_BG)
        angles_row.pack(fill=tk.X, pady=0)

        angle_data = [
            ("头部侧倾", session.get('avg_neck_angle'), COLOR_ACCENT),
            ("肩膀倾斜", session.get('avg_shoulder_diff'), COLOR_WARNING),
            ("头部前倾", session.get('avg_head_forward_angle'), COLOR_WARNING),
            ("躯干倾斜", session.get('avg_torso_angle'), COLOR_DANGER),
        ]

        for label, value, color in angle_data:
            cell = tk.Frame(angles_row, bg=COLOR_CARD, relief=tk.GROOVE, bd=1)
            cell.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=4)

            color_bar = tk.Frame(cell, bg=color, height=3)
            color_bar.pack(fill=tk.X)
            color_bar.pack_propagate(False)

            val_str = f"{value:.1f}°" if value is not None else "--"
            tk.Label(
                cell, text=label,
                font=("Microsoft YaHei", 9),
                fg=COLOR_TEXT_SEC, bg=COLOR_CARD
            ).pack(fill=tk.X, pady=5)

            tk.Label(
                cell, text=val_str,
                font=("Microsoft YaHei", 20, "bold"),
                fg=color, bg=COLOR_CARD
            ).pack(fill=tk.X, pady=2)

            tk.Label(
                cell, text="平均值",
                font=("Microsoft YaHei", 8),
                fg=COLOR_TEXT_SEC, bg=COLOR_CARD
            ).pack(fill=tk.X, pady=5)

        # ===== 底部操作按钮（固定底部） =====
        btn_bar = tk.Frame(win, bg=COLOR_CARD, height=54)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=16, pady=10)
        btn_bar.pack_propagate(False)

        btn_frame = tk.Frame(btn_bar, bg=COLOR_CARD)
        btn_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=6)

        export_btn = tk.Button(
            btn_frame, text="导出会话数据",
            font=("Microsoft YaHei", 10, "bold"),
            fg="#FFFFFF", bg=COLOR_ACCENT,
            activebackground="#1A82C4", activeforeground="#FFFFFF",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=lambda: self._do_export_session(session, win),
            padx=20, pady=7
        )
        export_btn.pack(side=tk.LEFT)

        delete_btn = tk.Button(
            btn_frame, text="删除当前会话",
            font=("Microsoft YaHei", 10, "bold"),
            fg="#FFFFFF", bg=COLOR_DANGER,
            activebackground="#C0392B", activeforeground="#FFFFFF",
            relief=tk.FLAT, bd=0, cursor="hand2",
            command=lambda: self._do_delete_session(session_id, win),
            padx=20, pady=7
        )
        delete_btn.pack(side=tk.RIGHT)

    def _do_export(self, export_type: str):
        labels = {'sessions': '会话记录', 'daily': '每日统计', 'violations': '违规记录'}
        label = labels.get(export_type, export_type)
        try:
            file_path = filedialog.asksaveasfilename(
                title=f"导出{label}",
                defaultextension=".csv",
                filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
                initialfile=f"posture_{export_type}_{date.today().isoformat()}.csv",
            )
            if not file_path:
                return
            self.data_manager.export_to_csv(file_path=file_path, export_type=export_type)
            messagebox.showinfo("导出成功", f"{label}已导出到:\n{file_path}")
        except Exception as e:
            logger.error(f"导出失败: {e}")
            messagebox.showerror("导出失败", f"导出时出错:\n{str(e)}")

    def _do_export_all_sessions(self):
        """导出全部会话到一个 CSV"""
        try:
            file_path = filedialog.asksaveasfilename(
                title="导出全部会话",
                defaultextension=".csv",
                filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
                initialfile=f"posture_all_sessions_{date.today().isoformat()}.csv",
            )
            if not file_path:
                return
            self.data_manager.export_all_sessions_to_csv(file_path)
            messagebox.showinfo("导出成功", f"全部会话已导出到:\n{file_path}")
        except ValueError as e:
            messagebox.showwarning("无可导出数据", str(e))
        except Exception as e:
            logger.error(f"导出全部会话失败: {e}")
            messagebox.showerror("导出失败", f"导出时出错:\n{str(e)}")

    def _do_export_daily_stats(self):
        """导出每日统计数据到 CSV"""
        try:
            file_path = filedialog.asksaveasfilename(
                title="导出每日统计",
                defaultextension=".csv",
                filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
                initialfile=f"posture_daily_stats_{date.today().isoformat()}.csv",
            )
            if not file_path:
                return
            self.data_manager.export_to_csv(
                file_path=file_path,
                export_type="daily",
                all_time=True
            )
            messagebox.showinfo("导出成功", f"每日统计数据已导出到:\n{file_path}")
        except Exception as e:
            logger.error(f"导出每日统计失败: {e}")
            messagebox.showerror("导出失败", f"导出时出错:\n{str(e)}")

    def _do_export_violations(self):
        """导出违规日志到 CSV"""
        try:
            file_path = filedialog.asksaveasfilename(
                title="导出违规日志",
                defaultextension=".csv",
                filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
                initialfile=f"posture_violations_{date.today().isoformat()}.csv",
            )
            if not file_path:
                return
            self.data_manager.export_to_csv(
                file_path=file_path,
                export_type="violations",
                all_time=True
            )
            messagebox.showinfo("导出成功", f"违规日志已导出到:\n{file_path}")
        except Exception as e:
            logger.error(f"导出违规日志失败: {e}")
            messagebox.showerror("导出失败", f"导出时出错:\n{str(e)}")

    def _do_clear_all_sessions(self):
        """清空全部历史记录"""
        if self.data_manager.get_current_session_id() is not None:
            messagebox.showwarning("正在监测", "请先结束当前监测会话，再清空历史记录。")
            return
        if not messagebox.askyesno("确认清除", "确定要清除所有历史会话记录吗？\n此操作不可恢复。"):
            return
        try:
            count = self.data_manager.clear_all_sessions()
            self._load_data()
            if self._detail_win:
                try:
                    self._detail_win.destroy()
                    self._detail_win = None
                except Exception:
                    pass
            messagebox.showinfo("清除成功", f"已清除 {count} 条会话记录。")
            logger.info(f"已清除全部会话记录，共 {count} 条")
        except Exception as e:
            logger.error(f"清除历史记录失败: {e}")
            messagebox.showerror("清除失败", f"清除时出错:\n{str(e)}")

    def _do_export_session(self, session: Dict, win: tk.Toplevel):
        """导出单个会话为 CSV"""
        try:
            file_path = filedialog.asksaveasfilename(
                title="导出会话记录",
                defaultextension=".csv",
                filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
                initialfile=f"posture_session_{session.get('id', '')}_{date.today().isoformat()}.csv",
            )
            if not file_path:
                return
            self.data_manager.export_session_to_csv(session, file_path)
            messagebox.showinfo("导出成功", f"会话记录已导出到:\n{file_path}")
        except Exception as e:
            logger.error(f"导出会话失败: {e}")
            messagebox.showerror("导出失败", f"导出时出错:\n{str(e)}")

    def _do_delete_session(self, session_id: int, win: tk.Toplevel):
        """删除当前会话"""
        if session_id == self.data_manager.get_current_session_id():
            messagebox.showwarning("正在监测", "请先结束当前监测会话，再删除这条记录。")
            return
        if not messagebox.askyesno("确认删除", "确定要删除这条会话记录吗？此操作不可恢复。"):
            return
        try:
            self.data_manager.delete_session(session_id)
            self._detail_win = None
            win.destroy()
            self._load_data()
            logger.info(f"会话已删除: id={session_id}")
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            messagebox.showerror("删除失败", f"删除时出错:\n{str(e)}")

    # ================================================================
    #  辅助方法
    # ================================================================

    def _fmt_dur(self, seconds: int) -> str:
        if seconds <= 0:
            return "00:00:00"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _darken(self, hex_color: str, factor: float = 0.85) -> str:
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}"


def create_history_viewer(parent, data_manager, current_settings: Dict = None) -> HistoryViewer:
    return HistoryViewer(parent, data_manager, current_settings)
