#!/usr/bin/env python3
"""
后端启动入口 — 火焰/烟雾检测 + 服务端通信
运行时提供交互式菜单，可自定义选择或初始化配置
"""

import os
import sys

# 设置 Qt 平台插件，确保在 Linux 下正常显示 GUI
os.environ["QT_QPA_PLATFORM"] = "xcb"

# 将当前目录加入模块搜索路径，便于导入同目录下的 flame_detect 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flame_detect import FlameDetector, Config

def show_interactive_menu():
    """显示交互式启动菜单，允许用户选择启动模式或自定义配置参数

    返回值:
        Config: 根据用户交互生成的配置对象
    """
    # 从与当前脚本同级目录加载 JSON 配置文件
    config_path = os.path.join(os.path.dirname(__file__), "flame_config.json")
    cfg = Config(config_path)

    # 打印启动菜单
    print("\n" + "="*60)
    print("🔥 YOLOv11 火焰烟雾智能监测系统 - 设备端启动平台")
    print("="*60)
    print(" [1] 快速启动 (直接使用默认配置文件参数)")
    print(" [2] 自定义启动 (手动交互式修改地点、端口、视频源)")
    print(" [3] 退出系统")
    print("="*60)
    
    choice = input("请选择操作 [1-3] (默认: 1): ").strip() or "1"
    
    if choice == "3":
        print("已退出系统。")
        sys.exit(0)
        
    if choice == "2":
        # 自定义启动模式：逐项配置参数
        print("\n--- 交互式初始化配置 ---")
        
        # 1. 配置安装地点
        default_loc = cfg.location
        loc_input = input(f"📍 请输入安装地点 (当前默认: '{default_loc}'): ").strip()
        if loc_input:
            cfg._cfg["location"] = loc_input
            
        # 2. 配置 WebSocket 服务端口
        default_port = getattr(cfg, "ws_port", 9999)
        port_input = input(f"🔌 请输入WebSocket服务端口 (当前默认: {default_port}): ").strip()
        if port_input:
            try:
                cfg._cfg["ws_port"] = int(port_input)
            except ValueError:
                print(f"⚠️ 端口格式无效，将采用默认端口: {default_port}")
                
        # 3. 配置视频源（摄像头编号 / 本地视频路径 / RTSP 流地址）
        default_source = cfg.camera_url
        source_input = input(f"🎥 请输入视频源 (0表示默认摄像头，或输入本地视频路径/RTSP流地址, 默认: '{default_source}'): ").strip()
        if source_input:
            try:
                cfg._cfg["camera_url"] = int(source_input)
            except ValueError:
                cfg._cfg["camera_url"] = source_input
                
        # 4. 配置摄像头 ID
        default_cam_id = cfg.camera_id
        cam_id_input = input(f"🆔 请输入摄像头ID (当前默认: {default_cam_id}): ").strip()
        if cam_id_input:
            try:
                cfg._cfg["camera_id"] = int(cam_id_input)
            except ValueError:
                print(f"⚠️ 摄像头ID格式无效，将采用默认ID: {default_cam_id}")

    # 打印最终配置摘要，供用户确认
    print("\n" + "="*60)
    print("🚀 系统初始化配置完成，即将启动检测：")
    print(f"   📍 监控地点: {cfg.location}")
    print(f"   🔌 WebSocket服务端口: {cfg.ws_port}")
    print(f"   🎥 视频源: {cfg.camera_url}")
    print(f"   🆔 摄像头ID: {cfg.camera_id}")
    print(f"   📂 报警数据目录: {cfg.save_dir}")
    print("="*60 + "\n")
    
    return cfg

if __name__ == "__main__":
    try:
        # 显示交互式菜单并获取用户配置
        cfg = show_interactive_menu()
        # 创建火焰检测器实例并启动主循环
        detector = FlameDetector(cfg)
        detector.run()
    except KeyboardInterrupt:
        # 用户通过 Ctrl+C 优雅终止
        print("\n检测任务已被用户终止。")
        sys.exit(0)
