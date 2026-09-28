"""使用合成关键点和单调时钟验证姿态判断与计时。"""

import unittest
from unittest import mock

from src.posture_analyzer import PostureAnalyzer, PostureStatus, SittingView


class PostureAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.clock = mock.patch('src.posture_analyzer.time.monotonic', return_value=0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.analyzer = PostureAnalyzer()
        self.normal = {'left_shoulder': (200, 200), 'right_shoulder': (400, 200),
                       'left_ear': (200, 100), 'right_ear': (400, 100)}
        self.tilted = dict(self.normal, right_ear=(400, 180))

    def sample(self, timestamp, landmarks=None):
        self.now.return_value = timestamp
        return self.analyzer.analyze_posture(self.normal if landmarks is None else landmarks)

    def test_consecutive_frames_suppress_flicker_and_count_each_episode_once(self):
        for stamp in (0, 1):
            self.assertEqual(self.sample(stamp, self.tilted)[0], PostureStatus.NORMAL)
        self.assertEqual(self.sample(2, self.tilted)[0], PostureStatus.HEAD_TILT)
        self.sample(3, self.tilted)
        self.assertEqual(self.analyzer.violation_count, 1)
        self.sample(4)
        for stamp in (5, 6, 7):
            self.sample(stamp, self.tilted)
        self.assertEqual(self.analyzer.violation_count, 2)

    def test_real_state_durations_sum_to_detected_sitting_time(self):
        self.analyzer.consecutive_frames = 1
        self.sample(0)
        self.sample(10, self.tilted)
        self.sample(25)
        self.sample(30)
        stats = self.analyzer.get_statistics()
        self.assertEqual(stats['normal_duration'], 15)
        self.assertEqual(stats['violation_duration'], 15)
        self.assertEqual(stats['sitting_duration'], 30)

    def test_nested_pause_does_not_count_paused_interval(self):
        self.sample(0)
        self.sample(10)
        self.now.return_value = 12
        self.analyzer.pause_sitting()
        self.analyzer.pause_sitting()
        self.now.return_value = 100
        self.analyzer.resume_sitting()
        self.sample(1000)
        self.assertEqual(self.analyzer.sitting_duration, 12)
        self.analyzer.resume_sitting()
        self.sample(1001)
        self.sample(1011)
        self.assertEqual(self.analyzer.sitting_duration, 22)

    def test_missing_shoulders_freeze_timer_and_update_status(self):
        self.sample(0)
        self.sample(10)
        for stamp in (11, 12, 13):
            status, _ = self.sample(stamp, {})
        self.assertEqual(status, PostureStatus.NO_DETECTION)
        self.assertEqual(self.analyzer.last_status, PostureStatus.NO_DETECTION)
        self.sample(100)
        self.sample(105)
        self.assertEqual(self.analyzer.sitting_duration, 15)
        stats = self.analyzer.get_statistics()
        self.assertEqual(stats['normal_duration'] + stats['violation_duration'], 15)

    def test_side_angles_use_complete_same_side_pairs(self):
        landmarks = {'right_shoulder': (400, 200), 'left_shoulder': (200, 200),
                     'left_ear': (200, 100), 'left_hip': (200, 400)}
        self.assertEqual(self.analyzer._calculate_head_forward_angle(landmarks), 0)
        self.assertEqual(self.analyzer._calculate_torso_angle(landmarks), 0)
        self.assertIsNone(self.analyzer._calculate_torso_angle(
            {'right_shoulder': (400, 200), 'left_hip': (200, 400)}))

    def test_angle_boundaries_and_degenerate_points(self):
        for angle, expected in ((0, 0), (90, 90), (180, 0), (225, 45),
                                (-270, 90), (360, 0), (540, 0), (675, 45)):
            with self.subTest(angle=angle):
                self.assertEqual(self.analyzer._angle_acute(angle), expected)
        self.assertEqual(self.analyzer._findAngle_ver(0, 0, 0, 1), 0)
        self.assertEqual(self.analyzer._findAngle_hor(0, 0, 0, 1), 90)
        self.assertIsNone(self.analyzer._findAngle_hor(1, 1, 1, 1))
        self.assertIsNone(self.analyzer._findAngle_ver(0, 0, float('nan'), 1))

    def test_zero_sedentary_threshold_disables_reminders(self):
        self.analyzer.set_sedentary_threshold(1)
        self.sample(0)
        self.sample(60)
        self.assertTrue(self.analyzer.check_sedentary_reminder())
        self.analyzer.set_sedentary_threshold(0)
        self.assertFalse(self.analyzer.check_sedentary_reminder())

    def test_reset_clears_missing_detection_and_duration_state(self):
        self.sample(0)
        self.sample(10, self.tilted)
        self.analyzer.current_view = SittingView.SIDE
        for stamp in (11, 12, 13):
            self.sample(stamp, {})
        self.analyzer.reset_session()
        self.assertEqual(self.analyzer.last_status, PostureStatus.NORMAL)
        self.assertEqual(self.analyzer.current_view, SittingView.FRONT)
        self.assertEqual(self.analyzer.no_detection_frames, 0)
        self.sample(100)
        self.assertEqual(self.analyzer.get_statistics()['sitting_duration'], 0)
        self.assertEqual(self.analyzer.get_statistics()['violation_duration'], 0)


if __name__ == '__main__':
    unittest.main()
