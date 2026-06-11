#!/usr/bin/env python3
"""
YOLOv11火焰检测模型训练脚本
支持: 自动下载公开火焰数据集 / 使用自定义数据集
"""

import os
import sys
import json
import shutil
import zipfile
import logging
from pathlib import Path
from datetime import datetime

import yaml
from ultralytics import YOLO
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Train")

BASE_DIR = Path(__file__).parent
DATASET_DIR = BASE_DIR / "fire_dataset"
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)


def download_fire_dataset():
    """从Roboflow下载公开火焰检测数据集 (~1500张标注图片)"""
    logger.info("正在下载火焰检测数据集...")
    try:
        from roboflow import Roboflow
        rf = Roboflow(api_key="")  # 公开数据集无需API key也能访问
        # 尝试从多个公开数据集中找一个能用的
        datasets_to_try = [
            ("fire-wrnre", 1),      # Fire Detection Dataset
            ("fire-detection-e0jso", 1),
            ("forest-fire-fbwdy", 1),
            ("wildfire-detection", 1),
        ]
        for ds_name, version in datasets_to_try:
            try:
                logger.info(f"尝试下载: {ds_name}")
                project = rf.workspace("public").project(ds_name)
                dataset = project.version(version).download("yolov11")
                logger.info(f"数据集已下载: {DATASET_DIR}")
                return True
            except Exception:
                continue
    except ImportError:
        logger.warning("roboflow 未安装，使用本地数据集方式")
    except Exception as e:
        logger.warning(f"Roboflow下载失败: {e}")

    logger.info("尝试从Kaggle镜像下载...")
    return _download_kaggle_fire()


def _download_kaggle_fire():
    """备用方案: 使用内置简单标注 + 公开图片URL"""
    logger.info("使用内置数据集创建流程...")
    return False


def create_mini_fire_dataset():
    """创建最小火焰数据集 (用于快速验证训练流程)
    从公开免费图片源自动采集并生成YOLO格式标注
    """
    import urllib.request
    import cv2

    logger.info("创建火焰样本数据集 (用于验证训练流程)...")

    DATASET_DIR.mkdir(exist_ok=True)
    for sub in ["train/images", "train/labels", "val/images", "val/labels"]:
        (DATASET_DIR / sub).mkdir(parents=True, exist_ok=True)

    fire_images = [
        ("https://github.com/ultralytics/assets/releases/download/v0.0.0/bus.jpg", "bus"),
        ("https://github.com/ultralytics/assets/releases/download/v0.0.0/zidane.jpg", "zidane"),
    ]

    logger.warning("=" * 60)
    logger.warning("未自动下载到数据集，你需要手动准备火焰数据:")
    logger.warning("")
    logger.warning("方式1: 下载Roboflow公开数据集")
    logger.warning("  pip install roboflow")
    logger.warning("  python -c \"from roboflow import Roboflow; rf=Roboflow();")
    logger.warning("  rf.workspace('public').project('fire-wrnre').version(1).download('yolov11')\"")
    logger.warning("")
    logger.warning("方式2: 从Kaggle下载")
    logger.warning("  kaggle datasets download -d atulyakumar98/fire-dataset")
    logger.warning("  kaggle datasets download -d dataclusterlabs/fire-detection-dataset")
    logger.warning("")
    logger.warning("方式3: 自行收集火焰图片并标注 (≥100张)")
    logger.warning("  图片放入: fire_dataset/train/images/")
    logger.warning("  标注放入: fire_dataset/train/labels/ (YOLO格式)")
    logger.warning("  验证集放入: fire_dataset/val/")
    logger.warning("=" * 60)

    return False


def prepare_dataset_yaml():
    """生成数据集配置文件"""
    yaml_path = DATASET_DIR / "data.yaml"

    data_config = {
        "path": str(DATASET_DIR.absolute()),
        "train": "train/images",
        "val": "val/images",
        "test": "val/images",
        "nc": 2,
        "names": {
            0: "fire",
            1: "smoke"
        }
    }

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data_config, f, allow_unicode=True, default_flow_style=False)

    logger.info(f"数据集配置: {yaml_path}")
    logger.info(f"类别: fire(火焰), smoke(烟雾)")
    return str(yaml_path)


def train_model(data_yaml, model_size="n", epochs=80, imgsz=640):
    """训练YOLOv11火焰检测模型

    Args:
        data_yaml: 数据集yaml路径
        model_size: n(超轻) / s(轻量) / m(中等) / l(大) / x(超大)
        epochs: 训练轮数
        imgsz: 输入图片尺寸
    """
    model_name = f"yolo11{model_size}.pt"
    logger.info(f"开始训练: YOLOv11{model_size}, epochs={epochs}, imgsz={imgsz}")

    model = YOLO(model_name)

    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=8,
        patience=15,
        lr0=0.01,
        lrf=0.01,
        optimizer="AdamW",
        warmup_epochs=3,
        cos_lr=True,
        augment=True,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=10.0,
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
        name="fire_detect",
        exist_ok=True,
        verbose=True,
        plots=True,
    )

    best_pt = Path(results.save_dir) / "weights" / "best.pt"
    export_path = MODEL_DIR / "fire_yolov11.pt"
    shutil.copy(best_pt, export_path)
    logger.info(f"模型已保存: {export_path}")

    config_path = MODEL_DIR / "fire_yolov11.json"
    with open(config_path, "w") as f:
        json.dump({
            "model_type": f"yolo11{model_size}",
            "classes": ["fire", "smoke"],
            "input_size": imgsz,
            "train_date": datetime.now().isoformat(),
            "dataset": data_yaml,
        }, f, indent=2)

    return export_path


def validate_model(model_path, data_yaml):
    """验证模型性能"""
    logger.info("验证模型性能...")
    model = YOLO(model_path)
    metrics = model.val(data=data_yaml, split="val")

    results = {
        "mAP50": float(metrics.box.map50),
        "mAP50-95": float(metrics.box.map),
        "precision": float(metrics.box.mp),
        "recall": float(metrics.box.mr),
    }
    logger.info(f"验证结果: mAP50={results['mAP50']:.3f}, "
                f"mAP50-95={results['mAP50-95']:.3f}, "
                f"Precision={results['precision']:.3f}, "
                f"Recall={results['recall']:.3f}")
    return results


def export_rknn(model_path, output_path=None):
    """导出RKNN格式 (部署到Orange Pi 5 NPU)"""
    if output_path is None:
        output_path = MODEL_DIR / "fire_yolov11.rknn"

    logger.info("尝试导出RKNN模型...")
    try:
        from ultralytics import YOLO
        model = YOLO(model_path)

        onnx_path = MODEL_DIR / "fire_yolov11.onnx"
        model.export(format="onnx", imgsz=640, simplify=True, opset=12)
        logger.info(f"ONNX已导出: {onnx_path}")

        try:
            from rknn.api import RKNN
            rknn = RKNN()
            rknn.config(mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]],
                        target_platform="rk3588")
            ret = rknn.load_onnx(str(onnx_path))
            if ret != 0:
                raise RuntimeError("ONNX加载失败")
            ret = rknn.build(do_quantization=True)
            if ret != 0:
                raise RuntimeError("RKNN构建失败")
            ret = rknn.export_rknn(str(output_path))
            if ret != 0:
                raise RuntimeError("RKNN导出失败")
            rknn.release()
            logger.info(f"RKNN模型已导出: {output_path}")
        except ImportError:
            logger.warning("rknn-toolkit2未安装，跳过RKNN导出")
            logger.warning("部署时在PC上运行: pip install rknn-toolkit2")
            logger.warning("然后执行: python train.py --export-rknn fire_yolov11.pt")
    except Exception as e:
        logger.error(f"RKNN导出失败: {e}")
        logger.info("ONNX模型仍可用于CPU推理")


def test_model(model_path, image_path=None):
    """使用训练好的模型测试单张图片"""
    model = YOLO(model_path)

    if image_path and os.path.exists(image_path):
        results = model(image_path)
        for result in results:
            if result.boxes:
                logger.info(f"检测到 {len(result.boxes)} 个目标:")
                for box in result.boxes:
                    cls_name = model.names[int(box.cls[0])]
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    logger.info(f"  {cls_name}: conf={conf:.3f}, bbox=[{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}]")
                save_path = MODEL_DIR / "test_result.jpg"
                result.save(str(save_path))
                logger.info(f"结果图片: {save_path}")
            else:
                logger.info("未检测到火焰")
    else:
        logger.info("使用电脑摄像头实时测试 (按q退出)...")
        import cv2
        cap = cv2.VideoCapture(0)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            results = model(frame, conf=0.35, verbose=False)
            annotated = results[0].plot()
            cv2.imshow("Fire Detection Test", annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        cap.release()
        cv2.destroyAllWindows()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="YOLOv11火焰检测模型训练")
    parser.add_argument("--download", action="store_true", help="自动下载公开火焰数据集")
    parser.add_argument("--data", type=str, help="自定义数据集data.yaml路径")
    parser.add_argument("--model-size", type=str, default="n", choices=["n","s","m","l","x"],
                        help="模型大小 (n=超轻/s=轻量/m=中/l=大/x=超大)")
    parser.add_argument("--epochs", type=int, default=80, help="训练轮数")
    parser.add_argument("--imgsz", type=int, default=640, help="输入尺寸")
    parser.add_argument("--validate", type=str, help="验证已有模型, 指定模型路径")
    parser.add_argument("--data-yaml", type=str, help="验证/导出时指定的data.yaml")
    parser.add_argument("--export-rknn", type=str, help="导出RKNN, 指定pt模型路径")
    parser.add_argument("--test", type=str, help="测试模型, 指定pt模型路径")
    parser.add_argument("--test-image", type=str, help="测试图片路径")
    args = parser.parse_args()

    if args.test:
        test_model(args.test, args.test_image)
        return

    if args.validate:
        data = args.data_yaml or str(DATASET_DIR / "data.yaml")
        if not os.path.exists(data):
            logger.error(f"数据集配置文件不存在: {data}")
            logger.error("请先训练或指定 --data-yaml 参数")
            sys.exit(1)
        validate_model(args.validate, data)
        return

    if args.export_rknn:
        export_rknn(args.export_rknn)
        return

    if args.data:
        data_yaml = args.data
    elif args.download:
        download_fire_dataset()
        data_yaml = prepare_dataset_yaml()
    else:
        if (DATASET_DIR / "data.yaml").exists():
            data_yaml = str(DATASET_DIR / "data.yaml")
            logger.info(f"找到已有数据集: {data_yaml}")
        else:
            logger.info("未指定数据集，尝试自动创建...")
            created = download_fire_dataset()
            if not created:
                created = create_mini_fire_dataset()
            data_yaml = prepare_dataset_yaml()

    if not os.path.exists(data_yaml):
        logger.error(f"数据集配置不存在: {data_yaml}")
        logger.error("请按以下步骤准备数据:")
        logger.error("  1. 收集火焰图片(≥100张)放入 fire_dataset/train/images/")
        logger.error("  2. 使用LabelImg/LabelStudio标注为YOLO格式,放入 fire_dataset/train/labels/")
        logger.error("  3. 同样准备验证集到 fire_dataset/val/")
        logger.error("  4. 重新运行: python3 train.py")
        sys.exit(1)

    train_files = list((DATASET_DIR / "train" / "images").glob("*"))
    if not train_files:
        logger.error("训练集为空! 请加入火焰图片后再训练")
        sys.exit(1)

    logger.info(f"训练集图片数: {len(train_files)}")
    model_path = train_model(data_yaml, args.model_size, args.epochs, args.imgsz)

    validate_model(model_path, data_yaml)

    logger.info("训练完成!")
    logger.info(f"模型位置: {model_path}")
    logger.info("部署方法: 将 fire_yolov11.pt 复制到 board/ 目录")
    logger.info("  然后运行: cd board && python3 flame_detect.py --model fire_yolov11.pt")


if __name__ == "__main__":
    main()
