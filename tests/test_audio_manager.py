"""模拟播放后端验证冷却时间，测试不会发声。"""

import subprocess
import unittest
from unittest import mock

from src.audio_manager import AudioManager


class AudioManagerTests(unittest.TestCase):
    def test_first_alert_plays_and_cooldown_uses_monotonic_time(self):
        manager = AudioManager()
        with mock.patch('src.audio_manager.os.name', 'nt'):
            with mock.patch.object(manager, '_play_windows', return_value=True) as play:
                with mock.patch('src.audio_manager.time.monotonic', return_value=0) as now:
                    self.assertTrue(manager.play_alert())
                    now.return_value = 4.9
                    self.assertFalse(manager.play_warning())
                    now.return_value = 5
                    self.assertTrue(manager.play_reminder())
                self.assertEqual(play.call_count, 2)

    def test_failed_playback_can_be_retried_without_cooldown(self):
        manager = AudioManager()
        with mock.patch('src.audio_manager.os.name', 'nt'):
            with mock.patch.object(manager, '_play_windows', side_effect=[False, True]):
                with mock.patch('src.audio_manager.time.monotonic', return_value=10):
                    self.assertFalse(manager.play_alert())
                    self.assertTrue(manager.play_alert())

    def test_disabled_sound_does_not_call_backend(self):
        manager = AudioManager(sound_enabled=False)
        with mock.patch.object(manager, '_play_windows') as play:
            self.assertFalse(manager.play_alert())
            play.assert_not_called()

    def test_linux_nonzero_process_exit_is_not_reported_as_success(self):
        manager = AudioManager()

        def run(*args, **kwargs):
            self.assertTrue(kwargs.get('check'))
            raise subprocess.CalledProcessError(1, 'paplay')

        with mock.patch('subprocess.run', side_effect=run):
            self.assertFalse(manager._play_linux())


if __name__ == '__main__':
    unittest.main()
