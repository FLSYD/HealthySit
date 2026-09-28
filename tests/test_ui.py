"""界面生命周期与摄像头回归测试：使用模拟 Tk、合成帧和临时数据库。"""

from contextlib import ExitStack
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import numpy as np

from ui.camera_preview import CameraPreview
from ui.control_panel import ControlPanel
from ui.history_viewer import HistoryViewer
from ui.main_window import MainWindow


class MainWindowTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch('ui.main_window.DataManager'))
        self.stack.enter_context(mock.patch.object(MainWindow, '_setup_style'))
        self.stack.enter_context(mock.patch.object(MainWindow, '_setup_ui'))
        self.errors = self.stack.enter_context(mock.patch('ui.main_window.messagebox.showerror'))
        self.root = mock.Mock()
        self.app = MainWindow(self.root)
        for name in ('camera_preview', 'control_panel', 'status_panel', 'status_label', 'camera_status'):
            setattr(self.app, name, mock.Mock())
        self.app.camera_preview.open_camera.return_value = True
        self.app.camera_preview.process_frame.side_effect = lambda frame: frame
        self.app.data_manager.start_session.side_effect = [41, 42, 43]
        self.app._do_idle_overlay = mock.Mock()
        self.app._do_pause_overlay = mock.Mock()
        self.thread_factory = self.stack.enter_context(mock.patch('ui.main_window.threading.Thread'))
        self.thread_factory.return_value.is_alive.return_value = False
        self.analyzer = mock.Mock()
        self.analyzer.sitting_duration = 60
        self.analyzer.violation_count = 2
        self.analyzer.last_status.value = 'normal'
        self.analyzer.current_view.value = 'front'
        self.analyzer.get_statistics.return_value = {
            'sitting_duration': 60, 'violation_count': 2,
            'normal_duration': 39, 'violation_duration': 21,
        }
        self.analyzer.get_angle_stats.return_value = {
            'avg_neck_angle': 4, 'avg_torso_angle': None,
            'avg_head_forward_angle': None, 'avg_shoulder_diff': 3,
        }
        self.app._create_analyzer = mock.Mock(return_value=self.analyzer)

    def _modules(self, detector=None, detector_error=None):
        detector = detector or mock.Mock()
        pose_module = types.ModuleType('src.pose_detector')
        pose_module.create_pose_detector = mock.Mock(return_value=detector, side_effect=detector_error)
        audio = mock.Mock()
        audio.play_reminder.return_value = False
        audio_module = types.ModuleType('src.audio_manager')
        audio_module.create_audio_manager = mock.Mock(return_value=audio)
        self.stack.enter_context(mock.patch.dict('sys.modules', {
            'src.pose_detector': pose_module, 'src.audio_manager': audio_module,
        }))
        return detector, audio

    def test_camera_failure_does_not_create_session_or_start_thread(self):
        self.app.camera_preview.open_camera.return_value = False
        self.assertFalse(self.app.start_monitoring())
        self.app.data_manager.start_session.assert_not_called()
        self.thread_factory.assert_not_called()
        self.assertFalse(self.app.is_running)

    def test_pause_resume_preserves_analyzer_and_existing_session(self):
        self.assertTrue(self.app.start_monitoring())
        self.app._no_detection_paused = True
        self.app.pause_monitoring()
        self.analyzer.pause_sitting.assert_called_once()
        self.app.data_manager.end_session.assert_not_called()
        self.assertTrue(self.app.start_monitoring())
        self.assertIs(self.app.posture_analyzer, self.analyzer)
        self.app._create_analyzer.assert_called_once()
        self.analyzer.resume_sitting.assert_called_once()
        self.app.data_manager.start_session.assert_called_once()
        self.assertTrue(self.app._no_detection_paused)

    def test_stop_after_pause_starts_a_fresh_session(self):
        self.app.start_monitoring()
        self.app.pause_monitoring()
        self.app.stop_monitoring()
        saved = self.app.data_manager.end_session.call_args.kwargs
        self.assertEqual(saved['normal_duration'], 39)
        self.assertEqual(saved['violation_duration'], 21)
        self.assertEqual(saved['total_duration'], 60)
        self.assertIsNone(self.app.posture_analyzer)
        self.assertIsNone(self.app.current_session_id)
        self.assertFalse(self.app._is_paused)
        self.assertTrue(self.app.start_monitoring())
        self.assertEqual(self.app.current_session_id, 42)
        self.assertEqual(self.app._create_analyzer.call_count, 2)

    def test_stop_waits_for_thread_without_join_or_early_release(self):
        self.app.start_monitoring()
        worker = self.app.video_thread
        worker.is_alive.return_value = True
        self.app.stop_monitoring()
        worker.join.assert_not_called()
        self.app.camera_preview.close.assert_not_called()
        self.app.data_manager.end_session.assert_not_called()
        self.assertFalse(self.app.start_monitoring())
        worker.is_alive.return_value = False
        self.root.after.call_args.args[1]()
        self.app.data_manager.end_session.assert_called_once()
        self.app.camera_preview.close.assert_called_once()

    def test_cleanup_waits_then_saves_once_before_destroy(self):
        self.app.start_monitoring()
        worker = self.app.video_thread
        worker.is_alive.return_value = True
        events = []
        self.app.data_manager.end_session.side_effect = lambda **kw: events.append('save')
        self.app.data_manager.close.side_effect = lambda: events.append('close')
        callback = mock.Mock(side_effect=lambda: events.append('destroy'))
        self.app.cleanup(callback)
        self.app.cleanup(callback)
        callback.assert_not_called()
        worker.is_alive.return_value = False
        self.root.after.call_args.args[1]()
        self.app.cleanup(callback)
        self.assertEqual(events, ['save', 'close', 'destroy'])
        callback.assert_called_once()

    def test_cleanup_without_monitoring_finishes_immediately(self):
        callback = mock.Mock()
        self.app.cleanup(callback)
        callback.assert_called_once()
        self.app.data_manager.end_session.assert_not_called()
        self.app.data_manager.close.assert_called_once()

    def test_close_supersedes_pending_pause(self):
        self.app.start_monitoring()
        worker = self.app.video_thread
        worker.is_alive.return_value = True
        self.app.pause_monitoring()
        callback = mock.Mock()
        self.app.cleanup(callback)
        self.assertEqual(self.app._pending_action, 'close')
        worker.is_alive.return_value = False
        self.root.after.call_args.args[1]()
        callback.assert_called_once()
        self.app.data_manager.end_session.assert_called_once()

    def test_failed_save_preserves_statistics_for_retry(self):
        self.app.start_monitoring()
        self.app.data_manager.end_session.side_effect = OSError('disk full')
        with self.assertLogs('ui.main_window', level='ERROR'):
            self.app.stop_monitoring()
        self.assertIs(self.app.posture_analyzer, self.analyzer)
        self.assertEqual(self.app.current_session_id, 41)
        self.assertTrue(self.app._is_paused)
        self.app.data_manager.end_session.side_effect = None
        self.app.stop_monitoring()
        self.assertIsNone(self.app.current_session_id)
        self.analyzer.pause_sitting.assert_called_once()

    def test_save_returning_false_does_not_discard_session(self):
        self.app.start_monitoring()
        self.app.data_manager.end_session.return_value = False
        with self.assertLogs('ui.main_window', level='ERROR'):
            self.app.stop_monitoring()
        self.assertEqual(self.app.current_session_id, 41)
        self.assertIs(self.app.posture_analyzer, self.analyzer)

    def test_lifecycle_persists_real_analyzer_stats_to_temporary_database(self):
        from src.data_manager import DataManager
        from src.posture_analyzer import PostureAnalyzer, PostureStatus
        temporary = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.app.data_manager = DataManager(str(Path(temporary) / 'test.db'))
        self.app._create_analyzer = PostureAnalyzer
        with mock.patch('src.posture_analyzer.time.monotonic', return_value=100) as clock:
            self.app.start_monitoring()
            analyzer = self.app.posture_analyzer
            analyzer._update_sitting_time(PostureStatus.NORMAL)
            clock.return_value = 110
            analyzer._update_sitting_time(PostureStatus.HEAD_TILT)
            analyzer.last_status = PostureStatus.HEAD_TILT
            clock.return_value = 115
            self.app.pause_monitoring()
            clock.return_value = 1000
            self.app.start_monitoring()
            analyzer._update_sitting_time(PostureStatus.NORMAL)
            analyzer.last_status = PostureStatus.NORMAL
            clock.return_value = 1005
            self.app.stop_monitoring()
        records = self.app.data_manager.get_session_history()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['status'], 'completed')
        self.assertEqual(records[0]['total_duration'], 20)
        self.assertEqual(records[0]['normal_duration'], 15)
        self.assertEqual(records[0]['violation_duration'], 5)

    def test_reset_while_paused_preserves_old_session_and_starts_zero_stats(self):
        self.app.start_monitoring()
        self.app.pause_monitoring()
        self.app.reset_session()
        self.app.data_manager.end_session.assert_called_once()
        self.assertEqual(self.app.current_session_id, 42)
        self.assertTrue(self.app._is_paused)
        self.assertFalse(self.app.is_running)
        self.assertEqual(self.app._create_analyzer.call_count, 2)

    def test_initial_idle_callback_cannot_cover_running_preview(self):
        self.app.is_running = True
        self.app._show_idle_preview()
        self.app._do_idle_overlay.assert_not_called()

    def test_worker_recovers_latest_frame_after_no_detection_without_tk_calls(self):
        self.app.start_monitoring()
        detector, _ = self._modules()
        first = np.full((8, 8, 3), 10, dtype=np.uint8)
        second = np.full((8, 8, 3), 20, dtype=np.uint8)
        frames = iter([first, second])
        def read():
            try:
                return next(frames)
            except StopIteration:
                self.app.stop_event.set()
                return None
        self.app.camera_preview.read_frame.side_effect = read
        detector.detect_pose.side_effect = [(False, None), (True, object())]
        detector.draw_landmarks.side_effect = lambda frame, results, **kw: frame
        self.analyzer.analyze_posture.return_value = ('normal', {'sitting_duration': 60})
        self.root.after.side_effect = AssertionError('Tk called from worker')
        self.app._video_loop()
        np.testing.assert_array_equal(self.app._latest_preview_frame, second)
        self.root.after.assert_not_called()
        detector.release.assert_called_once()
        self.app.camera_preview.close.assert_called_once()

    def test_worker_initialization_failure_releases_camera_and_restores_controls(self):
        self.app.start_monitoring()
        self._modules(detector_error=RuntimeError('missing model'))
        with self.assertLogs('ui.main_window', level='ERROR'):
            self.app._video_loop()
        self.assertFalse(self.app.is_running)
        self.assertTrue(self.app.stop_event.is_set())
        self.app.camera_preview.close.assert_called_once()
        self.root.after.assert_not_called()
        self.app._preview_refresh_loop()
        self.app.control_panel.reset_to_initial.assert_called_once()
        self.assertIn('missing model', self.app.status_panel.set_error.call_args.args[0])

    def test_muted_audio_does_not_suppress_visual_sedentary_reminder(self):
        self.app.settings.update(sedentary_minutes=1, sound_enabled=False)
        self.app.start_monitoring()
        detector, audio = self._modules()
        def read():
            if self.app._latest_preview_frame is not None:
                self.app.stop_event.set()
                return None
            return np.zeros((8, 8, 3), dtype=np.uint8)
        self.app.camera_preview.read_frame.side_effect = read
        detector.detect_pose.return_value = (True, object())
        detector.draw_landmarks.side_effect = lambda frame, results, **kw: frame
        self.analyzer.analyze_posture.return_value = ('normal', {})
        self.app._video_loop()
        self.assertEqual(self.app._ui_events.get_nowait(), 'reminder')
        audio.play_reminder.assert_called_once()

    def test_repeated_camera_read_failures_stop_and_release(self):
        self.app.start_monitoring()
        detector, _ = self._modules()
        self.app.camera_preview.read_frame.return_value = None
        self.app.stop_event = mock.Mock()
        self.app.stop_event.is_set.return_value = False
        with self.assertLogs('ui.main_window', level='ERROR'):
            self.app._video_loop()
        self.assertEqual(self.app.camera_preview.read_frame.call_count, 10)
        self.assertIn('摄像头连续读取失败', self.app._worker_error)
        detector.release.assert_called_once()
        self.app.stop_event.set.assert_called_once()


class CameraPreviewTests(unittest.TestCase):
    def test_failed_backend_releases_capture_before_fallback(self):
        broken = mock.Mock()
        broken.set.side_effect = RuntimeError('backend failure')
        healthy = mock.Mock()
        healthy.read.return_value = (True, np.zeros((8, 8, 3), dtype=np.uint8))
        preview = CameraPreview()
        with mock.patch('ui.camera_preview.cv2.VideoCapture', side_effect=[broken, healthy]):
            self.assertTrue(preview.open_camera())
        broken.release.assert_called_once()
        self.assertIs(preview.cap, healthy)
        preview.close()
        healthy.release.assert_called_once()
        self.assertIsNone(preview.current_frame)

    def test_invalid_frames_release_every_backend(self):
        captures = [mock.Mock() for _ in range(3)]
        for capture in captures:
            capture.read.return_value = (True, np.zeros((0, 0, 3), dtype=np.uint8))
        preview = CameraPreview()
        with mock.patch('ui.camera_preview.cv2.VideoCapture', side_effect=captures):
            with self.assertLogs('ui.camera_preview', level='WARNING'):
                self.assertFalse(preview.open_camera())
        for capture in captures:
            capture.release.assert_called_once()
        self.assertIsNone(preview.cap)

    def test_close_is_idempotent_even_when_release_raises(self):
        preview = CameraPreview()
        capture = mock.Mock()
        capture.release.side_effect = RuntimeError('driver closed')
        preview.cap = capture
        preview.is_running = True
        with self.assertLogs('ui.camera_preview', level='ERROR'):
            preview.close()
        preview.close()
        capture.release.assert_called_once()
        self.assertIsNone(preview.cap)
        self.assertFalse(preview.is_running)


class ControlAndHistoryTests(unittest.TestCase):
    def test_history_cannot_clear_or_delete_the_active_monitoring_session(self):
        viewer = mock.Mock()
        viewer.data_manager.get_current_session_id.return_value = 41
        with mock.patch('ui.history_viewer.messagebox.showwarning') as warning, \
                mock.patch('ui.history_viewer.messagebox.askyesno') as confirm:
            HistoryViewer._do_clear_all_sessions(viewer)
            HistoryViewer._do_delete_session(viewer, 41, mock.Mock())
        self.assertEqual(warning.call_count, 2)
        confirm.assert_not_called()
        viewer.data_manager.clear_all_sessions.assert_not_called()
        viewer.data_manager.delete_session.assert_not_called()

    def test_start_callback_failure_preserves_initial_button_state(self):
        panel = object.__new__(ControlPanel)
        panel.monitoring_state = 0
        panel.on_start = mock.Mock(return_value=False)
        panel._update_button_states = mock.Mock()
        panel._on_start_click()
        self.assertEqual(panel.monitoring_state, 0)
        panel._update_button_states.assert_not_called()

    def test_async_pause_does_not_claim_paused_before_worker_stops(self):
        panel = object.__new__(ControlPanel)
        panel.monitoring_state = 1
        panel.on_pause = mock.Mock()
        panel._on_start_click()
        panel.on_pause.assert_called_once()
        self.assertEqual(panel.monitoring_state, 1)

    def test_history_refreshes_updated_session_even_when_count_does_not_change(self):
        viewer = mock.Mock()
        viewer._sessions_cache = [{'id': 1, 'status': 'active'}]
        viewer._last_session_count = 1
        viewer.data_manager.get_session_history.return_value = [{'id': 1, 'status': 'completed'}]
        HistoryViewer._poll_data(viewer)
        viewer._render_session_cards.assert_called_once()
        viewer._load_summary.assert_called_once()
        viewer._load_trend.assert_called_once()

    def test_cancel_export_does_not_write_or_report_success(self):
        viewer = mock.Mock()
        with mock.patch('ui.history_viewer.filedialog.asksaveasfilename', return_value=''), \
                mock.patch('ui.history_viewer.messagebox.showinfo') as info:
            HistoryViewer._do_export_all_sessions(viewer)
        viewer.data_manager.export_all_sessions_to_csv.assert_not_called()
        info.assert_not_called()

    def test_export_daily_uses_selected_path_and_all_dates(self):
        viewer = mock.Mock()
        path = 'C:/exports/daily.csv'
        with mock.patch('ui.history_viewer.filedialog.asksaveasfilename', return_value=path), \
                mock.patch('ui.history_viewer.messagebox.showinfo'):
            HistoryViewer._do_export_daily_stats(viewer)
        viewer.data_manager.export_to_csv.assert_called_once_with(
            file_path=path, export_type='daily', all_time=True)


if __name__ == '__main__':
    unittest.main()
