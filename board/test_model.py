#!/usr/bin/env python3
"""
🔥 YOLOv11 火焰检测 终极可视化平台 (支持 摄像头/图片/视频)
直接运行: python3 test_gui.py
"""

import sys
import cv2
import time
import os
from ultralytics import YOLO

# 智能导入 Qt 库 (支持 PySide6 或 PyQt5)
try:
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QFileDialog,
        QFrame,
    )
    from PySide6.QtGui import QImage, QPixmap, QFont
    from PySide6.QtCore import QThread, Signal, Qt
except ImportError:
    from PyQt5.QtWidgets import (
        QApplication,
        QLabel,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QFileDialog,
        QFrame,
    )
    from PyQt5.QtGui import QImage, QPixmap, QFont
    from PyQt5.QtCore import QThread, pyqtSignal as Signal, Qt

# 你的模型路径
model_path = "/home/value/Keshe/fire/board/runs/detect/fire_detect/weights/best.pt"


class YOLOThread(QThread):
    """通用后台推理线程：处理摄像头、视频、单张图片"""

    frame_signal = Signal(QImage)
    info_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.source_type = None  # 'camera', 'image', 'video'
        self.source_path = None

        # 加载模型
        if os.path.exists(model_path):
            self.model = YOLO(model_path)
        else:
            self.model = None

    def set_source(self, source_type, path=0):
        """设置当前要检测的数据源"""
        self.source_type = source_type
        self.source_path = path

    def process_frame(self, frame, start_time=None):
        """核心 YOLO 推理与画图逻辑"""
        results = self.model(frame, conf=0.35, imgsz=480, verbose=False)
        annotated = results[0].plot()

        # 计算 FPS
        if start_time:
            fps = 1.0 / (time.time() - start_time)
            cv2.putText(
                annotated,
                f"FPS: {fps:.1f}",
                (10, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 0),
                2,
            )

        count = len(results[0].boxes)
        cv2.putText(
            annotated,
            f"Detected: {count}",
            (10, 75 if start_time else 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2,
        )

        # 转换为 Qt 图像
        rgb_img = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_img.shape
        qt_img = QImage(rgb_img.data, w, h, ch * w, QImage.Format_RGB888)
        self.frame_signal.emit(qt_img)

    def run(self):
        if self.model is None:
            self.info_signal.emit("❌ 模型未找到，请检查路径！")
            return

        self.running = True

        if self.source_type == "image":
            # === 图片处理模式 ===
            self.info_signal.emit(
                f"🖼️ 正在检测图片: {os.path.basename(self.source_path)}"
            )
            frame = cv2.imread(self.source_path)
            if frame is not None:
                self.process_frame(frame)
            self.running = False  # 图片只需处理一次

        else:
            # === 摄像头 / 视频处理模式 ===
            cap = cv2.VideoCapture(self.source_path)

            if self.source_type == "camera":
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.info_signal.emit("📷 摄像头实时检测中...")
                delay = 10  # 尽量快
            else:
                self.info_signal.emit(
                    f"🎞️ 正在播放视频: {os.path.basename(self.source_path)}"
                )
                fps = cap.get(cv2.CAP_PROP_FPS)
                delay = int(1000 / fps) if fps > 0 else 30  # 按视频原始帧率播放

            while self.running:
                start_time = time.time()
                ret, frame = cap.read()

                if not ret:
                    if self.source_type == "video":
                        self.info_signal.emit("✅ 视频播放结束。")
                    else:
                        self.info_signal.emit("❌ 摄像头掉线。")
                    break

                self.process_frame(frame, start_time)

                # 睡眠以控制帧率并让出 CPU 给主界面渲染
                QThread.msleep(delay)

            cap.release()

    def stop(self):
        """安全停止线程"""
        self.running = False
        self.wait()


class MainWindow(QMainWindow):
    """主程序界面"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🔥 YOLOv11 火焰烟雾智能监测系统")
        self.resize(1000, 700)
        self.current_qimage = None  # 缓存当前画面，用于调整窗口大小时重新缩放

        # --- 初始化 UI ---
        self.init_ui()

        # --- 初始化后台线程 ---
        self.thread = YOLOThread()
        self.thread.frame_signal.connect(self.update_frame)
        self.thread.info_signal.connect(self.update_status)

    def init_ui(self):
        # 主挂载点
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- 左侧控制面板 ---
        control_panel = QFrame()
        control_panel.setFixedWidth(200)
        control_panel.setStyleSheet(
            "background-color: #2b2b2b; color: white; border-radius: 10px;"
        )
        control_layout = QVBoxLayout(control_panel)

        title = QLabel("功能控制台")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        control_layout.addWidget(title)
        control_layout.addSpacing(20)

        # 按钮样式
        btn_style = """
            QPushButton {
                background-color: #4CAF50; color: white; border: none; 
                padding: 12px; border-radius: 6px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:pressed { background-color: #388E3C; }
        """

        self.btn_camera = QPushButton("📷 开启摄像头")
        self.btn_camera.setStyleSheet(btn_style)
        self.btn_camera.clicked.connect(self.start_camera)

        self.btn_image = QPushButton("🖼️ 选择图片检测")
        self.btn_image.setStyleSheet(
            btn_style.replace("#4CAF50", "#2196F3").replace("#45a049", "#1E88E5")
        )
        self.btn_image.clicked.connect(self.start_image)

        self.btn_video = QPushButton("🎞️ 选择视频检测")
        self.btn_video.setStyleSheet(
            btn_style.replace("#4CAF50", "#FF9800").replace("#45a049", "#F57C00")
        )
        self.btn_video.clicked.connect(self.start_video)

        self.btn_stop = QPushButton("🛑 停止当前任务")
        self.btn_stop.setStyleSheet(
            btn_style.replace("#4CAF50", "#F44336").replace("#45a049", "#E53935")
        )
        self.btn_stop.clicked.connect(self.stop_current)

        control_layout.addWidget(self.btn_camera)
        control_layout.addSpacing(10)
        control_layout.addWidget(self.btn_image)
        control_layout.addSpacing(10)
        control_layout.addWidget(self.btn_video)
        control_layout.addStretch()
        control_layout.addWidget(self.btn_stop)

        # --- 右侧显示面板 ---
        display_panel = QWidget()
        display_layout = QVBoxLayout(display_panel)

        self.video_label = QLabel("请在左侧选择检测模式...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet(
            "background-color: #1e1e1e; color: #888888; font-size: 24px; border-radius: 10px;"
        )

        self.status_label = QLabel("系统就绪")
        self.status_label.setStyleSheet(
            "color: #333; font-size: 14px; font-weight: bold;"
        )
        self.status_label.setFixedHeight(30)

        display_layout.addWidget(self.video_label)
        display_layout.addWidget(self.status_label)

        # 组装整体布局
        main_layout.addWidget(control_panel)
        main_layout.addWidget(display_panel)

    def start_camera(self):
        self.thread.stop()
        self.thread.set_source("camera", 0)
        self.thread.start()

    def start_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择要检测的图片", "", "图片文件 (*.jpg *.jpeg *.png *.bmp)"
        )
        if file_path:
            self.thread.stop()
            self.thread.set_source("image", file_path)
            self.thread.start()

    def start_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择要检测的视频", "", "视频文件 (*.mp4 *.avi *.mkv *.mov)"
        )
        if file_path:
            self.thread.stop()
            self.thread.set_source("video", file_path)
            self.thread.start()

    def stop_current(self):
        self.thread.stop()
        self.video_label.clear()
        self.video_label.setText("已停止检测。")
        self.status_label.setText("系统空闲")

    def update_frame(self, qt_img):
        """刷新画面"""
        self.current_qimage = qt_img
        scaled_img = qt_img.scaled(
            self.video_label.width(),
            self.video_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(QPixmap.fromImage(scaled_img))

    def update_status(self, text):
        """刷新底部状态栏"""
        self.status_label.setText(text)

    def resizeEvent(self, event):
        """窗口大小改变时，保证图片按比例自适应且不失真"""
        if self.current_qimage is not None:
            self.update_frame(self.current_qimage)
        super().resizeEvent(event)

    def closeEvent(self, event):
        """退出程序时安全释放线程"""
        self.thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
