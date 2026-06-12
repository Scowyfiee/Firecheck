# 视频AI智能识别及预警管理系统 — 完整部署指南

## 项目结构

```
fire/
├── board/                              # 边缘设备端（火焰检测）
│   ├── main.py                         # 启动入口（直接运行）
│   ├── flame_detect.py                 # 火焰检测核心模块
│   ├── flame_config.json               # 设备配置（模型路径/服务端地址/摄像头）
│   ├── run_train.py                    # 一键训练脚本
│   ├── test_model.py                   # 模型测试工具（4种模式）
│   ├── fire_dataset/                   # 训练数据集
│   │   └── data.yaml
│   ├── models/                         # 训练产出模型
│   ├── runs/                           # 训练日志/权重（git忽略）
│   └── alarm_data/                     # 报警图片视频缓存
├── server/                             # Web管理服务端
│   └── web_server.py                   # Flask全栈（单文件）
└── test/                               # 测试视频/图片（git忽略）
    └── *.mp4
```

---

## 系统架构

```
摄像头 ──RTSP/USB──> 边缘设备(main.py) ──HTTP──> Web服务端(web_server.py) ──> 浏览器
                         │                              │
                    YOLOv11检测火焰                Flask + SQLite
                    保存图片+5秒视频              数据大屏 + 管理后台
```

**两个组件必须同时运行才能看到完整效果。**

---

## 第一步：训练模型

```bash
cd fire/board
python3 run_train.py
```

自动检测已有模型，用低学习率继续优化。训练完成后模型位置：
- `runs/detect/fire_detect/weights/best.pt` (高精度模型，支持火焰与烟雾双通道检测)

---

## 第二步：测试模型效果

```bash
cd fire/board
python3 test_model.py
```

菜单选择：
- 1 → 摄像头实时检测
- 2 → 验证集图片浏览
- 3 → 单张图片检测
- 4 → 视频文件检测（推荐先用 test/*.mp4 测试）

---

## 第三步：启动 Web 管理服务端

**终端1：**

```bash
cd fire/server
python3 web_server.py
```

访问 http://127.0.0.1:5000

| 账号 | 密码 | 角色 | 权限 |
|------|------|------|------|
| admin | 123456 | 超级管理员 | 全部 |
| chuli001 | 123456 | 处理人 | 报警处理 |
| shenhe001 | 123456 | 审核人 | 事件审核 |

---

## 第四步：启动火焰与烟雾检测端

**终端2：**

```bash
cd fire/board
# 启动检测端：
python3 main.py

# 启动后，终端会进入交互式初始化配置面板：
# - 选择 1: 快速启动 (直接加载配置文件默认参数)
# - 选择 2: 自定义启动 (交互式手动输入/修改当前地点的端口、地点、摄像头源和 ID)
```

> [!NOTE]
> 边缘检测端启动后，会通过心跳机制向 Web 服务端上报自定义的 **WebSocket 端口 (port)** 和 **安装地点 (location)**，Web 端会智能接收并记录各个端口，从而在前端大屏流畅切换和扫描不同的摄像头画面。

---

## 本地测试流程（在PC上完整验证）

**目标：在你自己电脑上把整条链路跑通，确认没问题后再搬到开发板上。**

```
┌─────────────────────────────────────────────────────────┐
│                    你的电脑 (localhost)                   │
│                                                         │
│  终端1: web_server.py  ←──  浏览器访问 127.0.0.1:5000    │
│                    ↑                                     │
│  终端2: main.py     ──HTTP──→  上报报警事件             │
│           ↑                                             │
│      摄像头/USB摄像头/视频文件                            │
└─────────────────────────────────────────────────────────┘
```

### 4.1 确认配置

`fire/board/flame_config.json`:
```json
{
    "server_url": "http://127.0.0.1:5000",
    "camera_url": 0,
    "model_path": "runs/detect/fire_detect/weights/best.pt",
    "detect_classes": [0, 1],
    "conf_threshold": 0.35
}
```

### 4.2 启动测试

```bash
# 终端1
cd fire/server && python3 web_server.py

# 终端2
cd fire/board && python3 main.py
```

### 4.3 手动触发报警（无需真实火焰）

```bash
# 终端3: 模拟边缘设备发送报警
curl -X POST http://127.0.0.1:5000/api/alarm \
  -F "device_mac=AAABBBCCCDDD" \
  -F "device_id=1" \
  -F "camera_id=1" \
  -F "area_id=1" \
  -F "longitude=106.551556" \
  -F "latitude=29.563009" \
  -F "location=重庆理工大学花溪校区"
```

刷新 http://127.0.0.1:5000/dashboard → 数据大屏出现报警记录。

### 4.4 验证全流程

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 浏览器打开 127.0.0.1:5000 | 登录页 |
| 2 | admin/123456 登录 | 数据大屏，地图上有3个摄像头 |
| 3 | 终端2运行 main.py | 日志显示 "Flame detection started" |
| 4 | curl 模拟报警（或对摄像头展示火焰） | 终端2日志显示 "FLAME DETECTED!" |
| 5 | 刷新数据大屏 | 总报警次数+1，列表有新记录 |
| 6 | 点击 报警事件 → 处理 | 填写紧急程度/结果 → 提交 |
| 7 | 切换到审核账号 shenhe001 | 事件审核 → 通过 |
| 8 | 查看操作日志 | 记录所有操作 |

---

## 实机测试流程（部署到 Orange Pi 5）

**目标：代码+模型搬到开发板上运行，开发板通过网线连到PC。**

```
┌──────────────┐         HTTP          ┌──────────────────┐
│  Orange Pi 5 │ ───────────────────→  │  你的PC/笔记本     │
│              │   192.168.1.x:5000    │                  │
│  main.py     │                       │  web_server.py   │
│  + 摄像头     │                       │  浏览器访问       │
│  + YOLO模型  │                       │  127.0.0.1:5000  │
└──────────────┘                       └──────────────────┘
```

### 5.1 网络连接方式

| 方式 | 连接 | Orange Pi 5 IP | PC IP |
|------|------|---------------|-------|
| 网线直连 | Orange Pi 5 ←网线→ PC | 手动设静态IP | 手动设静态IP |
| 同一路由器 | 都插同一个路由器 | DHCP自动获取 | DHCP自动获取 |
| 同一WiFi | 都连同一个WiFi | DHCP自动获取 | DHCP自动获取 |

### 5.2 烧录系统

参考 `OrangePi_5_RK3588S_用户手册_v2.1.1.pdf` 第2章：
- 下载 Debian/Ubuntu 镜像
- 用 balenaEtcher 烧录到 TF 卡
- 插卡上电，接HDMI显示器或SSH登录

### 5.3 开发板环境配置

```bash
# SSH登录（默认账号密码: orangepi / orangepi）
ssh orangepi@<开发板IP>

# 安装依赖
sudo apt update
sudo apt install -y python3-pip python3-opencv
pip3 install ultralytics requests numpy pyyaml torch --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 5.4 上传代码和模型

```bash
# 在你的PC上执行
cd /home/value/Keshe

# 上传整个board目录
scp -r fire/board/ orangepi@<开发板IP>:~/fire_board/

# 开发板上的目录结构:
# ~/fire_board/
#   ├── main.py
#   ├── flame_detect.py
#   ├── flame_config.json
#   ├── runs/detect/fire_detect_continue/weights/best.pt
#   └── ...
```

### 5.5 修改配置指向PC

在开发板上编辑 `~/fire_board/flame_config.json`:
```json
{
    "server_url": "http://<你PC的IP>:5000",
    "camera_url": 0,
    "model_path": "runs/detect/fire_detect/weights/best.pt",
    "detect_classes": [0, 1],
    "conf_threshold": 0.35
}
```

### 5.6 启动

**PC端（终端1）：**
```bash
cd fire/server && python3 web_server.py
```

**开发板端（SSH终端2）：**
```bash
cd ~/fire_board && python3 main.py
```

**PC端浏览器：**
```
http://127.0.0.1:5000
```

### 5.7 实机验证清单

| 步骤 | 验证项 | 方法 |
|------|--------|------|
| 1 | 开发板摄像头正常 | 开发板上跑 `python3 test_model.py` 选1 |
| 2 | 开发板能ping通PC | `ping <PC的IP>` |
| 3 | PC端Web可访问 | 浏览器打开 127.0.0.1:5000 |
| 4 | 心跳通信正常 | web_server.py 日志显示 heartbeat |
| 5 | 报警上报正常 | 对摄像头展示火焰，刷新大屏有记录 |
| 6 | 图片视频存储 | `ls server/uploads/pictures/` 有新文件 |

---

## 答辩演示顺序

| 序号 | 操作 | 说辞 |
|------|------|------|
| 1 | 启动 web_server.py | 这是Web管理服务端，B/S架构 |
| 2 | 浏览器登录 admin/123456 | 系统分三种角色：管理员/处理人/审核人 |
| 3 | 展示数据大屏 | 地图显示摄像头分布，ECharts统计图表 |
| 4 | 展示设备管理 | 已配置AI分析盒和摄像头的MAC/位置 |
| 5 | SSH登录开发板，启动 main.py | 边缘设备运行YOLOv11模型，NPU加速 |
| 6 | 手机播放火焰视频对准摄像头 | 实时检测，<2秒延迟报警 |
| 7 | 刷新数据大屏 | 地图弹出报警弹窗，显示图片+视频+经纬度 |
| 8 | 报警事件 → 处理 | 紧急程度/处理结果/描述 |
| 9 | 切换审核账号 → 审核通过 | 三级流程闭环 |
| 10 | 展示日志管理 | 所有操作可追溯 |

---

## 常见问题

**Q: main.py 启动后报 "Model not found, downloading yolo11n"**
> 检查 `flame_config.json` 中 `model_path` 是否正确指向训练好的 `best.pt`。

**Q: heartbeat 报 Connection refused**
> web_server.py 没启动，先在另一个终端启动它。

**Q: 数据大屏没有地图**
> 地图依赖百度地图API在线加载，需要联网。如离线演示，地图区域显示为空但不影响报警列表。

**Q: CUDA out of memory**
> 降低 `run_train.py` 中的 `batch` 参数：12 → 8 → 4。

**Q: Orange Pi 5 找不到摄像头**
```bash
ls /dev/video*          # 查看摄像头设备
v4l2-ctl --list-devices # 查看详细信息
```
