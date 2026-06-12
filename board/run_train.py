#!/usr/bin/env python3
"""
YOLOv11 火焰检测 - 极致精度版 (断点续跑 + 从已有模型继续优化)
直接运行: python3 run_train.py

策略: 加载你已有的 best.pt 作为预训练权重, 用 yolo11m 继续训 200 轮
"""

import os
import torch
import json
import shutil
import yaml
from datetime import datetime
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def find_best_model():
    """查找所有可能的已有模型, 优先选最新的"""
    candidates = [
        os.path.join(BASE_DIR, "models", "fire_yolov11.pt"),
        os.path.join(BASE_DIR, "models", "fire_yolov11_final.pt"),
        os.path.join(BASE_DIR, "runs", "detect", "fire_detect_pro", "weights", "best.pt"),
        os.path.join(BASE_DIR, "runs", "detect", "fire_detect", "weights", "best.pt"),
        os.path.join(BASE_DIR, "runs", "detect", "fire_detect_continue", "weights", "best.pt"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def detect_gpu_mem():
    """检测GPU可用显存(GB)"""
    try:
        free, total = torch.cuda.mem_get_info(0)
        return free / (1024 ** 3), total / (1024 ** 3)
    except Exception:
        return 0, 0


def train():
    print("=" * 62)
    print("  YOLOv11 火焰检测 - 🔥 极致精度训练 (断点续跑)")
    print("=" * 62)

    dataset_dir = os.path.join(BASE_DIR, "fire_dataset")

    # ================================================================
    # 第1步: 数据集 + 已有模型检测
    # ================================================================
    print("\n[1/4] 检查环境...")

    train_img = val_img = None
    for d in ["data/train/images", "train/images", "images"]:
        p = os.path.join(dataset_dir, d)
        if os.path.isdir(p) and os.listdir(p):
            train_img = d; break
    for d in ["data/val/images", "data/valid/images", "val/images", "valid/images"]:
        p = os.path.join(dataset_dir, d)
        if os.path.isdir(p) and os.listdir(p):
            val_img = d; break

    if not train_img or not val_img:
        print("❌ 找不到数据集!"); return

    train_count = len(os.listdir(os.path.join(dataset_dir, train_img)))
    val_count   = len(os.listdir(os.path.join(dataset_dir, val_img)))
    print(f"   训练集: {train_count} 张  |  验证集: {val_count} 张")

    prev_model = find_best_model()
    if prev_model:
        print(f"   ✅ 找到已有模型: {os.path.basename(prev_model)}")

    free_gb, total_gb = detect_gpu_mem()
    if total_gb > 0:
        print(f"   GPU 显存: {free_gb:.1f}G 可用 / {total_gb:.1f}G 总计")

    # 显存自适应配置
    if total_gb >= 10:
        cfg = {"model_name": "yolo11m.pt", "imgsz": 800, "batch": 12}
    elif total_gb >= 7:
        cfg = {"model_name": "yolo11m.pt", "imgsz": 640, "batch": 8}
    elif total_gb >= 5:
        cfg = {"model_name": "yolo11s.pt", "imgsz": 640, "batch": 16}
    else:
        cfg = {"model_name": "yolo11n.pt", "imgsz": 640, "batch": 8}

    print(f"   🎯 自动选择: {cfg['model_name']}  imgsz={cfg['imgsz']}  batch={cfg['batch']}")

    classes = {0: "smoke", 1: "fire"}
    yaml_path = os.path.join(dataset_dir, "data.yaml")
    with open(yaml_path, "w") as f:
        yaml.dump({"path": str(dataset_dir), "train": train_img, "val": val_img,
                    "nc": 2, "names": classes}, f, default_flow_style=False, allow_unicode=True)

    # ================================================================
    # 第2步: 决定训练模式 (从头训 / 断点续跑 / 从已有模型继续优化)
    # ================================================================
    print("\n[2/4] 确定训练模式...")

    run_name = "fire_detect_max"
    total_epochs = 80
    last_pt    = os.path.join(BASE_DIR, "runs", "detect", run_name, "weights", "last.pt")
    best_pt_ck = os.path.join(BASE_DIR, "runs", "detect", run_name, "weights", "best.pt")
    model_out  = os.path.join(BASE_DIR, "models", "fire_yolov11.pt")
    resume = False
    model  = None
    lr0 = 0.01

    # 情况A: 有本次训练的断点
    if os.path.exists(last_pt):
        try:
            ckpt = torch.load(last_pt, map_location="cpu", weights_only=False)
            done = ckpt.get("epoch", -1) + 1
        except Exception:
            done = "?"
        if isinstance(done, int) and done >= total_epochs:
            os.makedirs(os.path.dirname(model_out), exist_ok=True)
            if os.path.exists(best_pt_ck):
                shutil.copy(best_pt_ck, model_out)
            print(f"\n   ✅ {done}轮已训练完成, 无需再训 → {model_out}")
            return
        print(f"\n   🔄 发现断点: 已完成 {done}/{total_epochs} 轮")
        print(f"   继续? (Enter=是, n=重头训): ", end="")
        if input().strip().lower() not in ("n", "no"):
            model = YOLO(last_pt)
            resume = True
            lr0 = 0.001
            print(f"   ✅ 从第{done}轮续跑, lr={lr0}")

    # 情况B: 无断点但有之前训练的模型 → 用已有权重初始化, 低学习率继续优化
    if model is None and prev_model:
        print(f"\n   🚀 用 {os.path.basename(prev_model)} 的权重初始化, 低学习率微调")
        print(f"   目标: {total_epochs} 轮, lr=0.001")
        model = YOLO(prev_model)
        resume = False
        lr0 = 0.001

    # 情况C: 全新训练
    if model is None:
        print(f"\n   🆕 全新训练 {cfg['model_name']}  {total_epochs} 轮")
        model = YOLO(cfg["model_name"])

    # ================================================================
    # 第3步: 训练
    # ================================================================
    print(f"\n[3/4] 训练中...")

    results = model.train(
        data=yaml_path,
        epochs=total_epochs,
        imgsz=cfg["imgsz"],
        batch=cfg["batch"],
        device=0,
        workers=4,
        patience=40,
        lr0=lr0,
        lrf=lr0 * 0.1,
        optimizer="AdamW",
        warmup_epochs=5,
        cos_lr=True,
        close_mosaic=20,
        augment=True,
        hsv_h=0.02,
        hsv_s=0.8,
        hsv_v=0.5,
        degrees=15.0,
        translate=0.15,
        scale=0.6,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.2,
        name=run_name,
        exist_ok=True,
        plots=True,
        resume=resume,
    )

    best_pt = os.path.join(results.save_dir, "weights", "best.pt")
    os.makedirs(os.path.dirname(model_out), exist_ok=True)
    shutil.copy(best_pt, model_out)
    print(f"   ✅ 模型: {model_out}")

    # ================================================================
    # 第4步: 验证
    # ================================================================
    print(f"\n[4/4] 验证指标...")

    m = YOLO(model_out)
    met = m.val(data=yaml_path, split="val")
    map50   = float(met.box.map50)
    map_all = float(met.box.map)
    prec    = float(met.box.mp)
    rec     = float(met.box.mr)

    print(f"   mAP50      : {map50:.4f}")
    print(f"   mAP50-95   : {map_all:.4f}")
    print(f"   Precision  : {prec:.4f}")
    print(f"   Recall     : {rec:.4f}")

    json.dump({
        "model": cfg["model_name"].replace(".pt", ""),
        "imgsz": cfg["imgsz"],
        "epochs": total_epochs,
        "train_imgs": train_count,
        "val_imgs": val_count,
        "metrics": {"mAP50": map50, "mAP50-95": map_all, "Precision": prec, "Recall": rec},
        "time": datetime.now().isoformat(),
    }, open(os.path.join(BASE_DIR, "models", "fire_yolov11_eval.json"), "w"), indent=2)

    print(f"""
    ╔══════════════════════════════════════════╗
    ║              🎉 训练完成!                ║
    ║                                        ║
    ║  模型:  models/fire_yolov11.pt         ║
    ║  测试:  python3 test_model.py          ║
    ║  运行:  python3 main.py                ║
    ╚══════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    train()
