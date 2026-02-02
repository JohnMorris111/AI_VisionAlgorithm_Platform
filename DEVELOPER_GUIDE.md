# AI Parking 算法开发框架

> **版本**: 1.0.0 Beta  
> **定位**: 类似 LangChain 的 **模块化算法集成框架**，当前聚焦于**违规停车检测**，可扩展到其他视觉 AI 算法。

---

## 📖 目录

1. [框架概述](#框架概述)
2. [现有算法清单](#现有算法清单)
3. [核心架构](#核心架构)
4. [算法接口规范](#算法接口规范)
5. [快速开始](#快速开始)
6. [如何开发新算法](#如何开发新算法)
7. [API 接口说明](#api-接口说明)
8. [配置与参数](#配置与参数)
9. [目录结构](#目录结构)

---

## 框架概述

本框架提供**统一的算法集成与调度能力**，核心设计理念：

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI 服务层                        │
│   /health  /parkingpredict  /parkingpayload  /ws       │
├─────────────────────────────────────────────────────────┤
│                    StreamWorker                          │
│       线程管理 · 视频流拉取 · 结果推送 · 证据存储         │
├─────────────────────────────────────────────────────────┤
│                 Algorithm Dispatcher                     │
│            按 algorithm 参数路由到不同检测器              │
├──────────────────┬───────────────────┬──────────────────┤
│   ROI 锚点算法    │   赏罚算法        │   (未来算法)     │
│   suanfaRoi125   │   suanfa + 赏罚   │   YourAlgorithm  │
└──────────────────┴───────────────────┴──────────────────┘
```

---

## 现有算法清单

| 算法标识 | 类名 | 模块路径 | 功能描述 |
|---------|------|---------|---------|
| `roi` / `roi125` / `anchor` | `RoiIllegalParkingDetector` | `function/suanfaRoi125.py` | 基于 **ROI 锚点匹配** 的违规停车检测，通过单应矩阵将预定义区域映射到实时帧 |
| `punish` / `sf` | `PunishIllegalParkingDetector` | `function/suanfa.py` | 基于 **赏罚机制** 的违规停车检测，配合二阶段区域判定 |
| `illegalparkingdetector2` | `IllegalParkingDetector2` | `function/赏罚.py` | **二阶段区域判定器**，对目标区域分类（合法/违规） |

### 算法选择

| 场景 | 推荐算法 |
|-----|---------|
| 已预标注 ROI 区域的固定摄像头 | `roi` |
| 无预标注区域，动态场景 | `punish` |
| 需要高精度二阶段验证 | `punish` + 二阶段 |

---

## 核心架构

### 1. 检测器基类设计

所有算法检测器遵循统一的接口模式：

```python
class BaseDetector:
    """算法检测器基类（概念性，当前隐式约定）"""
    
    def __init__(self, weights_path, source, device, conf, ...):
        """初始化模型与参数"""
        pass
    
    def load_model(self, reload: bool = False):
        """加载模型权重"""
        pass
    
    def parkingdetect(self, result, frame_index, M) -> dict[int, int]:
        """停车检测：返回 {track_id: 累计停车帧数}"""
        pass
    
    def panduan(self, frame, result, parked, min_frames, frame_index) -> dict:
        """二阶段判定：返回 {status_map: {}, evidence: {}}"""
        pass
```

### 2. StreamWorker 线程管理

```python
# 启动推理（内部自动选择算法）
worker.start(
    source="rtsp://...",
    algorithm="roi",  # 或 "punish"
    weights_path="...",
    # ... 其他参数
)

# 获取最新结果
payload = worker.latest_payload
# 结构: {frame_index, tracks: {track_id: {...}}, evidence: {right:[], wrong:[]}}

# 停止推理
worker.stop()
```

### 3. Payload 输出格式

```json
{
  "frame_index": 123,
  "tracks": {
    "1": {
      "track_id": 1,
      "cls_id": 3,
      "class_name": "小汽车",
      "conf": 0.87,
      "bbox": [100, 200, 300, 400],
      "parked_frames": 45,
      "panduan": "违规停车",
      "status": "违规停车"
    }
  },
  "evidence": {
    "right": [[x1,y1,x2,y2], ...],
    "wrong": [[x1,y1,x2,y2], ...]
  }
}
```

---

## 算法接口规范

### 必须实现的方法

要集成新算法到框架中，**必须**实现以下接口：

#### 1. `__init__` 构造函数

```python
def __init__(
    self,
    weights_path: str,       # 模型权重路径
    source: str,             # 视频源
    device: str = "mps",     # 计算设备
    imgsz: int = 640,        # 推理图像尺寸
    conf: float = 0.25,      # 置信度阈值
    tracker: str = "bytetrack.yaml",  # 跟踪器配置
    **kwargs                 # 其他算法特定参数
):
    pass
```

#### 2. `load_model` 加载模型

```python
def load_model(self, reload: bool = False) -> None:
    """加载或重新加载模型权重到 self.model"""
    if reload or self.model is None:
        self.model = YOLO(self.weights_path)
```

#### 3. `parkingdetect` 停车检测

```python
def parkingdetect(
    self,
    result,           # YOLO 检测结果
    frame_index: int, # 当前帧索引
    M,                # 运动补偿矩阵（可选）
) -> dict[int, int]:
    """
    返回 {track_id: parked_frames} 
    parked_frames > 0 表示该目标处于停车状态
    """
    pass
```

#### 4. `panduan` 二阶段判定

```python
def panduan(
    self,
    frame,            # 原始帧
    result,           # YOLO 检测结果
    parked: dict,     # parkingdetect 返回值
    min_frames: int,  # 最小停车帧数阈值
    frame_index: int,
) -> dict:
    """
    返回格式:
    {
        "status_map": {track_id: "合法停车"|"违规停车"|None, ...},
        "evidence": {"right": [...], "wrong": [...]}
    }
    """
    pass
```

---

## 快速开始

### 1. 直接使用 FastAPI 服务

```bash
# 启动服务
cd /Volumes/John/yolov8-visdrone/aiparking125Beta2RoiAiRepot
python appRoi125.py

# 服务端点
# - http://127.0.0.1:8000/health        # 健康检查
# - ws://127.0.0.1:8000/ws              # WebSocket (赏罚算法)
# - ws://127.0.0.1:8000/ws_roi          # WebSocket (ROI算法)
```

### 2. WebSocket 交互

```javascript
const ws = new WebSocket("ws://127.0.0.1:8000/ws_roi");

ws.onopen = () => {
  // 启动推理
  ws.send(JSON.stringify({
    type: "start",
    source: "rtsp://camera/stream"
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "payload") {
    console.log("检测结果:", data.payload);
  }
};

// 停止推理
ws.send(JSON.stringify({ type: "stop" }));
```

### 3. Python 直接调用算法

```python
from function.suanfaRoi125 import IllegalParkingDetector

detector = IllegalParkingDetector(
    weights_path="weight/best.pt",
    source="video.mp4",
    device="mps",
    conf=0.35,
    use_roi_detector=True,
    roi_json_path="roibeta/3_roi_candidates/roi_anchors.json",
)

detector.load_model()
detector.mainloop()  # 开始处理
```

---

## 如何开发新算法

### 步骤 1: 创建算法模块

在 `function/` 目录下创建新文件：

```python
# function/my_algorithm.py

import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from ultralytics import YOLO
import cv2
import numpy as np


class MyAlgorithmDetector:
    """我的自定义算法检测器"""
    
    def __init__(
        self,
        weights_path: str,
        source: str,
        device: str = "mps",
        imgsz: int = 640,
        conf: float = 0.25,
        tracker: str = "bytetrack.yaml",
        persist: bool = True,
        **kwargs
    ):
        self.weights_path = weights_path
        self.source = source
        self.device = device
        self.imgsz = imgsz
        self.conf = conf
        self.tracker = tracker
        self.persist = persist
        
        self.model = None
        self._track_history = {}
    
    def load_model(self, reload: bool = False):
        if reload or self.model is None:
            self.model = YOLO(self.weights_path)
    
    def parkingdetect(self, result, frame_index: int, M) -> dict[int, int]:
        """实现你的停车检测逻辑"""
        parked = {}
        if result.boxes is not None and result.boxes.id is not None:
            for i, track_id in enumerate(result.boxes.id):
                tid = int(track_id.item())
                # TODO: 实现你的检测逻辑
                parked[tid] = 0  # 返回停车帧数
        return parked
    
    def panduan(self, frame, result, parked, min_frames=None, frame_index=None) -> dict:
        """实现你的判定逻辑"""
        status_map = {}
        evidence = {"right": [], "wrong": []}
        
        for tid, frames in parked.items():
            if frames >= (min_frames or 30):
                # TODO: 实现合法/违规判定逻辑
                status_map[tid] = "违规停车"  # 或 "合法停车"
        
        return {"status_map": status_map, "evidence": evidence}
```

### 步骤 2: 在 appRoi125.py 中注册

```python
# 在 StreamWorker.start() 方法中添加新算法分支

from my_algorithm import MyAlgorithmDetector  # 导入

# ... 在 start() 方法的算法选择逻辑中添加:
elif algo in ("myalgo", "custom"):
    detector = MyAlgorithmDetector(
        weights_path=weights_path,
        source=source,
        device=device,
        conf=conf,
        imgsz=imgsz,
        tracker=tracker,
        persist=persist,
        frame_gap=frame_gap,
        **kwargs
    )
```

### 步骤 3: 添加专用 Worker 和 WebSocket (可选)

```python
# 创建专用 worker
worker_myalgo = StreamWorker()

# 添加 WebSocket endpoint
@app.websocket("/ws_myalgo")
async def ws_myalgo(websocket: WebSocket):
    # 复制 ws_roi 的逻辑，修改 algorithm 参数
    ...
```

---

## API 接口说明

### HTTP 接口

| 端点 | 方法 | 描述 |
|-----|------|-----|
| `/health` | GET | 系统健康检查，返回模型加载状态、路径信息 |
| `/parkingpayload` | GET | 获取赏罚算法最新检测结果 |
| `/parkingpayload_roi` | GET | 获取 ROI 算法最新检测结果 |

### WebSocket 接口

| 端点 | 协议 | 描述 |
|-----|------|-----|
| `/ws` | WebSocket | 赏罚算法实时推送 |
| `/ws_roi` | WebSocket | ROI 算法实时推送 |

#### WebSocket 消息格式

**客户端 -> 服务端：**
```json
{"type": "start", "source": "rtsp://..."}
{"type": "stop"}
```

**服务端 -> 客户端：**
```json
{"type": "schema", "schema": {...}}
{"type": "started", "running": true, "source": "...", "algorithm": "roi"}
{"type": "payload", "ts": 1234567890.123, "payload": {...}}
{"type": "frame", "ts": 1234567890.123}  // 后跟二进制 JPEG
{"type": "stopped", "running": false}
{"type": "error", "error": "..."}
```

---

## 配置与参数

### 后端默认参数（内部配置）

所有默认参数集中在 `appRoi125.py` 文件顶部，前端无需关心：

```python
# 主模型参数
DEFAULT_WEIGHTS_PATH = "weight/best.pt"
DEFAULT_DEVICE = "mps"
DEFAULT_CONF = 0.35
DEFAULT_IMGSZ = 384
DEFAULT_TRACKER = "bytetrack.yaml"
DEFAULT_FRAME_GAP = 4

# 二阶段参数
DEFAULT_AREA_WEIGHTS_PATH = "weight/CarV1.pt"
DEFAULT_AREA_CONF = 0.25

# ROI 参数
DEFAULT_ROI_JSON_PATH = "roibeta/3_roi_candidates/roi_anchors.json"
DEFAULT_ROI_KEYFRAMES_DIR = "roibeta/3_roi_candidates/frames"

# 证据保存参数
DEFAULT_EVIDENCE_THRESHOLD_FRAMES = 30
DEFAULT_EVIDENCE_EXPAND_RATIO = 1.5
```

### 检测目标

本算法默认检测以下车辆类型：

| 类型 | 说明 |
|------|------|
| 小汽车 | 私家车、轿车等 |
| 面包车 | 商务车、MPV 等 |
| 卡车 | 货车、大型车辆 |

---

## 目录结构

```
aiparking125Beta2RoiAiRepot/
├── appRoi125.py           # 主 FastAPI 服务入口
├── app.py                 # 旧版服务（参考）
├── app125.html            # 前端演示页面
│
├── function/              # 算法核心模块
│   ├── suanfa.py          # 赏罚算法（PunishIllegalParkingDetector）
│   ├── suanfaRoi125.py    # ROI锚点算法（RoiIllegalParkingDetector）
│   └── 赏罚.py            # 二阶段区域判定器（IllegalParkingDetector2）
│
├── roibeta/               # ROI 相关资源
│   ├── 1Original_data/    # 原始数据
│   ├── 2_keyframes_out/   # 关键帧输出
│   └── 3_roi_candidates/  # ROI 配置与检测器
│       ├── roi_anchors.json    # 锚点配置
│       ├── frames/             # 关键帧图像
│       └── roidetector125.py   # ROI检测器
│
├── weight/                # 模型权重
│   ├── best.pt            # 车辆检测模型
│   └── CarV1.pt           # 区域分类模型
│
├── result/                # 检测结果输出
│   └── {timestamp}_id{X}/ # 违规证据（全景图+裁剪图+CSV）
│
├── source/                # 测试视频源
│
└── docs/                  # 文档
    └── DEVELOPER_GUIDE.md # 本文档
```

---

## 未来扩展路线

1. **更多算法集成**
   - 火焰/烟雾检测
   - 人员闯入检测
   - 交通事故检测

2. **框架增强**
   - 算法自动注册机制
   - 统一的 BaseDetector 抽象类
   - 算法性能监控与对比

3. **工程化**
   - Docker 部署支持
   - GPU 多卡调度
   - 分布式推理

---

> **联系方式**: 如有疑问可联系闲鱼店铺：AI特级旷工  
> **服务**: 可提供远程配置环境、跑通等服务
