#!/usr/bin/env python3
"""
YOLOv11 火焰烟雾检测 - 智能断点续训 (自动扩展至 80 轮)
直接运行: python3 run_train.py
"""

import os
import glob
import json
import shutil
import yaml
from datetime import datetime
from ultralytics import YOLO


def train():
    print("=" * 60)
    print("  YOLOv11 火焰检测 - 🚀 智能断点续训 (目标: 80轮)")
    print("=" * 60)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_dir = os.path.join(base_dir, "fire_dataset")

    # ================================================================
    # 第1步: 检查数据集并修正 data.yaml
    # ================================================================
    print("\n[1/3] 检查数据集...")

    candidate_train = ["data/train/images", "train/images", "images"]
    candidate_val = [
        "data/val/images",
        "data/valid/images",
        "val/images",
        "valid/images",
    ]

    train_img = None
    val_img = None
    for d in candidate_train:
        p = os.path.join(dataset_dir, d)
        if os.path.isdir(p) and os.listdir(p):
            train_img = d
            break
    for d in candidate_val:
        p = os.path.join(dataset_dir, d)
        if os.path.isdir(p) and os.listdir(p):
            val_img = d
            break

    if not train_img or not val_img:
        print("❌ 错误: 找不到数据集!")
        return

    train_count = len(os.listdir(os.path.join(dataset_dir, train_img)))
    val_count = len(os.listdir(os.path.join(dataset_dir, val_img)))

    label_dir = train_img.replace("images", "labels")
    abs_label_dir = os.path.join(dataset_dir, label_dir)
    classes = {0: "smoke", 1: "fire"}

    yaml_content = {
        "path": str(dataset_dir),
        "train": train_img,
        "val": val_img,
        "nc": len(classes),
        "names": classes,
    }
    yaml_path = os.path.join(dataset_dir, "data.yaml")
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False, allow_unicode=True)

    print("   ✅ data.yaml 已配置")

    # ================================================================
    # 第2步: 智能修改总轮数并续训 (Resume to 80 Epochs)
    # ================================================================
    # 自动搜索 runs/detect 目录下所有的 last.pt，并按修改时间排序找最新那个！
    search_pattern = os.path.join(base_dir, "runs", "detect", "*", "weights", "last.pt")
    all_last_pts = glob.glob(search_pattern)

    if not all_last_pts:
        print("\n❌ 致命错误: 在 runs/detect/ 下没找到任何 last.pt 断点文件！")
        return

    # 1. 获取最新修改的那个 last.pt
    latest_last_pt = max(all_last_pts, key=os.path.getmtime)
    print(f"\n[2/3] 🌟 锁定最新的断点文件: \n      {latest_last_pt}")

    # 2. 【核心魔法】：自动找到对应的 args.yaml，把总轮数强行改成 80 轮！
    run_dir = os.path.dirname(
        os.path.dirname(latest_last_pt)
    )  # 向上两级找到本次运行的根目录
    args_yaml = os.path.join(run_dir, "args.yaml")
    target_epochs = 80  # <--- 你想要的总轮数在这里！

    if os.path.exists(args_yaml):
        with open(args_yaml, "r", encoding="utf-8") as f:
            args_cfg = yaml.safe_load(f)

        current_epochs = args_cfg.get("epochs", 0)
        if current_epochs != target_epochs:
            args_cfg["epochs"] = target_epochs
            with open(args_yaml, "w", encoding="utf-8") as f:
                yaml.safe_dump(args_cfg, f)
    else:
        print(f"      ⚠️ 警告: 找不到配置文件 {args_yaml}，修改轮数可能失败。")

    print(f"      正在恢复训练进度...\n")

    # 3. 用找到的最新断点文件来初始化，并开启真正的续训
    try:
        model = YOLO(latest_last_pt)
        # ⚠️ resume=True 会自动读取我们刚刚改成 80 轮的 args.yaml！
        results = model.train(resume=True)
    except AssertionError as e:
        print(f"\n❌ 断点恢复失败。原因: {e}")
        return
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        return

    # 训练完成后，提取最新的 best.pt 保存到 models 文件夹
    best_pt = os.path.join(results.save_dir, "weights", "best.pt")
    models_dir = os.path.join(base_dir, "models")
    os.makedirs(models_dir, exist_ok=True)
    out_path = os.path.join(models_dir, "fire_yolov11_final.pt")
    shutil.copy(best_pt, out_path)
    print(f"   ✅ 训练彻底完成! 最新融合模型已存至: {out_path}")

    # ================================================================
    # 第3步: 验证
    # ================================================================
    print(f"\n[3/3] 验证最终模型指标...")

    val_model = YOLO(out_path)
    metrics = val_model.val(data=yaml_path, split="val")

    mAP50 = float(metrics.box.map50)
    mAP = float(metrics.box.map)
    prec = float(metrics.box.mp)
    recall = float(metrics.box.mr)

    def level(v):
        if v >= 0.80:
            return "优秀"
        if v >= 0.70:
            return "良好"
        if v >= 0.60:
            return "及格"
        return "需优化"

    print(f"   mAP50      : {mAP50:.4f}  ({level(mAP50)})")
    print(f"   mAP50-95   : {mAP:.4f}  ({level(mAP)})")
    print(f"   Precision  : {prec:.4f}  ({level(prec)})")
    print(f"   Recall     : {recall:.4f}  ({level(recall)})")

    eval_info = {
        "dataset": "Smoke-Fire-Detection-YOLO",
        "model": "yolov11",
        "train_images": train_count,
        "val_images": val_count,
        "classes": classes,
        "metrics": {
            "mAP50": mAP50,
            "mAP50-95": mAP,
            "precision": prec,
            "recall": recall,
        },
        "train_time": datetime.now().isoformat(),
    }
    with open(os.path.join(models_dir, "fire_yolov11_eval.json"), "w") as f:
        json.dump(eval_info, f, indent=2, ensure_ascii=False)

    print(f"""
    ╔══════════════════════════════════════════╗
    ║              🎉 训练完美收官!            ║
    ║                                        ║
    ║  最终模型:  models/fire_yolov11_final.pt ║
    ║  开始测试:  python3 test_gui.py          ║
    ╚══════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    train()
