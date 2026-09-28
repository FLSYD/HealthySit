"""
主窗口组件
整合所有UI组件，提供完整的应用程序界面
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import time
import logging
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Dict, Any

from ui.camera_preview import CameraPreview
from ui.status_panel import StatusPanel
from ui.control_panel import ControlPanel
from ui.settings_dialog import SettingsDialog
from ui.history_viewer import HistoryViewer
from src.data_manager import DataManager

logger = logging.getLogger(__name__)


class MainWindow:
    """主窗口"""

    def __init__(self, root: tk.Tk):
        """初始化主窗口"""
        self.root = root
        self.root.title("HealthySit - 智能坐姿监测系统")
        self.root.geometry("1200x780")
        self.root.resizable(False, False)

        # 组件
        self.camera_preview: Optional[CameraPreview] = None
        self.status_panel: Optional[StatusPanel] = None
        self.control_panel: Optional[ControlPanel] = None

        # 状态
        self.is_running = False
        self.current_session_id = None

        # 设置
        self.settings = self._get_default_settings()

        # 后台线程
        self.video_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.posture_analyzer = None
        self.audio_manager = None
        self._is_paused = False
        self._pending_action = None
        self._closing = False
        self._closed = False
        self._close_callbacks = []
        self._worker_error = None
        self._ui_events = queue.SimpleQueue()
        self._latest_ui_update = None

        # 重置标记：防止 reset 时 UI 闪现 0
        self._resetting = False

        # FPS 计算
        self.frame_count = 0
        self.fps_start_time = time.time()
        self.current_fps = 0

        # 当前显示的图像引用
        self.current_photo = None
        self._latest_preview_frame = None
        self._preview_loop_active = True
        self._last_preview_update_ts = 0.0

        # 数据管理器（在整个应用生命周期内持久化）
        self.data_manager = DataManager()
        self._last_violation_type: Optional[str] = None

        self._setup_style()
        self._setup_ui()

        logger.info("主窗口初始化完成")

    def _get_default_settings(self) -> Dict[str, Any]:
        """获取默认设置"""
        return {
            'neck_tilt_threshold': 15.0,
            'shoulder_threshold': 15.0,
            'head_forward_threshold': 20.0,
            'torso_threshold': 15.0,
            'sedentary_minutes': 60,
            'show_skeleton': True,
            'sound_enabled': True,
            'repeat_count': 1,
        }

    def _setup_style(self):
        """设置样式"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except:
            pass

        style.configure('Card.TFrame', background='#FFFFFF')
        style.configure('Card.TLabelframe', background='#FFFFFF')
        style.configure('Card.TLabelframe.Label', background='#FFFFFF')
        self.root.configure(bg='#E8ECF0')

    def _setup_ui(self):
        """设置UI"""
        self._create_header()

        # 主内容区域
        main_container = tk.Frame(self.root, bg='#E8ECF0')
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # 左侧：摄像头预览卡片
        left_card = tk.Frame(main_container, bg='#FFFFFF')
        left_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 16))

        self._create_camera_section(left_card)

        # 右侧：状态面板卡片
        right_card = tk.Frame(main_container, bg='#FFFFFF')
        right_card.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(16, 0))
        right_card.configure(width=380)
        right_card.pack_propagate(False)

        self._create_status_section(right_card)

        # 底部：控制面板
        control_card = tk.Frame(self.root, bg='#FFFFFF')
        control_card.pack(fill=tk.X, padx=20, pady=(0, 12))

        self._create_control_section(control_card)

        # 状态栏
        self._create_statusbar()

    def _create_header(self):
        """创建标题栏"""
        header = tk.Frame(self.root, bg='#1E3A5F', height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title = tk.Label(
            header,
            text="HealthySit - 智能坐姿监测系统",
            font=("Microsoft YaHei", 18, "bold"),
            fg="#FFFFFF",
            bg='#1E3A5F'
        )
        title.pack(side=tk.LEFT, padx=24, pady=12)

    def _create_camera_section(self, parent):
        """创建摄像头区域"""
        header = tk.Frame(parent, bg='#FFFFFF')
        header.pack(fill=tk.X, padx=16, pady=(16, 8))

        ttk.Label(
            header,
            text="实时预览",
            font=("Microsoft YaHei", 13, "bold"),
            foreground="#1E3A5F"
        ).pack(side=tk.LEFT)

        canvas_frame = tk.Frame(parent, bg='#2C3E50')
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        self.video_canvas = tk.Canvas(
            canvas_frame,
            width=640,
            height=480,
            bg='#2C3E50',
            highlightthickness=0,
            bd=0
        )
        self.video_canvas.pack()

        self.camera_preview = CameraPreview(640, 480)

        # 显示初始空闲画面
        self.root.after(100, self._show_idle_preview)
        self.root.after(50, self._preview_refresh_loop)

    def _create_status_section(self, parent):
        """创建状态区域"""
        self.status_panel = StatusPanel(parent)
        self.status_panel.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

    def _create_control_section(self, parent):
        """创建控制区域"""
        self.control_panel = ControlPanel(parent)
        self.control_panel.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        self.control_panel.on_start = self.start_monitoring
        self.control_panel.on_pause = self.pause_monitoring
        self.control_panel.on_stop = self.stop_monitoring
        self.control_panel.on_settings = self.open_settings
        self.control_panel.on_history = self.open_history_viewer
        self.control_panel.set_on_reset(self.reset_session)

    def _create_statusbar(self):
        """创建状态栏"""
        self.statusbar = tk.Frame(self.root, bg='#D5DCE5', height=32)
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)
        self.statusbar.pack_propagate(False)

        self.status_label = tk.Label(
            self.statusbar,
            text="就绪",
            font=("Microsoft YaHei", 10),
            fg="#5A6978",
            bg='#D5DCE5',
            anchor=tk.W
        )
        self.status_label.pack(side=tk.LEFT, padx=20, pady=4)

        self.camera_status = tk.Label(
            self.statusbar,
            text="摄像头: 未连接",
            font=("Microsoft YaHei", 10),
            fg="#5A6978",
            bg='#D5DCE5',
            anchor=tk.E
        )
        self.camera_status.pack(side=tk.RIGHT, padx=20, pady=4)

    def start_monitoring(self):
        """开始或继续监测；只有初始化成功才切换按钮。"""
        if self.is_running or self._pending_action or self._closing:
            return False
        if self.video_thread and self.video_thread.is_alive():
            return False
        if not self.camera_preview.open_camera(0):
            messagebox.showerror("错误", "无法打开摄像头或读取实时画面，请检查摄像头是否被其他程序占用后重试。")
            self.status_panel.set_error("摄像头连接失败")
            return False

        try:
            if self._is_paused:
                self.posture_analyzer.resume_sitting()
            else:
                self.posture_analyzer = self._create_analyzer()
                self.current_session_id = self.data_manager.start_session()
                self._no_detection_paused = False
                self._last_violation_type = None
                self._reminder_count = 1
                self._last_main_multiple = 0
            self._is_paused = False
            self._worker_error = None
            self._latest_ui_update = None
            self._latest_preview_frame = None
            self._last_preview_update_ts = time.time()
            self.frame_count = 0
            self.fps_start_time = time.time()
            self.current_fps = 0
            self.stop_event.clear()
            self.is_running = True
            self.status_panel.set_running()
            self.camera_preview.set_preview_state("running")
            self.control_panel.set_monitoring_state(1)
            self.update_status("正在监测...")
            self.video_thread = threading.Thread(target=self._video_loop, daemon=True)
            self.video_thread.start()
        except Exception as exc:
            logger.exception("启动监测失败")
            self._worker_error = f"启动监测失败: {exc}"
            self._request_transition("error")
            return False
        logger.info("开始监测")
        return True

    def _create_analyzer(self):
        """创建坐姿分析器"""
        from src.posture_analyzer import PostureAnalyzer
        analyzer = PostureAnalyzer(
            neck_tilt_threshold=self.settings['neck_tilt_threshold'],
            head_forward_threshold=self.settings['head_forward_threshold'],
            torso_threshold=self.settings['torso_threshold'],
            shoulder_threshold=self.settings['shoulder_threshold'],
            consecutive_frames=3,
            sensitivity=5
        )
        analyzer.set_sedentary_threshold(self.settings['sedentary_minutes'])
        return analyzer

    def pause_monitoring(self):
        """停止视频线程后冻结统计，保留同一分析器及数据库会话。"""
        if self.is_running:
            self._request_transition("pause")

    def _request_transition(self, action):
        """只在主线程推进生命周期，避免 join 阻塞 Tk 事件循环。"""
        if self._pending_action:
            if action == "close":
                self._pending_action = "close"
            return
        self._pending_action = action
        self.is_running = False
        self.stop_event.set()
        self.control_panel.set_busy(True)
        self._wait_for_video_stop()

    def _wait_for_video_stop(self):
        if self.video_thread and self.video_thread.is_alive():
            self.root.after(20, self._wait_for_video_stop)
            return
        action = self._pending_action
        self._pending_action = None
        self.video_thread = None
        self._latest_preview_frame = None
        self._latest_ui_update = None
        self.camera_preview.close()
        while not self._ui_events.empty():
            self._ui_events.get_nowait()
        if self.posture_analyzer is not None and not self._is_paused:
            self.posture_analyzer.pause_sitting()
            self._is_paused = True
        if action == "pause":
            self.control_panel.set_monitoring_state(2)
            self._pause_ui_update()
        else:
            if not self._finish_session():
                self._worker_error = None
                self._closing = False
                self._close_callbacks.clear()
                if not self._preview_loop_active:
                    self._preview_loop_active = True
                    self.root.after(33, self._preview_refresh_loop)
                self.control_panel.set_monitoring_state(2)
                self.control_panel.set_busy(False)
                self._pause_ui_update()
                self.update_status("保存失败，统计已保留，请重试结束监测")
                return
            self._is_paused = False
            self.posture_analyzer = None
            self.control_panel.reset_to_initial()
            if action == "close":
                self.data_manager.close()
                self._closed = True
                callbacks, self._close_callbacks = self._close_callbacks, []
                for callback in callbacks:
                    callback()
                return
            self._stop_ui_update()
            if action == "error":
                self.status_panel.set_error(self._worker_error or "监测线程异常退出")
                self.update_status(self._worker_error or "监测线程异常退出")
                self._worker_error = None
            elif action == "reset_running":
                self.control_panel.set_busy(False)
                self.start_monitoring()
            elif action == "reset_paused":
                self.posture_analyzer = self._create_analyzer()
                self.current_session_id = self.data_manager.start_session()
                self.posture_analyzer.pause_sitting()
                self._no_detection_paused = False
                self._last_violation_type = None
                self._reminder_count = 1
                self._last_main_multiple = 0
                self._is_paused = True
                self.control_panel.set_monitoring_state(2)
                self._pause_ui_update()
        self.control_panel.set_busy(False)

    def _finish_session(self):
        """后台写入停止后保存完整会话统计。"""
        if self.current_session_id is None:
            return True
        analyzer = self.posture_analyzer
        try:
            if analyzer is not None:
                stats = analyzer.get_statistics()
                angle_stats = analyzer.get_angle_stats()
                saved = self.data_manager.end_session(
                    posture_status=analyzer.last_status.value,
                    total_duration=int(stats['sitting_duration']),
                    total_violations=stats['violation_count'],
                    normal_duration=int(stats['normal_duration']),
                    violation_duration=int(stats['sitting_duration']) - int(stats['normal_duration']),
                    sitting_view=analyzer.current_view.value,
                    **angle_stats,
                )
            else:
                saved = self.data_manager.end_session(total_duration=0)
            if saved is False:
                raise RuntimeError("数据库未能结束当前会话，请稍后重试")
            self.current_session_id = None
            return True
        except Exception:
            logger.exception("保存监测会话失败")
            messagebox.showerror("保存失败", "监测数据保存失败，请查看日志中的详细原因。")
            return False

    def _pause_ui_update(self):
        """视频线程退出后同步显示暂停画面。"""
        self.status_panel.set_paused()
        self.camera_preview.set_preview_state("paused")
        self._do_pause_overlay()
        self.update_status("已暂停")

    def _do_pause_overlay(self):
        """实际执行暂停画面显示（在延迟后执行）"""
        logger.info("_do_pause_overlay 开始")
        try:
            paused_frame = self._create_paused_overlay()
            logger.info(f"_do_pause_overlay: paused_frame 生成完成, shape={paused_frame.shape}")
            photo = self.camera_preview.convert_to_tkinter(paused_frame)
            logger.info(f"_do_pause_overlay: photo 转换完成, photo={photo}")
            if photo:
                self.video_canvas.delete("all")
                self._canvas_image_id = self.video_canvas.create_image(0, 0, anchor=tk.NW, image=photo)
                self.current_photo = photo
                self.camera_status.config(text="摄像头: 已暂停")
                logger.info("_do_pause_overlay: 画布已更新")
            else:
                logger.warning("_do_pause_overlay: photo 为 None，跳过画布更新")
        except Exception as e:
            logger.error(f"_do_pause_overlay 执行出错: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _create_paused_overlay(self) -> np.ndarray:
        """创建暂停状态的遮罩画面"""
        import numpy as np
        # 创建深色背景
        frame = np.ones((480, 640, 3), dtype=np.uint8) * 35

        # 绘制暂停图标
        icon_x, icon_y = 320, 180
        # 外圆
        cv2.circle(frame, (icon_x, icon_y), 60, (230, 126, 34), -1)
        cv2.circle(frame, (icon_x, icon_y), 60, (255, 200, 100), 3)
        # 暂停符号 ||
        cv2.rectangle(frame, (icon_x - 20, icon_y - 30), (icon_x - 8, icon_y + 30), (255, 255, 255), -1)
        cv2.rectangle(frame, (icon_x + 8, icon_y - 30), (icon_x + 20, icon_y + 30), (255, 255, 255), -1)

        # 添加文字
        from PIL import Image, ImageDraw, ImageFont
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_frame)
        draw = ImageDraw.Draw(pil_img)

        try:
            font_title = ImageFont.truetype("msyh.ttc", 32)
            font_sub = ImageFont.truetype("msyh.ttc", 16)
        except:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        # 标题
        title = "监测已暂停"
        try:
            text_width = draw.textlength(title, font=font_title)
        except:
            text_width = 200
        draw.text(((640 - text_width) // 2, icon_y + 80), title, font=font_title, fill=(255, 200, 100))

        # 副标题
        subtitle = "点击「继续监测」按钮恢复"
        try:
            text_width = draw.textlength(subtitle, font=font_sub)
        except:
            text_width = 180
        draw.text(((640 - text_width) // 2, icon_y + 125), subtitle, font=font_sub, fill=(150, 150, 150))

        result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return result

    def stop_monitoring(self):
        """结束监测并保存当前会话。"""
        self._request_transition("stop")

    def _stop_ui_update(self):
        """同步显示结束画面，避免延迟回调覆盖新会话。"""
        self.status_panel.set_waiting()
        self.status_panel.update_data(sitting_view="waiting")
        self.camera_preview.set_preview_state("stopped")
        self._do_idle_overlay()
        self.update_status("监测已结束")

    def _do_idle_overlay(self):
        """实际执行空闲画面显示（在延迟后执行）"""
        logger.info("_do_idle_overlay 开始")
        try:
            idle_frame = self.camera_preview.get_idle_frame()
            logger.info(f"_do_idle_overlay: idle_frame 生成完成, type={type(idle_frame)}, shape={idle_frame.shape if hasattr(idle_frame, 'shape') else 'N/A'}")
            photo = self.camera_preview.convert_to_tkinter(idle_frame)
            logger.info(f"_do_idle_overlay: photo 转换完成, photo={photo}")
            if photo:
                self.video_canvas.delete("all")
                self._canvas_image_id = self.video_canvas.create_image(0, 0, anchor=tk.NW, image=photo)
                self.current_photo = photo
                self.camera_status.config(text="摄像头: 未连接")
                logger.info("_do_idle_overlay: 画布已更新")
            else:
                logger.warning("_do_idle_overlay: photo 为 None，跳过画布更新")
        except Exception as e:
            logger.error(f"_do_idle_overlay 执行出错: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def reset_session(self):
        """保存重置前的记录，新会话从零开始，避免历史明细与统计不符。"""
        if self._pending_action or self._closing:
            return
        if self.is_running:
            self._request_transition("reset_running")
        elif self._is_paused:
            self._request_transition("reset_paused")
        else:
            self.status_panel.update_data(sitting_view="waiting")
        self.update_status("统计已重置")

    def open_settings(self):
        """打开设置对话框"""
        def on_apply(new_settings):
            # 先更新 settings（确保所有路径读取的值一致）
            self.settings = new_settings

            # 更新姿态分析器的各阈值
            if hasattr(self, 'posture_analyzer') and self.posture_analyzer:
                self.posture_analyzer.neck_tilt_threshold = new_settings['neck_tilt_threshold']
                self.posture_analyzer.head_forward_threshold = new_settings['head_forward_threshold']
                self.posture_analyzer.torso_threshold = new_settings['torso_threshold']
                self.posture_analyzer.shoulder_threshold = new_settings['shoulder_threshold']
                self.posture_analyzer.set_sedentary_threshold(new_settings['sedentary_minutes'])

                new_interval_sec = new_settings['sedentary_minutes'] * 60
                self._repeat_limit = new_settings['repeat_count']
                if new_interval_sec > 0:
                    self._last_main_multiple = int(self.posture_analyzer.sitting_duration / new_interval_sec)
                    self._reminder_count = 1
                else:
                    self._reminder_count = float('inf')
                    self._last_main_multiple = float('inf')

            # 更新声音提醒状态（仅在监测已开始时生效）
            if hasattr(self, 'audio_manager') and self.audio_manager:
                self.audio_manager.set_enabled(new_settings['sound_enabled'])

            self.update_status("设置已应用")

        dialog = SettingsDialog(self.root, self.settings, on_apply=on_apply)
        new_settings = dialog.show()
        if new_settings:
            self.settings = new_settings
            self.update_status("设置已保存")

    def _show_idle_preview(self):
        """显示初始画面，但不覆盖已经开始的监测。"""
        if not self.is_running and not self._is_paused and not self._closing:
            self._do_idle_overlay()

    def _show_paused_preview(self):
        """显示暂停状态预览"""
        frame = self.camera_preview.get_paused_frame()
        photo = self.camera_preview.convert_to_tkinter(frame)
        if photo:
            self._update_canvas(photo)

    def _show_stopped_preview(self):
        """显示结束状态预览"""
        frame = self.camera_preview.get_stopped_frame()
        photo = self.camera_preview.convert_to_tkinter(frame)
        if photo:
            self._update_canvas(photo)

    def _video_loop(self):
        """后台只处理帧和数据，所有 Tk 操作由主线程刷新循环执行。"""
        pose_detector = None
        try:
            from src.pose_detector import create_pose_detector
            from src.audio_manager import create_audio_manager
            pose_detector = create_pose_detector()
            self.audio_manager = create_audio_manager(self.settings['sound_enabled'])
            failed_reads = 0
            while not self.stop_event.is_set():
                frame = self.camera_preview.read_frame()
                if frame is None:
                    if not self._no_detection_paused:
                        self.posture_analyzer.pause_sitting()
                        self._no_detection_paused = True
                    failed_reads += 1
                    if failed_reads >= 10:
                        raise RuntimeError("摄像头连续读取失败，请重新连接后开始监测")
                    self.stop_event.wait(0.1)
                    continue
                failed_reads = 0
                success, results = pose_detector.detect_pose(frame)
                if self.stop_event.is_set():
                    break
                if success:
                    if self._no_detection_paused:
                        self.posture_analyzer.resume_sitting()
                        self._no_detection_paused = False
                    landmarks = pose_detector.get_upper_body_landmarks(results, frame.shape[:2])
                    status, data = self.posture_analyzer.analyze_posture(landmarks)
                    interval_sec = self.settings['sedentary_minutes'] * 60
                    repeat_limit = self.settings['repeat_count']
                    if interval_sec > 0 and repeat_limit != 0:
                        current_multiple = self.posture_analyzer.sitting_duration // interval_sec
                        if current_multiple > self._last_main_multiple:
                            if repeat_limit == 11 or self._reminder_count <= repeat_limit:
                                self.audio_manager.play_reminder()
                                self._ui_events.put("reminder")
                            self._last_main_multiple = current_multiple
                            self._reminder_count += 1
                    if self.settings['show_skeleton']:
                        frame = pose_detector.draw_landmarks(
                            frame, results, sitting_view=data.get('sitting_view', 'front'))
                    self._latest_ui_update = (status, data)
                    status_key = status.value if hasattr(status, 'value') else str(status)
                    if status_key not in ('normal', 'no_detection'):
                        if status_key != self._last_violation_type:
                            self._log_violation(status_key, data)
                            self._last_violation_type = status_key
                    else:
                        self._last_violation_type = None
                else:
                    if not self._no_detection_paused:
                        self.posture_analyzer.pause_sitting()
                        self._no_detection_paused = True
                    self._latest_ui_update = (None, None)
                self.frame_count += 1
                elapsed = time.time() - self.fps_start_time
                if elapsed >= 1.0:
                    self.current_fps = self.frame_count / elapsed
                    self.frame_count = 0
                    self.fps_start_time = time.time()
                self._latest_preview_frame = self.camera_preview.process_frame(frame).copy()
        except Exception as exc:
            logger.exception("视频处理失败")
            self._worker_error = f"监测失败: {exc}"
            self.is_running = False
            self.stop_event.set()
        finally:
            if pose_detector is not None:
                try:
                    pose_detector.release()
                except Exception:
                    logger.exception("释放姿态检测器失败")
            self.camera_preview.close()
            self.audio_manager = None

    def _draw_status_on_frame(self, frame, status, data):
        """在帧上绘制状态信息（中文大字+英文小字）"""
        status_text = status.value if hasattr(status, 'value') else str(status)

        if status_text == 'normal':
            color = (0, 200, 120)
        elif status_text == 'shoulder_tilt':
            color = (255, 71, 87)        # 肩膀倾斜：红色（高优先级）
        elif status_text in ['head_forward', 'hunchback', 'head_tilt']:
            color = (255, 165, 0)        # 头部侧倾/前倾/驼背：橙色
        else:
            color = (52, 152, 219)

        h, w = frame.shape[:2]

        # 中文状态文字
        status_names_cn = {
            'normal': '坐姿正常',
            'head_forward': '头部前倾',
            'hunchback': '弯腰驼背',
            'head_tilt': '头部侧倾',
            'shoulder_tilt': '肩膀倾斜',
            'no_detection': '未检测到',
        }

        # 英文状态文字
        status_names_en = {
            'normal': 'Good posture',
            'head_forward': 'Head forward',
            'hunchback': 'Hunchback',
            'head_tilt': 'Head tilt',
            'shoulder_tilt': 'Shoulder tilt',
            'no_detection': 'No detection',
        }

        cn_status = status_names_cn.get(status_text, '未知状态')
        en_status = status_names_en.get(status_text, 'Unknown')

        # 使用PIL绘制中文
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_frame)
        draw = ImageDraw.Draw(pil_img)

        # 尝试加载中文字体
        try:
            font_cn = ImageFont.truetype("msyh.ttc", 28)
            font_en = ImageFont.truetype("arial.ttf", 18)
        except:
            font_cn = ImageFont.load_default()
            font_en = ImageFont.load_default()

        # 计算文字位置
        text_width_cn = draw.textlength(cn_status, font=font_cn) if hasattr(draw, 'textlength') else 100
        text_width_en = draw.textlength(en_status, font=font_en) if hasattr(draw, 'textlength') else 60

        # 背景框位置
        box_x, box_y = 15, 15
        box_w = max(int(text_width_cn), int(text_width_en)) + 50
        box_h = 80

        # 绘制半透明背景
        overlay = pil_img.copy()
        draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h],
                      fill=color + (200,))
        pil_img.putalpha(220)
        overlay.paste(pil_img, (0, 0), pil_img)

        # 绘制背景
        draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h],
                      fill=color)
        draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h],
                      outline=(255, 255, 255), width=2)

        # 绘制中文大字
        draw.text((box_x + 15, box_y + 10), cn_status, font=font_cn, fill=(255, 255, 255))

        # 绘制英文小字
        draw.text((box_x + 15, box_y + 48), en_status, font=font_en, fill=(220, 220, 220))

        # 转换回OpenCV格式
        result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        return result

    def _draw_no_detection(self, frame):
        """绘制未检测到人体的提示"""
        import cv2
        h, w = frame.shape[:2]

        overlay = frame.copy()
        cv2.rectangle(overlay, (w//4 - 60, h//2-30), (3*w//4 + 60, h//2+30), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_frame)
        draw = ImageDraw.Draw(pil_img)

        try:
            font = ImageFont.truetype("msyh.ttc", 28)
        except Exception:
            font = ImageFont.load_default()

        text = "请确保上半身在画面中可见"
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
        except Exception:
            text_w = len(text) * 28

        text_x = (w - text_w) // 2
        text_y = h // 2 - 14
        draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255))

        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def _update_ui(self, status, data):
        """更新UI"""
        # 重置状态或停止/暂停状态下不更新UI
        if self._resetting or self.stop_event.is_set():
            return

        status_map = {
            'normal': ('正常', '坐姿良好，继续保持'),
            'head_forward': ('头部前倾', '请将头部向后调整'),
            'hunchback': ('弯腰驼背', '请挺直腰背'),
            'head_tilt': ('头部侧倾', '请将头部摆正'),
            'shoulder_tilt': ('肩膀倾斜', '请保持肩膀平衡'),
            'no_detection': ('未检测到', '请确保上半身在画面中'),
        }

        status_text = status.value if hasattr(status, 'value') else str(status)
        status_info = status_map.get(status_text, ('未知', ''))

        self.status_panel.update_status(status_info[0], status_info[1])
        self.status_panel.update_data(
            neck_angle=data.get('neck_angle'),
            head_forward_angle=data.get('head_forward_angle'),
            torso_angle=data.get('torso_angle'),
            shoulder_diff=data.get('shoulder_diff'),
            sitting_time=int(data.get('sitting_duration', 0)),
            violations=data.get('violation_count', 0),
            fps=self.current_fps,
            sitting_view=data.get('sitting_view', 'front')
        )

    def _update_ui_no_detection(self):
        """更新UI为未检测状态"""
        if self._resetting or self.stop_event.is_set():
            return
        self.status_panel.update_status('未检测到', '请确保上半身在画面中')
        # 未检测时所有角度数据用 -- 显示，坐姿模式改为等待监测，坐姿时长和违规数保持不变
        self.status_panel.update_data(
            neck_angle=None, head_forward_angle=None,
            torso_angle=None, shoulder_diff=None,
            sitting_time=int(getattr(self.posture_analyzer, 'sitting_duration', 0)),
            violations=getattr(self.posture_analyzer, 'violation_count', 0),
            sitting_view="waiting"
        )

    def _update_canvas(self, photo):
        """更新画布"""
        # 如果已停止/暂停，不允许视频线程的帧覆盖暂停/空闲画面
        if self.stop_event.is_set():
            return

        if not hasattr(self, '_canvas_image_id'):
            self._canvas_image_id = self.video_canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        else:
            self.video_canvas.itemconfig(self._canvas_image_id, image=photo)

        self.current_photo = photo
        self.camera_status.config(text=f"摄像头: 已连接 | FPS: {self.current_fps:.1f}")

    def _preview_refresh_loop(self):
        """主线程定时刷新预览，避免后台线程直接操作 Tk 图像导致打包后黑屏"""
        if not self._preview_loop_active:
            return
        try:
            if self._worker_error and not self._pending_action:
                self._request_transition("error")
            if self.is_running and not self.stop_event.is_set():
                latest = self._latest_ui_update
                self._latest_ui_update = None
                if latest is not None:
                    status, data = latest
                    if status is None:
                        self._update_ui_no_detection()
                    else:
                        self._update_ui(status, data)
                if not self._ui_events.empty():
                    self._ui_events.get_nowait()
                    self._show_reminder()
            if self.is_running and not self.stop_event.is_set() and self._latest_preview_frame is not None:
                photo = self.camera_preview.convert_to_tkinter(self._latest_preview_frame)
                if photo:
                    self._update_canvas(photo)
                    self._last_preview_update_ts = time.time()
                else:
                    self.camera_status.config(text="摄像头: 画面转换失败")
            elif self.is_running and (time.time() - self._last_preview_update_ts) > 2.0:
                self.camera_status.config(text="摄像头: 已连接，但预览刷新异常")
        except Exception as e:
            logger.error(f"主线程预览刷新失败: {e}")
            self.camera_status.config(text="摄像头: 预览显示失败")
        finally:
            if self._preview_loop_active and self.root.winfo_exists():
                self.root.after(33, self._preview_refresh_loop)

    def _show_reminder(self):
        """显示久坐提醒"""
        messagebox.showwarning(
            "久坐提醒",
            "您已经连续坐姿时间过长，请起身活动一下！\n\n建议：站起来走动 3-5 分钟，做一些简单的伸展运动。"
        )

    def _log_violation(self, violation_type: str, data: Dict):
        """记录违规事件到数据库"""
        threshold_map = {
            'head_tilt': self.settings.get('neck_tilt_threshold', 15.0),
            'shoulder_tilt': self.settings.get('shoulder_threshold', 15.0),
            'head_forward': self.settings.get('head_forward_threshold', 20.0),
            'hunchback': self.settings.get('torso_threshold', 15.0),
        }
        value_map = {
            'head_tilt': data.get('neck_angle'),
            'shoulder_tilt': data.get('shoulder_diff'),
            'head_forward': data.get('head_forward_angle'),
            'hunchback': data.get('torso_angle'),
        }
        try:
            self.data_manager.log_violation(
                violation_type=violation_type,
                violation_value=value_map.get(violation_type),
                threshold_value=threshold_map.get(violation_type),
            )
        except Exception as e:
            logger.warning(f"记录违规事件失败: {e}")

    def open_history_viewer(self):
        """打开健康历史查看器"""
        HistoryViewer(self.root, self.data_manager, self.settings)

    def update_status(self, message: str):
        """更新状态栏"""
        self.status_label.config(text=message)

    def run(self):
        """运行应用"""
        self.status_panel.set_waiting()
        self.root.mainloop()

    def cleanup(self, on_complete=None):
        """等待后台释放并保存会话后再关闭窗口；重复调用保持幂等。"""
        if self._closed:
            return
        if on_complete is not None and on_complete not in self._close_callbacks:
            self._close_callbacks.append(on_complete)
        if self._closing:
            return
        self._closing = True
        self._preview_loop_active = False
        self._request_transition("close")


def create_main_window() -> MainWindow:
    """创建主窗口的工厂函数"""
    root = tk.Tk()
    return MainWindow(root)
