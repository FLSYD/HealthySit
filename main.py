"""
HealthySit - 智能坐姿监测系统
基于计算机视觉的久坐行为与健康坐姿分析系统

主程序入口
"""

import sys
import os
import logging
import traceback

from src.runtime import ensure_ascii_runtime, get_app_base_dir


# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def setup_logging():
    """配置日志"""
    # 创建日志目录
    app_base_dir = get_app_base_dir()
    log_dir = os.path.join(app_base_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'healthysit.log')

    # 配置日志格式
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # 静默 matplotlib 字体管理的调试日志
    logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)
    logging.getLogger('matplotlib.ticker').setLevel(logging.WARNING)

    return logging.getLogger(__name__)


def main():
    """主函数"""
    logger = logging.getLogger(__name__)
    try:
        logger = setup_logging()
        ensure_ascii_runtime()
        logger.info("=" * 50)
        logger.info("HealthySit - 智能坐姿监测系统启动")
        logger.info("=" * 50)

        # 迁移完成后再加载界面和本地依赖，同时捕获导入阶段的启动错误。
        import tkinter as tk
        from ui.main_window import MainWindow

        # 创建主窗口
        root = tk.Tk()

        # 设置窗口图标（如果存在）
        app_base_dir = get_app_base_dir()
        icon_path = os.path.join(app_base_dir, 'assets', 'icon.ico')
        if not os.path.exists(icon_path):
            icon_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'assets',
                'icon.ico'
            )
        if os.path.exists(icon_path):
            try:
                root.iconbitmap(icon_path)
            except Exception as e:
                logger.warning(f"无法设置窗口图标: {e}")

        # 创建主窗口实例
        app = MainWindow(root)

        # 设置关闭回调
        def on_closing():
            logger.info("应用程序正在关闭...")
            app.cleanup(on_complete=root.destroy)

        root.protocol("WM_DELETE_WINDOW", on_closing)

        # 运行应用
        app.run()

    except Exception as e:
        logger.error(f"应用程序发生错误: {e}")
        logger.error(traceback.format_exc())

        # 显示错误对话框
        try:
            from tkinter import messagebox
            messagebox.showerror(
                "错误",
                f"应用程序发生错误:\n\n{str(e)}\n\n请查看日志文件获取详细信息。"
            )
        except:
            pass

        sys.exit(1)

    finally:
        logger.info("应用程序已退出")
        logging.shutdown()


if __name__ == "__main__":
    main()
