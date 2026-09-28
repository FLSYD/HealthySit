"""
姿态检测核心模块
使用 MediaPipe 和 OpenCV 实现人体骨骼点检测
"""

import cv2
import mediapipe as mp
import numpy as np
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)


class PoseDetector:
    """人体姿态检测器"""

    NOSE = 0
    LEFT_EYE = 1
    RIGHT_EYE = 2
    LEFT_EAR = 7
    RIGHT_EAR = 8
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_HIP = 23
    RIGHT_HIP = 24
    NUM_LANDMARKS = 33

    def __init__(self,
                 static_image_mode: bool = False,
                 model_complexity: int = 1,
                 smooth_landmarks: bool = True,
                 enable_segmentation: bool = False,
                 smooth_segmentation: bool = True,
                 min_detection_confidence: float = 0.5,
                 min_tracking_confidence: float = 0.5):
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles

        self.pose = self.mp_pose.Pose(
            static_image_mode=static_image_mode,
            model_complexity=model_complexity,
            smooth_landmarks=smooth_landmarks,
            enable_segmentation=enable_segmentation,
            smooth_segmentation=smooth_segmentation,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )

        logger.info("姿态检测器初始化完成")

    def detect_pose(self, frame: np.ndarray) -> Tuple[bool, Optional[any]]:
        """检测视频帧中的人体姿态"""
        if frame is None or frame.size == 0:
            return False, None
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False
        try:
            results = self.pose.process(rgb_frame)
        finally:
            rgb_frame.flags.writeable = True
        success = results.pose_landmarks is not None
        return success, results

    def get_landmark(self,
                     results: any,
                     landmark_idx: int,
                     image_shape: Tuple[int, int],
                     min_visibility: float = 0.15) -> Optional[Tuple[float, float]]:
        """获取指定关键点的坐标（极低可见度阈值）"""
        if results is None or results.pose_landmarks is None:
            return None

        landmarks = results.pose_landmarks.landmark
        if not 0 <= landmark_idx < len(landmarks):
            return None
        landmark = landmarks[landmark_idx]

        # 大幅降低可见度阈值，从0.5降到0.15
        if (not np.isfinite([landmark.x, landmark.y, landmark.visibility]).all()
                or landmark.visibility < min_visibility):
            return None

        h, w = image_shape[:2]
        x = landmark.x * w
        y = landmark.y * h

        return (x, y)

    def get_nose(self, results: any, image_shape: Tuple[int, int]) -> Optional[Tuple[float, float]]:
        """获取鼻尖坐标（使用较低可见度阈值，适应更多姿态）"""
        return self.get_landmark(results, self.NOSE, image_shape, min_visibility=0.05)

    def get_multiple_landmarks(self,
                              results: any,
                              landmark_indices: List[int],
                              image_shape: Tuple[int, int]) -> dict:
        """获取多个关键点的坐标"""
        landmarks = {}
        for idx in landmark_indices:
            landmarks[idx] = self.get_landmark(results, idx, image_shape)
        return landmarks

    def get_upper_body_landmarks(self,
                                results: any,
                                image_shape: Tuple[int, int]) -> dict:
        """获取上半身关键点（鼻尖、耳朵、肩膀、臀部）"""
        indices = [
            self.NOSE,
            self.LEFT_EAR, self.RIGHT_EAR,
            self.LEFT_SHOULDER, self.RIGHT_SHOULDER,
            self.LEFT_HIP, self.RIGHT_HIP
        ]

        names = [
            'nose',
            'left_ear', 'right_ear',
            'left_shoulder', 'right_shoulder',
            'left_hip', 'right_hip'
        ]

        landmarks = self.get_multiple_landmarks(results, indices, image_shape)
        # 鼻尖使用专用低阈值方法
        nose_point = self.get_nose(results, image_shape)
        result_dict = dict(zip(names, [landmarks[i] for i in indices]))
        if nose_point is not None:
            result_dict['nose'] = nose_point
        return result_dict

    def get_any_upper_body_point(self, results: any, image_shape: Tuple[int, int]) -> bool:
        """检查是否检测到任何上半身关键点"""
        if results is None or results.pose_landmarks is None:
            return False

        # 检查肩膀是否存在
        for idx in [self.LEFT_SHOULDER, self.RIGHT_SHOULDER, self.LEFT_HIP, self.RIGHT_HIP]:
            if self.get_landmark(results, idx, image_shape) is not None:
                return True
        return False

    def draw_landmarks(self,
                      frame: np.ndarray,
                      results: any,
                      sitting_view: str = "front") -> np.ndarray:
        """在图像上绘制骨骼点，根据视角选择绘制范围

        正坐（front）：只绘制双耳+双肩（4点）+ 耳朵到肩膀、肩膀之间的连线
        侧坐（side）：只绘制近端单耳+单肩+单髋（3点）+ 对应连线
        """
        if results is None or results.pose_landmarks is None:
            return frame

        if sitting_view == "front":
            self._draw_front_connections(frame, results.pose_landmarks.landmark)
        else:
            self._draw_side_connections(frame, results.pose_landmarks.landmark)

        return frame

    def _draw_front_connections(self, frame: np.ndarray, landmarks) -> None:
        """绘制正坐模式骨骼（双耳+双肩 + 完整连线）"""
        h, w = frame.shape[:2]

        # 正坐连线：双耳→双肩 + 肩与肩
        connections = [
            (self.LEFT_EAR, self.LEFT_SHOULDER),
            (self.RIGHT_EAR, self.RIGHT_SHOULDER),
            (self.LEFT_SHOULDER, self.RIGHT_SHOULDER),
        ]

        for start_idx, end_idx in connections:
            if start_idx < len(landmarks) and end_idx < len(landmarks):
                start = landmarks[start_idx]
                end = landmarks[end_idx]
                if start.visibility > 0.1 and end.visibility > 0.1:
                    start_coords = (int(start.x * w), int(start.y * h))
                    end_coords = (int(end.x * w), int(end.y * h))
                    cv2.line(frame, start_coords, end_coords, (0, 220, 130), 3, cv2.LINE_AA)

        # 绘制4个关键点：双耳+双肩
        for idx in [self.LEFT_EAR, self.RIGHT_EAR,
                    self.LEFT_SHOULDER, self.RIGHT_SHOULDER]:
            if idx < len(landmarks):
                point = landmarks[idx]
                if point.visibility > 0.1:
                    coords = (int(point.x * w), int(point.y * h))
                    cv2.circle(frame, coords, 6, (0, 220, 130), -1, cv2.LINE_AA)
                    cv2.circle(frame, coords, 6, (255, 255, 255), 2, cv2.LINE_AA)

    def _draw_side_connections(self, frame: np.ndarray, landmarks) -> None:
        """绘制侧坐模式骨骼（近端单耳+单肩+单髋 + 完整侧面连线）

        判断近端侧：以臀部可见度为主（侧坐时靠近镜头的髋部可见度更高），
        可见度相同时参考肩膀，最终参考耳朵。
        """
        h, w = frame.shape[:2]

        # 判断哪一侧更近（可见度更高的那侧）
        if len(landmarks) <= max(self.LEFT_HIP, self.RIGHT_HIP):
            return
        l_hip = landmarks[self.LEFT_HIP]
        r_hip = landmarks[self.RIGHT_HIP]
        l_shoulder = landmarks[self.LEFT_SHOULDER]
        r_shoulder = landmarks[self.RIGHT_SHOULDER]
        l_ear = landmarks[self.LEFT_EAR]
        r_ear = landmarks[self.RIGHT_EAR]

        l_score = (l_hip.visibility + l_shoulder.visibility)
        r_score = (r_hip.visibility + r_shoulder.visibility)
        if abs(l_score - r_score) < 0.1:
            # 可见度接近时，用肩膀补充
            l_score += l_ear.visibility
            r_score += r_ear.visibility

        is_left_near = l_score >= r_score
        ear_idx = self.LEFT_EAR if is_left_near else self.RIGHT_EAR
        shoulder_idx = self.LEFT_SHOULDER if is_left_near else self.RIGHT_SHOULDER
        hip_idx = self.LEFT_HIP if is_left_near else self.RIGHT_HIP

        # 侧坐连线：耳朵→肩膀→髋部
        connections = [
            (ear_idx, shoulder_idx),
            (shoulder_idx, hip_idx),
        ]

        for start_idx, end_idx in connections:
            if start_idx < len(landmarks) and end_idx < len(landmarks):
                start = landmarks[start_idx]
                end = landmarks[end_idx]
                if start.visibility > 0.1 and end.visibility > 0.1:
                    start_coords = (int(start.x * w), int(start.y * h))
                    end_coords = (int(end.x * w), int(end.y * h))
                    cv2.line(frame, start_coords, end_coords, (0, 220, 130), 3, cv2.LINE_AA)

        # 绘制3个关键点：单耳+单肩+单髋
        for idx in [ear_idx, shoulder_idx, hip_idx]:
            if idx < len(landmarks):
                point = landmarks[idx]
                if point.visibility > 0.1:
                    coords = (int(point.x * w), int(point.y * h))
                    cv2.circle(frame, coords, 6, (0, 220, 130), -1, cv2.LINE_AA)
                    cv2.circle(frame, coords, 6, (255, 255, 255), 2, cv2.LINE_AA)

    def calculate_angle(self,
                       point1: Tuple[float, float],
                       point2: Tuple[float, float],
                       reference: str = 'horizontal') -> Optional[float]:
        """计算两点之间的角度"""
        if point1 is None or point2 is None:
            return None

        x1, y1 = point1
        x2, y2 = point2
        dx = x2 - x1
        dy = y2 - y1
        if not np.isfinite([dx, dy]).all() or (dx == 0 and dy == 0):
            return None

        if reference == 'horizontal':
            angle = np.degrees(np.arctan2(dy, dx))
        else:
            angle = np.degrees(np.arctan2(dx, dy))

        return angle

    def release(self):
        """释放资源"""
        if self.pose is not None:
            self.pose.close()
            self.pose = None
        logger.info("姿态检测器已关闭")


def create_pose_detector() -> PoseDetector:
    """创建姿态检测器的工厂函数"""
    return PoseDetector(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
