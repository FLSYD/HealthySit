"""
坐姿判定逻辑模块
基于姿态检测结果进行坐姿分析

设计原则（参考 SittingProject 开源项目）：
  1. 根据肩膀宽度像素距离判断坐姿视角（正坐/侧坐）
  2. 正坐（front）检测：头部侧倾 + 肩膀倾斜
  3. 侧坐（side）检测：头部前倾 + 弯腰驼背
  4. 四种姿势完全独立检测，互不干扰
"""

import numpy as np
from typing import Dict, Optional, Tuple
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


class SittingView(Enum):
    """坐姿视角枚举"""
    FRONT = "front"   # 正坐：肩膀宽度大，肩膀连线与摄像头近似垂直
    SIDE = "side"     # 侧坐：肩膀宽度小，肩膀连线与摄像头近似平行


class PostureStatus(Enum):
    """坐姿状态枚举"""
    NORMAL = "normal"
    HEAD_FORWARD = "head_forward"   # 侧坐时：头部前倾
    HUNCHBACK = "hunchback"         # 侧坐时：弯腰驼背
    HEAD_TILT = "head_tilt"         # 正坐时：头部侧倾（歪头）
    SHOULDER_TILT = "shoulder_tilt" # 正坐时：肩膀倾斜
    NO_DETECTION = "no_detection"


# 正坐/侧坐判断：肩膀宽度像素阈值
# 阈值参考 SittingProject 经验值（100px），留出容差
FRONT_VIEW_SHOULDER_WIDTH_THRESHOLD = 100.0


class PostureAnalyzer:
    """坐姿分析器

    视角判断：
      shoulder_width > FRONT_VIEW_SHOULDER_WIDTH_THRESHOLD → 正坐（FRONT）
      shoulder_width <= FRONT_VIEW_SHOULDER_WIDTH_THRESHOLD → 侧坐（SIDE）

    正坐（FRONT）检测：
      - 头部侧倾：耳朵连线相对水平线的倾斜角（|angle| > threshold → 侧倾）
      - 肩膀倾斜：左右肩膀高度差（|diff| > threshold → 肩斜）

    侧坐（SIDE）检测：
      - 头部前倾：近侧耳-肩连线与垂直方向的夹角（angle > threshold → 前倾）
        （angle 越大 = 头部越向前探出）
      - 弯腰驼背：躯干倾斜角（相对垂直线，|angle| > threshold → 驼背）

    四种姿势有独立的连续帧计数器，互不干扰。
    同时检测到多种违规时，优先级：驼背 > 头前倾 > 侧倾 > 肩斜。
    """

    def __init__(self,
                 neck_tilt_threshold: float = 10.0,
                 head_forward_threshold: float = 20.0,
                 torso_threshold: float = 10.0,
                 shoulder_threshold: float = 15.0,
                 consecutive_frames: int = 3,
                 sensitivity: int = 5):
        self.base_neck_tilt_threshold = neck_tilt_threshold
        self.base_head_forward_threshold = head_forward_threshold
        self.base_torso_threshold = torso_threshold
        self.base_shoulder_threshold = shoulder_threshold

        self.consecutive_frames = consecutive_frames
        self.sensitivity = sensitivity

        self.neck_tilt_threshold = neck_tilt_threshold
        self.head_forward_threshold = head_forward_threshold
        self.torso_threshold = torso_threshold
        self.shoulder_threshold = shoulder_threshold

        # 四种姿势的连续帧计数器
        self.head_forward_frames = 0
        self.hunchback_frames = 0
        self.head_tilt_frames = 0
        self.shoulder_tilt_frames = 0

        # 当前处于违规状态的标记（用于一次违规只计一次）
        self._violation_active = {
            'head_forward': False,
            'hunchback': False,
            'head_tilt': False,
            'shoulder_tilt': False,
        }

        # 角度累积（用于会话结束时计算平均值）
        self._sum_neck_angle = 0.0
        self._sum_torso_angle = 0.0
        self._sum_head_forward_angle = 0.0
        self._sum_shoulder_diff = 0.0
        self._cnt_neck_angle = 0
        self._cnt_torso_angle = 0
        self._cnt_head_forward_angle = 0
        self._cnt_shoulder_diff = 0

        self._sitting_pause_ref: int = 0           # 嵌套引用计数
        self._sitting_pause_at: Optional[float] = None   # 冻结时的基准时刻
        self._sitting_duration_snapshot: float = 0.0  # 冻结时的快照值
        self.sitting_start_time = None
        self.sitting_duration = 0
        self.normal_duration = 0.0
        self.violation_duration = 0.0
        self._last_sample_time = None
        self._last_sample_status = PostureStatus.NORMAL
        self.sedentary_threshold = 45 * 60

        # 违规计数
        self.violation_count = 0
        self.total_violations = 0

        self.no_detection_frames = 0
        self.last_status = PostureStatus.NORMAL

        self.current_view = SittingView.FRONT
        self._view_stability_frames = 0
        self._last_view = SittingView.FRONT

        logger.info(f"坐姿分析器初始化完成，灵敏度: {sensitivity}")

    # ============================================================
    #  视角判断（正坐/侧坐）
    # ============================================================

    def _determine_view(self, shoulder_width: float) -> SittingView:
        """根据肩膀宽度像素距离判断正坐/侧坐

        原理：正对摄像头时，肩膀连线与图像平面平行，宽度大（约100~250px）
              侧对摄像头时，肩膀连线与图像平面垂直，宽度小（约30~80px）
        阈值 100px 为经验值，参考 SittingProject 论文分析超过100个样本得出。
        """
        if shoulder_width > FRONT_VIEW_SHOULDER_WIDTH_THRESHOLD:
            return SittingView.FRONT
        return SittingView.SIDE

    def _is_view_stable(self, new_view: SittingView, min_frames: int = 5) -> bool:
        """判断视角是否稳定（避免频繁切换导致误判）"""
        if new_view == self._last_view:
            self._view_stability_frames += 1
        else:
            self._view_stability_frames = 1
            self._last_view = new_view

        if self._view_stability_frames >= min_frames:
            self.current_view = new_view
            return True
        return False

    # ============================================================
    #  核心入口
    # ============================================================

    def analyze_posture(self, landmarks: Dict[str, Tuple[float, float]]) -> Tuple[PostureStatus, Dict]:
        """分析坐姿状态"""
        has_any_shoulder = (landmarks.get('left_shoulder') is not None
                            or landmarks.get('right_shoulder') is not None)

        if not has_any_shoulder:
            self.no_detection_frames += 1
            self._update_sitting_time(PostureStatus.NO_DETECTION)
            if self.no_detection_frames >= 3:
                self._reset_counters()
                self.last_status = PostureStatus.NO_DETECTION
            return self.last_status, {}
        else:
            self.no_detection_frames = 0

        # 计算肩宽以判断视角
        shoulder_width = self._calculate_shoulder_width(landmarks)
        raw_width = shoulder_width if shoulder_width is not None else 0.0
        view = self._determine_view(raw_width)
        self._is_view_stable(view)

        is_front = (self.current_view == SittingView.FRONT)

        # ----- 按视角计算相关指标 -----
        # 侧坐：头部前倾（单耳单肩单髋，近镜头侧）
        # 正坐：头部侧倾（双耳）+ 肩膀倾斜（双肩）
        if is_front:
            neck_tilt_angle = self._calculate_neck_tilt_angle(landmarks)
            shoulder_diff_angle = self._calculate_shoulder_diff_angle(landmarks)
            head_forward_angle = None
            torso_angle = None
        else:
            head_forward_angle = self._calculate_head_forward_angle(landmarks)
            torso_angle = self._calculate_torso_angle(landmarks)
            neck_tilt_angle = None
            shoulder_diff_angle = None

        # 四种姿势独立检测
        hf_active = self._check_head_forward(head_forward_angle, is_front)
        hb_active = self._check_hunchback(torso_angle)
        ht_active = self._check_head_tilt(neck_tilt_angle, is_front)
        st_active = self._check_shoulder_tilt(shoulder_diff_angle, is_front)

        if not (hf_active or hb_active or ht_active or st_active):
            self._reset_counters()

        status = self._get_priority_status()
        self.last_status = status
        self._update_sitting_time(status)

        analysis_data = {
            # 仅返回当前视角相关的指标，其余为 None（界面显示 --）
            'neck_angle': neck_tilt_angle,         # 正坐：头部侧倾角（°）
            'head_forward_angle': head_forward_angle,  # 侧坐：头部前倾角（°）
            'torso_angle': torso_angle,            # 侧坐：躯干倾斜角（°）
            'shoulder_diff': shoulder_diff_angle,  # 正坐：肩膀倾斜角（°）
            'shoulder_width': shoulder_width if shoulder_width is not None else 0.0,
            'sitting_view': self.current_view.value,
            'sitting_duration': self.sitting_duration,
            'violation_count': self.violation_count
        }

        # 角度累积（用于会话结束时计算平均值）
        self._sum_neck_angle += neck_tilt_angle if neck_tilt_angle is not None else 0.0
        self._sum_torso_angle += torso_angle if torso_angle is not None else 0.0
        self._sum_head_forward_angle += head_forward_angle if head_forward_angle is not None else 0.0
        self._sum_shoulder_diff += shoulder_diff_angle if shoulder_diff_angle is not None else 0.0
        # 各自累积帧数，避免视角切换导致均值被零稀释
        self._cnt_neck_angle += 1 if neck_tilt_angle is not None else 0
        self._cnt_torso_angle += 1 if torso_angle is not None else 0
        self._cnt_head_forward_angle += 1 if head_forward_angle is not None else 0
        self._cnt_shoulder_diff += 1 if shoulder_diff_angle is not None else 0

        return status, analysis_data

    # ============================================================
    #  角度计算（参考 SittingProject main_pose_detect.py）
    # ============================================================

    def _angle_acute(self, angle: float) -> float:
        """将任意角度转为锐角（0°~90°），值越大表示倾斜越严重"""
        a = abs(angle) % 180
        a = min(a, 180 - a)
        return round(a, 1)

    def _findAngle_hor(self,
                      x1: float, y1: float,
                      x2: float, y2: float) -> Optional[float]:
        """计算向量(x1,y1)→(x2,y2)与水平向右方向的夹角，转为锐角（0°~90°）
        值越大 = 倾斜越严重
        """
        dx = x2 - x1
        dy = y2 - y1
        if not np.isfinite([dx, dy]).all() or (dx == 0 and dy == 0):
            return None
        raw = np.degrees(np.arctan2(dy, dx))
        return self._angle_acute(raw)

    def _findAngle_ver(self,
                       x1: float, y1: float,
                       x2: float, y2: float) -> Optional[float]:
        """计算向量(x1,y1)→(x2,y2)与屏幕向上方向的夹角，转为锐角（0°~90°）
        值越大 = 倾斜越严重
        """
        dx = x2 - x1
        dy = y2 - y1
        if not np.isfinite([dx, dy]).all() or (dx == 0 and dy == 0):
            return None
        raw = np.degrees(np.arctan2(dx, -dy))
        return self._angle_acute(raw)

    def _calculate_shoulder_width(self, landmarks: Dict[str, Tuple[float, float]]) -> Optional[float]:
        """计算肩膀宽度（像素），用于判断正坐/侧坐"""
        left_shoulder = landmarks.get('left_shoulder')
        right_shoulder = landmarks.get('right_shoulder')
        if left_shoulder is None or right_shoulder is None:
            return None
        width = np.sqrt(
            (right_shoulder[0] - left_shoulder[0]) ** 2
            + (right_shoulder[1] - left_shoulder[1]) ** 2
        )
        return round(width, 1)

    # ---- 侧坐（Side）角度计算 ----

    def _calculate_head_forward_angle(self, landmarks: Dict[str, Tuple[float, float]]) -> Optional[float]:
        """计算头部前倾角度（侧坐模式）

        算法：SittingProject 侧坐头部前倾
        用近镜头侧肩膀、耳的连线与垂直方向的夹角
        角度越大 = 头部越向前探出

        入参需要：near_shoulder, near_ear
        返回：角度值（°），正负表示方向
        """
        l_shoulder = landmarks.get('left_shoulder')
        r_shoulder = landmarks.get('right_shoulder')
        l_ear = landmarks.get('left_ear')
        r_ear = landmarks.get('right_ear')

        near_shoulder = None
        near_ear = None
        if r_shoulder is not None and r_ear is not None:
            near_shoulder = r_shoulder
            near_ear = r_ear if r_ear is not None else None
        if near_shoulder is None and l_shoulder is not None and l_ear is not None:
            near_shoulder = l_shoulder
            near_ear = l_ear

        if near_shoulder is None or near_ear is None:
            return None

        return self._findAngle_ver(near_ear[0], near_ear[1],
                                   near_shoulder[0], near_shoulder[1])

    def _calculate_torso_angle(self, landmarks: Dict[str, Tuple[float, float]]) -> Optional[float]:
        """计算躯干倾斜角度（侧坐模式）

        算法：SittingProject 侧坐驼背检测
        用近镜头侧肩膀、髋部的连线与垂直方向的夹角
        角度越大 = 躯干越弯曲（弯腰）

        入参需要：near_shoulder, near_hip
        返回：角度值（°），正负表示方向
        """
        l_shoulder = landmarks.get('left_shoulder')
        r_shoulder = landmarks.get('right_shoulder')
        l_hip = landmarks.get('left_hip')
        r_hip = landmarks.get('right_hip')

        if r_shoulder is not None and r_hip is not None:
            near_shoulder, near_hip = r_shoulder, r_hip
        elif l_shoulder is not None and l_hip is not None:
            near_shoulder, near_hip = l_shoulder, l_hip
        else:
            return None

        return self._findAngle_ver(near_hip[0], near_hip[1],
                                   near_shoulder[0], near_shoulder[1])

    # ---- 正坐（Front）角度计算 ----

    def _calculate_neck_tilt_angle(self, landmarks: Dict[str, Tuple[float, float]]) -> Optional[float]:
        """计算头部侧倾角度（正坐模式）

        算法：SittingProject 正坐头部侧倾
        用双耳连线与水平线的夹角
        角度越大 = 头歪得越厉害
        """
        l_ear = landmarks.get('left_ear')
        r_ear = landmarks.get('right_ear')
        if l_ear is None or r_ear is None:
            return None
        return self._findAngle_hor(l_ear[0], l_ear[1],
                                   r_ear[0], r_ear[1])

    def _calculate_shoulder_diff_angle(self, landmarks: Dict[str, Tuple[float, float]]) -> Optional[float]:
        """计算肩膀倾斜角度（正坐模式）

        算法：双肩连线与水平向右方向的夹角，转为锐角（0°~90°）
        角度越大 = 肩膀越歪
        """
        l_shoulder = landmarks.get('left_shoulder')
        r_shoulder = landmarks.get('right_shoulder')
        if l_shoulder is None or r_shoulder is None:
            return None
        return self._findAngle_hor(l_shoulder[0], l_shoulder[1],
                                   r_shoulder[0], r_shoulder[1])

    # ============================================================
    #  四种姿势独立检测
    # ============================================================

    def _check_head_forward(self, head_forward_dist: Optional[float], is_front: bool) -> bool:
        """检测头部前倾（侧坐模式专用）"""
        if is_front:
            if self._violation_active['head_forward'] and self.head_forward_frames > 0:
                self.head_forward_frames = 0
                self._violation_active['head_forward'] = False
            else:
                self.head_forward_frames = 0
            return False

        if head_forward_dist is None:
            if self._violation_active['head_forward']:
                self.head_forward_frames = 0
                self._violation_active['head_forward'] = False
            else:
                self.head_forward_frames = 0
            return False

        if abs(head_forward_dist) > self.head_forward_threshold:
            self.head_forward_frames += 1
            if self.head_forward_frames == self.consecutive_frames:
                if not self._violation_active['head_forward']:
                    self._increment_violation()
                    self._violation_active['head_forward'] = True
                    logger.info(f"头部前倾检测触发: {head_forward_dist:.1f}° > {self.head_forward_threshold:.1f}°")
            return True

        if self.head_forward_frames > 0:
            self.head_forward_frames = 0
            self._violation_active['head_forward'] = False
        return False

    def _check_hunchback(self, torso_angle: Optional[float]) -> bool:
        """检测弯腰驼背（侧坐模式专用）
        一次违规只计一次
        """
        if torso_angle is None:
            if self._violation_active['hunchback']:
                self.hunchback_frames = 0
                self._violation_active['hunchback'] = False
            else:
                self.hunchback_frames = 0
            return False

        if torso_angle > self.torso_threshold:
            self.hunchback_frames += 1
            if self.hunchback_frames == self.consecutive_frames:
                if not self._violation_active['hunchback']:
                    self._increment_violation()
                    self._violation_active['hunchback'] = True
                    logger.info(f"弯腰驼背检测触发: {torso_angle:.1f}° > {self.torso_threshold:.1f}°")
            return True

        if self.hunchback_frames > 0:
            self.hunchback_frames = 0
            self._violation_active['hunchback'] = False
        return False

    def _check_head_tilt(self, neck_tilt_angle: Optional[float], is_front: bool) -> bool:
        """检测头部侧倾（正坐模式专用）

        is_front 仅用于传入上下文，实际角度判断与视角无关。
        角度由 _calculate_neck_tilt_angle 计算（正坐模式才有值，侧坐模式为 None）。
        """
        if neck_tilt_angle is None:
            if self.head_tilt_frames > 0:
                self.head_tilt_frames = 0
                self._violation_active['head_tilt'] = False
            return False

        if neck_tilt_angle > self.neck_tilt_threshold:
            self.head_tilt_frames += 1
            if self.head_tilt_frames == self.consecutive_frames:
                if not self._violation_active['head_tilt']:
                    self._increment_violation()
                    self._violation_active['head_tilt'] = True
                    logger.info(f"头部侧倾检测触发: {neck_tilt_angle:.1f}° > {self.neck_tilt_threshold:.1f}°")
            return True

        if self.head_tilt_frames > 0:
            self.head_tilt_frames = 0
            self._violation_active['head_tilt'] = False
        return False

    def _check_shoulder_tilt(self, shoulder_diff: Optional[float], is_front: bool) -> bool:
        """检测肩膀倾斜（正坐模式专用）

        is_front 仅用于传入上下文，实际角度判断与视角无关。
        角度由 _calculate_shoulder_diff_angle 计算（正坐模式才有值，侧坐模式为 None）。
        """
        if shoulder_diff is None:
            if self.shoulder_tilt_frames > 0:
                self.shoulder_tilt_frames = 0
                self._violation_active['shoulder_tilt'] = False
            return False

        if shoulder_diff > self.shoulder_threshold:
            self.shoulder_tilt_frames += 1
            if self.shoulder_tilt_frames == self.consecutive_frames:
                if not self._violation_active['shoulder_tilt']:
                    self._increment_violation()
                    self._violation_active['shoulder_tilt'] = True
                    logger.info(f"肩膀倾斜检测触发: {shoulder_diff:.1f}° > {self.shoulder_threshold:.1f}°")
            return True

        if self.shoulder_tilt_frames > 0:
            self.shoulder_tilt_frames = 0
            self._violation_active['shoulder_tilt'] = False
        return False

    def _get_priority_status(self) -> PostureStatus:
        """根据视角和计数器状态，返回优先级最高的状态

        正坐模式：头部侧倾 > 肩膀倾斜
        侧坐模式：弯腰驼背 > 头部前倾
        """
        CONSEC = self.consecutive_frames

        if self.current_view == SittingView.FRONT:
            # 正坐模式
            if self.head_tilt_frames >= CONSEC:
                return PostureStatus.HEAD_TILT
            if self.shoulder_tilt_frames >= CONSEC:
                return PostureStatus.SHOULDER_TILT
        else:
            # 侧坐模式
            if self.hunchback_frames >= CONSEC:
                return PostureStatus.HUNCHBACK
            if self.head_forward_frames >= CONSEC:
                return PostureStatus.HEAD_FORWARD

        return PostureStatus.NORMAL

    # ============================================================
    #  辅助方法
    # ============================================================

    def _increment_violation(self):
        self.violation_count += 1
        self.total_violations += 1

    def _reset_counters(self):
        self.head_forward_frames = 0
        self.hunchback_frames = 0
        self.head_tilt_frames = 0
        self.shoulder_tilt_frames = 0
        self._violation_active = {k: False for k in self._violation_active}

    def _update_sitting_time(self, status: PostureStatus):
        # 相邻有效采样之间的时间归属于前一采样状态，暂停和离席不累计。
        if self._sitting_pause_ref > 0 or status == PostureStatus.NO_DETECTION:
            self._last_sample_time = None
            return
        now = time.monotonic()
        if self.sitting_start_time is None:
            self.sitting_start_time = now
        if self._last_sample_time is not None:
            elapsed = max(0.0, now - self._last_sample_time)
            if self._last_sample_status == PostureStatus.NORMAL:
                self.normal_duration += elapsed
            else:
                self.violation_duration += elapsed
        self._last_sample_time = now
        self._last_sample_status = status
        self.sitting_duration = self.normal_duration + self.violation_duration

    def check_sedentary_reminder(self) -> bool:
        return self.sedentary_threshold > 0 and self.sitting_duration >= self.sedentary_threshold

    def set_sedentary_threshold(self, minutes: int):
        self.sedentary_threshold = max(0, minutes) * 60

    def set_sensitivity(self, sensitivity: int):
        self.sensitivity = max(1, min(10, sensitivity))

    def pause_sitting(self):
        """暂停久坐计时（支持嵌套引用计数）"""
        if self._sitting_pause_ref == 0:
            self._update_sitting_time(self.last_status)
            self._sitting_pause_at = time.monotonic()
            self._sitting_duration_snapshot = self.sitting_duration
            self._last_sample_time = None
        self._sitting_pause_ref += 1

    def resume_sitting(self):
        """恢复久坐计时（支持嵌套引用计数）"""
        if self._sitting_pause_ref > 0:
            self._sitting_pause_ref -= 1
        if self._sitting_pause_ref == 0 and self._sitting_pause_at is not None:
            self.sitting_start_time = time.monotonic() - self._sitting_duration_snapshot
            self._sitting_pause_at = None
            self._last_sample_time = None

    def reset_session(self):
        self.sitting_start_time = None
        self.sitting_duration = 0
        self.normal_duration = 0.0
        self.violation_duration = 0.0
        self._last_sample_time = None
        self._last_sample_status = PostureStatus.NORMAL
        self.no_detection_frames = 0
        self.last_status = PostureStatus.NORMAL
        self.current_view = SittingView.FRONT
        self._last_view = SittingView.FRONT
        self.violation_count = 0
        self._sitting_pause_ref = 0
        self._sitting_pause_at = None
        self._sitting_duration_snapshot = 0.0
        self._sum_neck_angle = 0.0
        self._sum_torso_angle = 0.0
        self._sum_head_forward_angle = 0.0
        self._sum_shoulder_diff = 0.0
        self._cnt_neck_angle = 0
        self._cnt_torso_angle = 0
        self._cnt_head_forward_angle = 0
        self._cnt_shoulder_diff = 0
        self._reset_counters()
        self._view_stability_frames = 0
        logger.info("会话统计已重置")

    def get_statistics(self) -> Dict:
        return {
            'sitting_duration': self.sitting_duration,
            'normal_duration': self.normal_duration,
            'violation_duration': self.violation_duration,
            'violation_count': self.violation_count,
            'total_violations': self.total_violations,
            'current_status': self._get_status_text()
        }

    def get_angle_stats(self) -> Dict:
        """获取角度统计（用于会话结束时计算平均值）"""
        def safe_avg(s, c):
            return (s / c) if c > 0 else None
        return {
            'avg_neck_angle': safe_avg(self._sum_neck_angle, self._cnt_neck_angle),
            'avg_torso_angle': safe_avg(self._sum_torso_angle, self._cnt_torso_angle),
            'avg_head_forward_angle': safe_avg(self._sum_head_forward_angle, self._cnt_head_forward_angle),
            'avg_shoulder_diff': safe_avg(self._sum_shoulder_diff, self._cnt_shoulder_diff),
        }

    def _get_status_text(self) -> str:
        status_map = {
            PostureStatus.HUNCHBACK: "弯腰驼背",
            PostureStatus.HEAD_FORWARD: "头部前倾",
            PostureStatus.HEAD_TILT: "头部侧倾",
            PostureStatus.SHOULDER_TILT: "肩膀倾斜",
            PostureStatus.NORMAL: "正常",
            PostureStatus.NO_DETECTION: "未检测到",
        }
        return status_map.get(self.last_status, "未知")


def create_posture_analyzer(sensitivity: int = 5,
                            sedentary_minutes: int = 60) -> PostureAnalyzer:
    analyzer = PostureAnalyzer(sensitivity=sensitivity)
    analyzer.set_sedentary_threshold(sedentary_minutes)
    return analyzer
