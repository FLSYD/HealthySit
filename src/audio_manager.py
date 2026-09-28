"""
音频提醒管理模块
使用 Windows 系统提示音
"""

import os
import logging
import time

logger = logging.getLogger(__name__)


class AudioManager:
    """音频管理器"""

    def __init__(self, sound_enabled: bool = True):
        """
        初始化音频管理器

        Args:
            sound_enabled: 是否启用声音
        """
        self.sound_enabled = sound_enabled
        self.last_alert_time = None
        self.alert_cooldown = 5  # 警报冷却时间（秒）

        logger.info(f"音频管理器初始化完成，启用状态: {sound_enabled}")

    def set_enabled(self, enabled: bool):
        """动态启用/禁用声音"""
        self.sound_enabled = enabled
        logger.info(f"声音提醒已{'启用' if enabled else '禁用'}")

    def play_alert(self, sound_type: str = 'default') -> bool:
        """
        播放提醒音

        Args:
            sound_type: 声音类型 ('default', 'warning', 'reminder')

        Returns:
            是否成功播放
        """
        if not self.sound_enabled:
            return False

        current_time = time.monotonic()
        if (self.last_alert_time is not None
                and current_time - self.last_alert_time < self.alert_cooldown):
            return False

        try:
            if os.name == 'nt':  # Windows
                played = self._play_windows()
            else:  # Linux
                played = self._play_linux()
            if played:
                self.last_alert_time = current_time
            return played
        except Exception as e:
            logger.warning(f"播放声音失败: {e}")
            return False

    def _play_windows(self) -> bool:
        """Windows 平台播放系统提示音"""
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return True
        except Exception as e:
            logger.warning(f"winsound 播放失败: {e}")
            return False

    def _play_linux(self) -> bool:
        """Linux 平台播放声音"""
        try:
            import subprocess
            subprocess.run(
                ['paplay',
                 '/usr/share/sounds/gnome/default/alerts/dialog-warning.ogg'],
                capture_output=True, timeout=1, check=True
            )
            return True
        except Exception:
            return False

    def play_reminder(self) -> bool:
        """播放久坐提醒音"""
        return self.play_alert('reminder')

    def play_warning(self) -> bool:
        """播放警告音"""
        return self.play_alert('warning')


def create_audio_manager(sound_enabled: bool = True) -> AudioManager:
    """创建音频管理器的工厂函数"""
    return AudioManager(sound_enabled=sound_enabled)
