"""
摄像头预览组件
负责视频流显示和图像处理
"""

import cv2
import numpy as np
from PIL import Image, ImageTk, ImageDraw, ImageFont
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class CameraPreview:
    """摄像头预览组件"""

    def __init__(self, canvas_width: int = 640, canvas_height: int = 480):
        """初始化摄像头预览"""
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height

        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.preview_state = "idle"  # idle, running, paused, stopped
        self.camera_backend = ""

        self.current_frame = None
        self.display_image: Optional[ImageTk.PhotoImage] = None

        logger.info(f"摄像头预览组件初始化完成，尺寸: {canvas_width}x{canvas_height}")

    def open_camera(self, camera_index: int = 0) -> bool:
        """打开摄像头，自动尝试多个后端以兼容打包环境"""
        self.close()

        backend_candidates = [
            ("CAP_DSHOW", cv2.CAP_DSHOW),
            ("CAP_MSMF", cv2.CAP_MSMF),
            ("CAP_ANY", cv2.CAP_ANY),
        ]

        for backend_name, backend in backend_candidates:
            cap = None
            try:
                logger.info(f"尝试打开摄像头 {camera_index}，后端: {backend_name}")
                cap = cv2.VideoCapture(camera_index, backend)

                if not cap or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    logger.warning(f"摄像头后端 {backend_name} 打开失败")
                    continue

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.canvas_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.canvas_height)

                ret, test_frame = cap.read()
                if not ret or test_frame is None or getattr(test_frame, 'size', 0) == 0:
                    cap.release()
                    logger.warning(f"摄像头后端 {backend_name} 可打开但无法读取有效画面")
                    continue

                actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                self.cap = cap
                self.current_frame = test_frame
                self.camera_backend = backend_name
                logger.info(
                    f"摄像头已打开，后端: {backend_name}，实际分辨率: {actual_width}x{actual_height}"
                )

                self.is_running = True
                return True

            except Exception as e:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        logger.exception("释放初始化失败的摄像头后端失败")
                logger.warning(f"使用后端 {backend_name} 打开摄像头失败: {e}")

        logger.error(f"无法打开摄像头 {camera_index}，所有后端均失败")
        return False

    def read_frame(self) -> Optional[np.ndarray]:
        """读取一帧"""
        if self.cap is None or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if ret and frame is not None and getattr(frame, 'size', 0) > 0:
            self.current_frame = frame
            return frame

        logger.warning(f"读取摄像头画面失败，当前后端: {self.camera_backend or 'unknown'}")
        return None

    def get_frame(self) -> Optional[np.ndarray]:
        """获取当前帧"""
        return self.current_frame

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """处理视频帧"""
        if frame is None:
            return self._create_placeholder()

        h, w = frame.shape[:2]
        if w != self.canvas_width or h != self.canvas_height:
            frame = cv2.resize(frame, (self.canvas_width, self.canvas_height))

        return frame

    def _create_placeholder(self) -> np.ndarray:
        """创建占位图像"""
        frame = np.ones((self.canvas_height, self.canvas_width, 3), dtype=np.uint8) * 240

        text = "摄像头未连接"
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 1, 2)[0]
        text_x = (self.canvas_width - text_size[0]) // 2
        text_y = (self.canvas_height + text_size[1]) // 2
        cv2.putText(frame, text, (text_x, text_y), font, 1, (100, 100, 100), 2)

        return frame

    def _create_idle_placeholder(self) -> np.ndarray:
        """创建初始状态占位图像"""
        import cv2
        frame = np.ones((self.canvas_height, self.canvas_width, 3), dtype=np.uint8) * 50

        # 绘制摄像头图标（使用 cv2）
        icon_x, icon_y = self.canvas_width // 2, self.canvas_height // 2 - 80
        cv2.circle(frame, (icon_x, icon_y), 55, (80, 80, 80), -1)
        cv2.circle(frame, (icon_x, icon_y), 55, (120, 120, 120), 3)
        cv2.circle(frame, (icon_x, icon_y), 35, (60, 60, 60), -1)
        cv2.circle(frame, (icon_x, icon_y), 35, (100, 100, 100), 2)
        cv2.ellipse(frame, (icon_x - 12, icon_y - 17), (8, 6), 0, 0, 360, (120, 120, 120), -1)
        cv2.rectangle(frame, (icon_x - 8, icon_y + 45), (icon_x + 8, icon_y + 70), (100, 100, 100), -1)
        cv2.rectangle(frame, (icon_x - 25, icon_y + 65), (icon_x + 25, icon_y + 75), (90, 90, 90), -1)

        # 使用 PIL 绘制文字
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_frame)
        draw = ImageDraw.Draw(pil_img)

        # 尝试加载中文字体
        try:
            font_title = ImageFont.truetype("msyh.ttc", 36)
            font_sub = ImageFont.truetype("msyh.ttc", 18)
        except Exception:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        def center_x(text: str, font: ImageFont.FreeTypeFont, canvas_w: int) -> int:
            """计算文字水平居中的 x 坐标"""
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_w = bbox[2] - bbox[0]
            except Exception:
                text_w = len(text) * (font.size if hasattr(font, 'size') else 12)
            return (canvas_w - text_w) // 2

        # 绘制标题
        title = "等待开始监测"
        draw.text((center_x(title, font_title, self.canvas_width), icon_y + 90),
                  title, font=font_title, fill=(200, 200, 200))

        # 绘制副标题
        subtitle = "点击「开始监测」按钮启动"
        draw.text((center_x(subtitle, font_sub, self.canvas_width), icon_y + 140),
                  subtitle, font=font_sub, fill=(150, 150, 150))

        result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return result

    def _create_paused_placeholder(self) -> np.ndarray:
        """创建暂停状态占位图像 - 显示实时画面快照"""
        # 尝试读取当前帧作为快照
        frame = self.current_frame
        if frame is None:
            frame = np.ones((self.canvas_height, self.canvas_width, 3), dtype=np.uint8) * 40

        # 调整大小
        if frame.shape[1] != self.canvas_width or frame.shape[0] != self.canvas_height:
            frame = cv2.resize(frame, (self.canvas_width, self.canvas_height))

        # 添加半透明暗色遮罩
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (self.canvas_width, self.canvas_height),
                     (30, 30, 30), -1)
        frame = cv2.addWeighted(frame, 0.6, overlay, 0.4, 0)

        try:
            font_title = ImageFont.truetype("msyh.ttc", 32)
            font_sub = ImageFont.truetype("msyh.ttc", 16)
        except Exception:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        # 绘制暂停图标（使用 cv2 更可靠）
        icon_x, icon_y = self.canvas_width // 2, self.canvas_height // 2 - 60
        cv2.circle(frame, (icon_x, icon_y), 50, (230, 126, 34), -1)
        cv2.circle(frame, (icon_x, icon_y), 50, (255, 200, 100), 3)
        cv2.rectangle(frame, (icon_x - 17, icon_y - 20), (icon_x - 5, icon_y + 20), (255, 255, 255), -1)
        cv2.rectangle(frame, (icon_x + 5, icon_y - 20), (icon_x + 17, icon_y + 20), (255, 255, 255), -1)

        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        # 绘制标题（不使用 textlength，避免默认字体不支持）
        title = "监测已暂停"
        title_x = (self.canvas_width - 200) // 2
        draw.text((title_x, icon_y + 60), title, font=font_title, fill=(255, 200, 100))

        # 绘制副标题
        subtitle = "点击「继续监测」按钮恢复"
        sub_x = (self.canvas_width - 280) // 2
        draw.text((sub_x, icon_y + 100), subtitle, font=font_sub, fill=(150, 150, 150))

        result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return result

    def _create_stopped_placeholder(self) -> np.ndarray:
        """创建结束状态占位图像 - 与初始状态一致"""
        return self._create_idle_placeholder()

    def set_preview_state(self, state: str):
        """设置预览状态"""
        self.preview_state = state
        logger.info(f"预览状态已切换: {state}")

    def get_idle_frame(self) -> np.ndarray:
        """获取空闲状态的画面"""
        return self._create_idle_placeholder()

    def get_paused_frame(self) -> np.ndarray:
        """获取暂停状态的画面"""
        return self._create_paused_placeholder()

    def get_stopped_frame(self) -> np.ndarray:
        """获取结束状态的画面"""
        return self._create_stopped_placeholder()

    def convert_to_tkinter(self, frame: np.ndarray) -> Optional[ImageTk.PhotoImage]:
        """将 OpenCV 图像转换为 Tkinter 图像"""
        try:
            if frame is None:
                frame = self._create_placeholder()

            # BGR -> RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # 转换为 PIL Image
            pil_image = Image.fromarray(rgb_frame)

            # 转换为 Tkinter PhotoImage
            self.display_image = ImageTk.PhotoImage(pil_image)

            return self.display_image

        except Exception as e:
            logger.error(f"图像转换失败: {e}")
            return None

    def close(self):
        """关闭摄像头"""
        cap, self.cap = self.cap, None
        self.is_running = False
        self.current_frame = None
        self.camera_backend = ""
        if cap is not None:
            try:
                cap.release()
            except Exception:
                logger.exception("释放摄像头失败")
            logger.info("摄像头已关闭")

    def is_opened(self) -> bool:
        """检查摄像头是否打开"""
        return self.cap is not None and self.cap.isOpened()

    def get_fps(self) -> float:
        """获取帧率"""
        if self.cap is not None and self.cap.isOpened():
            return self.cap.get(cv2.CAP_PROP_FPS)
        return 0.0

    def release(self):
        """释放资源"""
        self.close()


def create_camera_preview(width: int = 640, height: int = 480) -> CameraPreview:
    """创建摄像头预览组件的工厂函数"""
    return CameraPreview(canvas_width=width, canvas_height=height)
