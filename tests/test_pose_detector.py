"""模拟模型响应，验证图像与关键点接口；不连接摄像头。"""

from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from src.pose_detector import PoseDetector


class PoseDetectorTests(unittest.TestCase):
    def setUp(self):
        self.constructor = mock.patch('src.pose_detector.mp.solutions.pose.Pose')
        self.pose_class = self.constructor.start()
        self.addCleanup(self.constructor.stop)
        self.detector = PoseDetector(static_image_mode=True)
        self.addCleanup(self.detector.release)
        self.model = self.pose_class.return_value

    def result(self, visibility=1.0):
        points = [SimpleNamespace(x=0.25, y=0.5, visibility=visibility)
                  for _ in range(33)]
        return SimpleNamespace(pose_landmarks=SimpleNamespace(landmark=points))

    def test_model_gets_read_only_rgb_and_original_frame_is_preserved(self):
        frame = np.full((2, 2, 3), [10, 20, 30], dtype=np.uint8)
        original = frame.copy()

        def process(rgb):
            self.assertEqual(rgb[0, 0].tolist(), [30, 20, 10])
            self.assertFalse(rgb.flags.writeable)
            return SimpleNamespace(pose_landmarks=None)

        self.model.process.side_effect = process
        success, result = self.detector.detect_pose(frame)
        self.assertFalse(success)
        self.assertIsNotNone(result)
        np.testing.assert_array_equal(frame, original)
        self.assertTrue(frame.flags.writeable)

    def test_empty_frame_does_not_invoke_model(self):
        self.assertEqual(self.detector.detect_pose(None), (False, None))
        self.assertEqual(self.detector.detect_pose(np.zeros((0, 0, 3), dtype=np.uint8)),
                         (False, None))
        self.model.process.assert_not_called()

    def test_landmarks_scale_correctly_and_use_nose_visibility_threshold(self):
        result = self.result(0.1)
        self.assertIsNone(self.detector.get_landmark(result, 11, (480, 640)))
        self.assertEqual(self.detector.get_nose(result, (480, 640)), (160, 240))
        result.pose_landmarks.landmark[11].visibility = 0.15
        self.assertTrue(self.detector.get_any_upper_body_point(result, (480, 640)))

    def test_truncated_and_non_finite_landmarks_are_ignored(self):
        result = self.result()
        result.pose_landmarks.landmark = result.pose_landmarks.landmark[:1]
        self.assertIsNone(self.detector.get_landmark(result, 11, (480, 640)))
        self.assertIsNone(self.detector.get_landmark(result, -1, (480, 640)))
        result.pose_landmarks.landmark[0].x = float('nan')
        self.assertIsNone(self.detector.get_nose(result, (480, 640)))
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        self.assertIs(self.detector.draw_landmarks(frame, result, 'side'), frame)

    def test_angles_handle_missing_or_degenerate_points(self):
        self.assertIsNone(self.detector.calculate_angle(None, (0, 0)))
        self.assertIsNone(self.detector.calculate_angle((1, 1), (1, 1)))
        self.assertEqual(self.detector.calculate_angle((0, 0), (0, 1)), 90)
        self.assertEqual(self.detector.calculate_angle((0, 0), (1, 0)), 0)

    def test_release_is_idempotent(self):
        self.detector.release()
        self.detector.release()
        self.model.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
