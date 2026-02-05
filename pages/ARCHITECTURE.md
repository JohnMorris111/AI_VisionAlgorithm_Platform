# AI 违停检测服务 - 后端架构

## 三层架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                      第三层：WebSocket API                        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  /ws (Punish算法)     /ws_roi (ROI算法)                       │ │
│  │  - receive_loop: 接收 start/stop 指令                         │ │
│  │  - push_loop: 推送 payload + 视频帧                           │ │
│  └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────┘
                                │ 调用
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      第二层：StreamWorker                         │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  职责：后台线程管理 + 状态共享                                   │ │
│  │                                                               │ │
│  │  start(source, algorithm)                                     │ │
│  │    → 创建检测器 → 启动后台线程                                   │ │
│  │                                                               │ │
│  │  _inference_loop() [后台线程]                                  │ │
│  │    → 读帧 → YOLO推理 → 停车检测 → 二阶段判定 → 更新共享状态        │ │
│  │                                                               │ │
│  │  共享状态（线程安全）：                                          │ │
│  │    - latest_result: 最新检测结果                                │ │
│  │    - latest_preview_jpeg: 最新预览图                            │ │
│  └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────┘
                                │ 调用
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     第一层：算法模块 (function/)                    │
│  ┌──────────────────────┐  ┌──────────────────────┐              │
│  │   suanfaRoi125.py     │  │     suanfa.py        │              │
│  │  (RoiDetector)        │  │  (PunishDetector)    │              │
│  │                        │  │                      │              │
│  │  - 基于 ROI 区域判定    │  │  - 基于赏罚机制判定   │              │
│  │  - 合法区=合法停车      │  │  - 二阶段区域模型     │              │
│  │  - 违规区=违规停车      │  │  - 累计奖惩分判定     │              │
│  └──────────────────────┘  └──────────────────────┘              │
│                                                                   │
│  共同基础：                                                         │
│  - YOLO 目标检测 + ByteTrack 跟踪                                   │
│  - parkingdetect(): 运动补偿 + 停车帧计数                            │
│  - panduan(): 二阶段违规判定                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 数据流详解

### 1. 客户端启动检测
```
客户端 → {"type": "start", "source": "rtsp://..."} → WebSocket
                                                         ↓
                                               receive_loop 接收
                                                         ↓
                                               worker.start(source, algorithm)
                                                         ↓
                                               _create_detector() → 实例化算法
                                                         ↓
                                               启动 _inference_loop 后台线程
```

### 2. 后台推理循环
```
_inference_loop (独立线程)
    │
    ├─→ 读取一帧 (cv2.VideoCapture)
    │
    ├─→ YOLO 检测 + ByteTrack 跟踪
    │       detector.model.track(frame, ...)
    │       返回: boxes.xyxy, boxes.id, boxes.cls
    │
    ├─→ 停车检测 (运动补偿)
    │       detector.parkingdetect(result, frame_index, motion_matrix)
    │       返回: {track_id: parked_frames}
    │
    ├─→ 二阶段判定
    │       detector.panduan(frame, result, parked_dict, ...)
    │       返回: {"status_map": {id: "违规停车/合法停车"}, "evidence": {...}}
    │
    ├─→ 构建结构化输出
    │       _build_frame_result() → FrameResult
    │
    ├─→ 保存违规证据 (可选)
    │       _save_violation_evidence() → result/目录
    │
    └─→ 更新共享状态 (加锁)
            self.latest_result = {...}
            self.latest_preview_jpeg = JPEG_bytes
```

### 3. 结果推送给客户端
```
push_loop (异步任务)
    │
    ├─→ 读取共享状态 (加锁)
    │       ts, payload, jpeg = worker.latest_*
    │
    ├─→ 发送 payload JSON
    │       {"type": "payload", "ts": ..., "payload": {...}}
    │
    └─→ 发送视频帧
            {"type": "frame", "ts": ...}
            [二进制 JPEG 数据]
```

---

## 核心类说明

### StreamWorker
```python
class StreamWorker:
    """线程安全的视频流处理器"""
    
    # 生命周期
    start(source, algorithm)  # 启动检测
    stop()                     # 停止检测
    is_running()              # 查询状态
    
    # 共享状态 (需加锁访问)
    latest_result             # 最新检测结果
    latest_preview_jpeg       # 最新预览图
    
    # 内部方法
    _create_detector()        # 工厂方法：创建算法实例
    _inference_loop()         # 后台线程：读帧→推理→更新
    _build_frame_result()     # 构建输出格式
    _render_preview()         # 渲染预览图
    _save_violation_evidence()  # 保存证据
```

### FrameResult / TrackInfo
```python
@dataclass
class TrackInfo:
    track_id: int          # 跟踪ID
    class_name: str        # 类别 (小汽车/卡车/...)
    bbox: list[int]        # [x1, y1, x2, y2]
    parked_frames: int     # 已停车帧数
    status: str            # 移动/停车/违规停车/合法停车
    panduan_result: str    # 二阶段判定结果

@dataclass
class FrameResult:
    frame_index: int
    algorithm: str         # roi/punish
    tracks: dict[str, TrackInfo]
    evidence: dict         # {"right": [...], "wrong": [...]}
```

---

## 文件结构

```
aiparking125Beta2RoiAiRepotBeta/
├── appRoi128knowclaude.py    # 主服务文件 (本文档描述)
├── function/                  # 算法模块目录
│   ├── suanfaRoi125.py       # ROI 算法
│   ├── suanfa.py             # Punish 算法
│   └── 赏罚.py               # 二阶段区域模型
├── weight/                    # 模型权重
│   ├── best.pt               # YOLO 主模型
│   └── CarV1.pt              # 区域判定模型
├── roibeta/                   # ROI 配置
│   └── 3_roi_candidates/
│       ├── roi_anchors.json  # ROI 锚点定义
│       └── frames/           # 关键帧图片
└── result/                    # 违规证据输出目录
```

---

## 关键设计决策

| 决策 | 原因 |
|------|------|
| **后台线程推理** | 视频读取是阻塞 IO，放在异步事件循环会卡住 |
| **共享状态 + 锁** | 推理线程和推送协程需要安全交换数据 |
| **两个独立 Worker** | ROI 和 Punish 算法可能同时运行，互不干扰 |
| **reload=True 加载模型** | 重置 ByteTrack tracker，让 ID 从头开始 |
| **抽帧推理 (frame_gap)** | 减少计算量，4 帧处理 1 帧 |
