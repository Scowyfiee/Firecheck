#!/usr/bin/env python3
"""
视频AI智能识别及预警管理系统 - 边缘设备火焰检测模块
YOLOv11火焰识别 + 与Web服务端通信
部署目标: Orange Pi 5 (RK3588S) / 通用Linux设备
"""

import os
import sys
import time
import json
import uuid
import base64
import hashlib
import logging
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from io import BytesIO
from collections import deque

import cv2
import numpy as np
import requests
import websockets
from ultralytics import YOLO

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("flame_detect.log")]
)
logger = logging.getLogger("FlameDetector")


class Config:
    def __init__(self, config_file="flame_config.json"):
        self._cfg = {
            "device_mac": self._get_mac(),
            "server_url": "http://127.0.0.1:5000",
            "camera_url": 0,
            "model_path": os.path.join(os.path.dirname(__file__), "models", "fire_yolov11.pt"),
            "use_npu": False,
            "rknn_model_path": os.path.join(os.path.dirname(__file__), "models", "fire_yolov11.rknn"),
            "conf_threshold": 0.35,
            "iou_threshold": 0.45,
            "detect_classes": [0],
            "image_size": 640,
            "video_duration": 5,
            "heartbeat_interval": 60,
            "save_dir": "alarm_data",
            "longitude": "106.551556",
            "latitude": "29.563009",
            "location": "重庆理工大学",
            "camera_id": 1,
            "device_id": 1,
            "area_id": 1,
        }
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                self._cfg.update(json.load(f))
        Path(self._cfg["save_dir"]).mkdir(parents=True, exist_ok=True)

    def __getattr__(self, name):
        if name in self._cfg:
            return self._cfg[name]
        raise AttributeError(f"Config has no attribute: {name}")

    @staticmethod
    def _get_mac():
        try:
            with open("/sys/class/net/eth0/address") as f:
                return f.read().strip().replace(":", "").upper()
        except Exception:
            import uuid as _uuid
            return str(_uuid.getnode()).zfill(12)


class FlameDetector:
    def __init__(self, config: Config):
        self.cfg = config
        self.model = None
        self.cap = None
        self.running = False
        self.alarm_cooldown = {}
        self.cooldown_seconds = 15
        self.frame_buffer = deque(maxlen=config.video_duration * 30)
        self.video_writer = None
        self.recording = False
        self.record_start_time = 0
        self.detection_history = deque(maxlen=10)
        self.lock = threading.Lock()
        self._latest_frame = None
        self._frame_lock = threading.Lock()

    def load_model(self):
        model_path = self.cfg.model_path
        if not os.path.isabs(model_path):
            board_dir = os.path.dirname(os.path.abspath(__file__))
            resolved_path = os.path.abspath(os.path.join(board_dir, model_path))
        else:
            resolved_path = model_path

        logger.info(f"Loading YOLOv11 model: {resolved_path}")
        if self.cfg.use_npu and os.path.exists(self.cfg.rknn_model_path):
            self._load_rknn_model(resolved_path)
        elif os.path.exists(resolved_path):
            self.model = YOLO(resolved_path)
            self.cfg.model_path = resolved_path
        else:
            logger.warning(f"Fire model not found at {resolved_path}, downloading YOLOv11n base model")
            self.model = YOLO("yolo11n.pt")
        
        if hasattr(self, "model") and self.model is not None:
            logger.info(f"Model loaded successfully. Classes detected: {self.model.names}")
        else:
            logger.info("Model loaded")

    def _load_rknn_model(self, resolved_path):
        try:
            from rknnlite.api import RKNNLite
            self.rknn = RKNNLite()
            self.rknn.load_rknn(self.cfg.rknn_model_path)
            ret = self.rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0)
            if ret != 0:
                raise RuntimeError("RKNN runtime init failed")
            logger.info("RKNN model loaded on NPU")
        except ImportError:
            logger.warning("rknnlite not available, falling back to PyTorch")
            self.model = YOLO(resolved_path) if os.path.exists(resolved_path) else YOLO("yolo11n.pt")
        except Exception as e:
            logger.error(f"RKNN init failed: {e}, falling back to PyTorch")
            self.model = YOLO(resolved_path) if os.path.exists(resolved_path) else YOLO("yolo11n.pt")

    def open_camera(self):
        cam = self.cfg.camera_url
        try:
            if isinstance(cam, int) or (isinstance(cam, str) and cam.isdigit()):
                self.cap = cv2.VideoCapture(int(cam))
            else:
                self.cap = cv2.VideoCapture(cam)
            if not self.cap.isOpened():
                raise RuntimeError(f"Cannot open camera: {cam}")
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.cap.set(cv2.CAP_PROP_FPS, 25)
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25
            self.is_mock = False
            logger.info(f"Camera opened, FPS: {self.fps}")
        except Exception as e:
            logger.warning(f"Failed to open camera ({cam}): {e}. Falling back to mock camera stream simulation.")
            self.cap = None
            self.is_mock = True
            self.fps = 25

    def detect_frame(self, frame):
        if self.cfg.use_npu and hasattr(self, "rknn"):
            return self._detect_rknn(frame)
        results = self.model(frame, conf=self.cfg.conf_threshold, iou=self.cfg.iou_threshold,
                             classes=self.cfg.detect_classes or None, imgsz=480, verbose=False, device=0)
        return results[0] if results else None

    def _detect_rknn(self, frame):
        img = cv2.resize(frame, (self.cfg.image_size, self.cfg.image_size))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = np.expand_dims(img, axis=0).astype(np.float32)
        outputs = self.rknn.inference(inputs=[img])
        return outputs

    def has_flame(self, result):
        if result is None:
            return False
        if hasattr(result, "boxes") and result.boxes is not None and len(result.boxes) > 0:
            return True
        return False

    def get_detection_info(self, result, frame_shape):
        if not hasattr(result, "boxes") or result.boxes is None:
            return []
        detections = []
        h, w = frame_shape[:2]
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            cls_name = self.model.names.get(cls_id, f"class_{cls_id}")
            detections.append({
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "confidence": round(conf, 4),
                "class_id": cls_id,
                "class_name": cls_name,
                "center": [int((x1 + x2) / 2), int((y1 + y2) / 2)],
            })
        return detections

    def save_alarm_image(self, frame, detections, event_id):
        img = frame.copy()
        h, w = img.shape[:2]
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
            label = f"{det['class_name']}: {det['confidence']:.2f}"
            cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{event_id}_{ts}.jpg"
        filepath = os.path.join(self.cfg.save_dir, filename)
        cv2.imwrite(filepath, img)
        logger.info(f"Alarm image saved: {filepath}")
        return filepath, filename

    def start_recording(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"alarm_{ts}.mp4"
        filepath = os.path.join(self.cfg.save_dir, filename)
        
        # Try avc1 first for HTML5 compatibility, fallback to mp4v if unavailable
        try:
            fourcc = cv2.VideoWriter_fourcc(*"avc1")
            self.video_writer = cv2.VideoWriter(filepath, fourcc, 20.0, (1280, 720))
            if not self.video_writer.isOpened():
                raise Exception("avc1 writer not opened")
        except Exception:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.video_writer = cv2.VideoWriter(filepath, fourcc, 20.0, (1280, 720))
            
        self.recording = True
        self.record_start_time = time.time()
        self._recorded_frames_filepath = filepath
        self._recorded_frames_filename = filename
        for f in self.frame_buffer:
            self.video_writer.write(f)
        self.frame_buffer.clear()
        logger.info(f"Recording started: {filepath}")

    def stop_recording(self):
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        self.recording = False
        elapsed = time.time() - self.record_start_time
        logger.info(f"Recording stopped, duration: {elapsed:.1f}s")
        
        # Transcode using ffmpeg if it's not HTML5 compatible or to guarantee playability
        filepath = getattr(self, "_recorded_frames_filepath", "")
        if filepath and os.path.exists(filepath):
            temp_path = filepath + ".tmp.mp4"
            try:
                cmd = ["ffmpeg", "-y", "-i", filepath, "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "baseline", "-level", "3.0", temp_path]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
                if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                    os.replace(temp_path, filepath)
                    logger.info("Video transcoded successfully to H.264 via ffmpeg")
            except Exception as e:
                logger.warning(f"Video transcoding skipped or ffmpeg not available: {e}")
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except: pass
                    
        return getattr(self, "_recorded_frames_filepath", ""), getattr(self, "_recorded_frames_filename", "")

    def send_alarm_to_server(self, image_path, image_filename, video_path, video_filename, detections):
        try:
            files = {}
            with open(image_path, "rb") as f:
                files["picture"] = (image_filename, f.read(), "image/jpeg")
            if os.path.exists(video_path):
                with open(video_path, "rb") as f:
                    files["video"] = (video_filename, f.read(), "video/mp4")

            data = {
                "device_mac": self.cfg.device_mac,
                "device_id": self.cfg.device_id,
                "camera_id": self.cfg.camera_id,
                "area_id": self.cfg.area_id,
                "longitude": self.cfg.longitude,
                "latitude": self.cfg.latitude,
                "location": self.cfg.location,
                "detections": json.dumps(detections),
                "timestamp": datetime.now().isoformat(),
            }
            url = f"{self.cfg.server_url}/api/alarm"
            resp = requests.post(url, data=data, files=files, timeout=30)
            if resp.status_code == 200:
                logger.info(f"Alarm sent to server: {resp.json()}")
                return True
            else:
                logger.error(f"Server returned {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send alarm: {e}")
            return False

    def should_trigger_alarm(self, detections):
        if not detections:
            return False
        now = time.time()
        for d in detections:
            key = str(d["class_id"])
            if key not in self.alarm_cooldown or now - self.alarm_cooldown[key] > self.cooldown_seconds:
                self.alarm_cooldown[key] = now
                return True
        return False

    def process_alarm(self, frame, result):
        detections = self.get_detection_info(result, frame.shape)
        if not detections:
            return
        if not self.should_trigger_alarm(detections):
            return
        event_id = f"FLAME_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"
        logger.info(f"FLAME DETECTED! Event: {event_id}, Objects: {len(detections)}")

        image_path, image_filename = self.save_alarm_image(frame, detections, event_id)

        self.start_recording()
        time.sleep(self.cfg.video_duration)
        video_path, video_filename = self.stop_recording()

        success = self.send_alarm_to_server(image_path, image_filename, video_path, video_filename, detections)
        if success:
            logger.info(f"Alarm event {event_id} processed")
        else:
            logger.warning(f"Alarm event {event_id} saved locally but not sent to server")

    def register_device(self):
        try:
            url = f"{self.cfg.server_url}/api/device/heartbeat"
            data = {
                "device_mac": self.cfg.device_mac,
                "device_id": self.cfg.device_id,
                "camera_id": self.cfg.camera_id,
                "timestamp": datetime.now().isoformat(),
                "status": "online",
                "model_info": getattr(self.cfg, "model_info", "YOLOv11"),
                "cpu_usage": self._get_cpu_usage(),
                "memory_usage": self._get_memory_usage(),
            }
            resp = requests.post(url, json=data, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Heartbeat failed: {e}")
            return False

    @staticmethod
    def _get_cpu_usage():
        try:
            return float(os.popen("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'").read().strip().replace(",", ".") or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _get_memory_usage():
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            total = int(lines[0].split()[1])
            available = int(lines[2].split()[1])
            return round((1 - available / total) * 100, 1)
        except Exception:
            return 0.0

    def heartbeat_loop(self):
        while self.running:
            self.register_device()
            time.sleep(self.cfg.heartbeat_interval)

    def _websocket_server(self, port=9999):
        import asyncio
        import websockets

        async def handler(ws):
            logger.info(f"[WS] New connection from {ws.remote_address}")
            try:
                while self.running:
                    with self._frame_lock:
                        f = self._latest_frame.copy() if self._latest_frame is not None else None
                    
                    if f is not None:
                        _, jpg = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 50])
                        await ws.send(jpg.tobytes())
                    
                    await asyncio.sleep(0.04)
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"[WS] Connection closed: {ws.remote_address}")
            except Exception as e:
                logger.error(f"[WS] Handler error: {e}")

        async def serve():
            try:
                async with websockets.serve(handler, "0.0.0.0", port, ping_interval=20, ping_timeout=20):
                    logger.info(f"[WS] Server successfully bound to port {port}")
                    await asyncio.Future() # Keep alive forever
            except Exception as e:
                logger.error(f"[WS] Server failed to start: {e}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(serve())

    def set_latest_frame(self, frame):
        with self._frame_lock:
            self._latest_frame = frame

    def run(self):
        self.load_model()
        self.open_camera()
        self.register_device()

        self.running = True
        
        # Start Heartbeat
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()
        
        # Start WebSocket Server
        threading.Thread(target=self._websocket_server, args=(9999,), daemon=True).start()

        logger.info("Flame detection started. Main loop running.")
        frame_count = 0
        last_print = 0

        try:
            while self.running:
                if getattr(self, "is_mock", False):
                    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                    for x in range(0, 1280, 80):
                        cv2.line(frame, (x, 0), (x, 720), (15, 23, 42), 1)
                    for y in range(0, 720, 80):
                        cv2.line(frame, (0, y), (1280, y), (15, 23, 42), 1)
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    cv2.putText(frame, "CAMERA SIMULATION ACTIVE", (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (6, 182, 212), 2)
                    cv2.putText(frame, f"TIMESTAMP: {ts}", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (148, 163, 184), 1)
                    cv2.putText(frame, f"LOCATION: {self.cfg.location}", (40, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (148, 163, 184), 1)
                    
                    angle = (time.time() * 2) % (2 * np.pi)
                    cx = int(640 + 200 * np.cos(angle))
                    cy = int(360 + 100 * np.sin(angle))
                    cv2.circle(frame, (cx, cy), 15, (16, 185, 129), -1)
                    cv2.putText(frame, "SIMULATED TARGET", (cx - 60, cy - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (16, 185, 129), 1)
                    
                    ret = True
                    time.sleep(1.0 / self.fps)
                else:
                    ret, frame = self.cap.read()
                    if not ret:
                        # For local video testing, reset frame pointer to 0 and loop
                        if self.cap is not None:
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ret, frame = self.cap.read()
                        if not ret:
                            time.sleep(0.01)
                            continue

                frame_count += 1

                if getattr(self, "is_mock", False):
                    result = None
                    detections = []
                else:
                    result = self.detect_frame(frame)
                    detections = self.get_detection_info(result, frame.shape) if result else []
                
                annotated = frame.copy()

                for det in detections:
                    x1, y1, x2, y2 = det["bbox"]
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv2.putText(annotated, f"{det['class_name']} {det['confidence']:.2f}",
                                (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

                self.set_latest_frame(annotated)

                if detections:
                    if time.time() - last_print > 2:
                        for det in detections:
                            print(f"  🔥 {det['class_name']} conf={det['confidence']:.2f}")
                        last_print = time.time()
                    if not self.recording:
                        threading.Thread(
                            target=self.process_alarm,
                            args=(frame.copy(), result),
                            daemon=True
                        ).start()

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.recording:
            self.stop_recording()
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        logger.info("Flame detector stopped")


def train_fire_model(data_yaml="fire_dataset/data.yaml", epochs=50, imgsz=640):
    logger.info("Training YOLOv11 fire detection model...")
    model = YOLO("yolo11n.pt")
    results = model.train(data=data_yaml, epochs=epochs, imgsz=imgsz, patience=10,
                          name="fire_detect", exist_ok=True)
    logger.info(f"Training completed. Best model: {results.save_dir}/weights/best.pt")
    return results


def convert_to_rknn(pt_model_path, rknn_output_path, dataset_txt="dataset.txt"):
    try:
        from rknn.api import RKNN
        rknn = RKNN()
        ret = rknn.load_pytorch(pt_model_path, input_size_list=[[1, 3, 640, 640]])
        if ret != 0:
            raise RuntimeError("Load PyTorch model failed")
        ret = rknn.build(do_quantization=True, dataset=dataset_txt)
        if ret != 0:
            raise RuntimeError("Build RKNN model failed")
        ret = rknn.export_rknn(rknn_output_path)
        if ret != 0:
            raise RuntimeError("Export RKNN model failed")
        rknn.release()
        logger.info(f"RKNN model exported: {rknn_output_path}")
    except ImportError:
        logger.error("rknn-toolkit2 not installed. Install: pip install rknn-toolkit2")
    except Exception as e:
        logger.error(f"RKNN conversion failed: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="火焰检测边缘设备")
    parser.add_argument("--config", default="flame_config.json", help="配置文件路径")
    parser.add_argument("--camera", type=str, help="摄像头地址 (RTSP URL 或 设备编号)")
    parser.add_argument("--model", type=str, help="YOLOv11模型路径")
    parser.add_argument("--server", type=str, help="服务端URL")
    parser.add_argument("--train", type=str, help="训练数据集yaml路径")
    parser.add_argument("--convert-rknn", type=str, help="转换模型为RKNN格式, 指定pt路径")
    parser.add_argument("--use-npu", action="store_true", help="使用NPU加速")
    parser.add_argument("--conf", type=float, help="检测置信度阈值")
    args = parser.parse_args()

    if args.train:
        train_fire_model(args.train)
        return
    if args.convert_rknn:
        convert_to_rknn(args.convert_rknn, args.convert_rknn.replace(".pt", ".rknn"))
        return

    cfg = Config(args.config if os.path.exists(args.config) else "flame_config.json")
    if args.camera:
        cfg._cfg["camera_url"] = int(args.camera) if args.camera.isdigit() else args.camera
    if args.model:
        cfg._cfg["model_path"] = args.model
    if args.server:
        cfg._cfg["server_url"] = args.server
    if args.use_npu:
        cfg._cfg["use_npu"] = True
    if args.conf is not None:
        cfg._cfg["conf_threshold"] = args.conf

    detector = FlameDetector(cfg)
    detector.run()


if __name__ == "__main__":
    main()
