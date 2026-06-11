#!/usr/bin/env python3
"""
后端启动入口 — 火焰检测 + 服务端通信
直接运行: python3 main.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flame_detect import FlameDetector, Config

if __name__ == "__main__":
    cfg = Config(os.path.join(os.path.dirname(__file__), "flame_config.json"))
    detector = FlameDetector(cfg)
    detector.run()
