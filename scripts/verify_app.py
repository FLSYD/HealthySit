"""真实 Tk 界面与 MediaPipe 模型验收；不访问摄像头或用户数据库。"""

import argparse
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def verify_model():
    import numpy as np
    from src.pose_detector import PoseDetector

    detector = PoseDetector(static_image_mode=True)
    try:
        detected, result = detector.detect_pose(np.zeros((480, 640, 3), dtype=np.uint8))
        if detected or result.pose_landmarks is not None:
            raise AssertionError('空白测试帧不应识别出人体')
    finally:
        detector.release()
    print('PASS: MediaPipe model, blank-frame inference, and resource cleanup')


def verify_gui():
    import tkinter as tk
    from src.data_manager import DataManager
    from ui.main_window import MainWindow

    with tempfile.TemporaryDirectory(prefix='HealthySit-gui-check-') as temporary:
        root = tk.Tk()
        root.withdraw()
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        closed = []
        try:
            database = str(Path(temporary) / 'test.db')
            with patch('ui.main_window.DataManager', side_effect=lambda: DataManager(database)):
                app = MainWindow(root)
            root.update()
            if 'HealthySit' not in root.title():
                raise AssertionError('主窗口未完成初始化')
            app.cleanup(on_complete=lambda: closed.append(True))
            deadline = time.monotonic() + 10
            while not closed and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            if not closed:
                raise AssertionError('主窗口资源清理超时')
            if errors:
                raise AssertionError(f'Tk 回调发生异常: {errors}')
        finally:
            root.destroy()
    print('PASS: Tk window, temporary database, and normal shutdown')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', action='store_true', help='加载真实模型并推理合成帧')
    parser.add_argument('--gui', action='store_true', help='初始化真实 Tk 窗口并正常关闭')
    args = parser.parse_args()
    if not (args.model or args.gui):
        parser.error('请指定 --model 和/或 --gui')
    if args.model:
        verify_model()
    if args.gui:
        verify_gui()


if __name__ == '__main__':
    main()
