# AI Parking API 交互规范

> **以违规停车检测为范例**  
> 本文档定义后端 API 标准，供前端开发者调用。后续所有检测算法均遵循此规范。

---

## 📌 核心概念

```
┌──────────────┐    WebSocket    ┌──────────────┐
│    前端      │ ◄─────────────► │   FastAPI    │
│  (HTML/JS)   │                 │   后端服务    │
└──────────────┘                 └──────────────┘
      │                                │
      │  1. 连接 ws://host:port/ws     │
      │  2. 发送 {type:"start",...}    │
      │  3. 接收 payload + frame       │
      │  4. 发送 {type:"stop"}         │
      └────────────────────────────────┘
```

---

## 🔌 连接地址

| 算法 | WebSocket 地址 | HTTP 地址 |
|-----|---------------|-----------|
| 赏罚算法 | `ws://127.0.0.1:8000/ws` | `/parkingpayload` |
| ROI算法 | `ws://127.0.0.1:8000/ws_roi` | `/parkingpayload_roi` |

---

## 📥 输入 (前端 → 后端)

### 消息类型

| type | 参数 | 说明 |
|------|------|------|
| `start` | `source` | 启动检测 |
| `stop` | 无 | 停止检测 |

### 1. 启动检测

```json
{
  "type": "start",
  "source": "ws://127.0.0.1:8011/stream"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | 固定 `"start"` |
| `source` | string | ✅ | 视频源地址（支持 rtsp/http/ws/本地文件） |

### 2. 停止检测

```json
{ "type": "stop" }
```

---

## 📤 输出 (后端 → 前端)

### 消息类型

| type | 说明 | 后跟数据 |
|------|------|---------|
| `schema` | 首次连接返回字段定义 | JSON |
| `started` | 检测已启动 | JSON |
| `stopped` | 检测已停止 | JSON |
| `payload` | 检测结果（每帧） | JSON |
| `frame` | 带标注图像帧 | 二进制 JPEG |
| `error` | 错误信息 | JSON |

### 1. 检测结果 payload

```json
{
  "type": "payload",
  "ts": 1706540188.123,
  "payload": {
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
}
```

#### tracks 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `track_id` | int | 跟踪 ID（唯一标识目标） |
| `cls_id` | int | 类别 ID |
| `class_name` | string | 类别中文名（小汽车/面包车/卡车...） |
| `conf` | float | 检测置信度 0~1 |
| `bbox` | [x1,y1,x2,y2] | 边界框坐标 |
| `parked_frames` | int | 累计停车帧数（>0 表示已停车） |
| `panduan` | string\|null | 二阶段判定结果 |
| `status` | string | 最终状态 |

#### status 取值

| 值 | 含义 | 颜色建议 |
|----|------|---------|
| `"移动"` | 目标正在移动 | 🟢 绿色 |
| `"停车"` | 正在停车中，尚未判定 | 🟡 黄色 |
| `"合法停车"` | 停在合法区域 | 🟣 紫色 |
| `"违规停车"` | 停在违规区域 | 🔴 红色 |

### 2. 图像帧

收到 `{"type":"frame","ts":...}` 后，下一条消息为 **二进制 JPEG 图像**。

---

## 🎯 最小前端示例

### 纯 JavaScript (可直接运行)

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>违停检测 - 最小示例</title>
  <style>
    body { font-family: sans-serif; padding: 20px; background: #1a1a2e; color: #eee; }
    .box { display: flex; gap: 20px; margin-top: 20px; }
    img { max-width: 640px; border: 2px solid #333; border-radius: 8px; }
    pre { background: #16213e; padding: 15px; border-radius: 8px; max-height: 400px; overflow: auto; }
    button { padding: 10px 20px; margin-right: 10px; cursor: pointer; }
    .status { padding: 5px 10px; border-radius: 5px; display: inline-block; margin-left: 10px; }
    .connected { background: #2ecc71; }
    .disconnected { background: #e74c3c; }
  </style>
</head>
<body>

<h1>🚗 违规停车检测 <span id="status" class="status disconnected">未连接</span></h1>

<div>
  <input id="source" value="ws://127.0.0.1:8011/stream" placeholder="视频源地址" style="width: 300px; padding: 8px;">
  <button onclick="start()">▶️ 开始检测</button>
  <button onclick="stop()">⏹️ 停止检测</button>
</div>

<div class="box">
  <div>
    <h3>实时画面</h3>
    <img id="frame" alt="等待画面...">
  </div>
  <div>
    <h3>检测结果</h3>
    <pre id="result">等待连接...</pre>
  </div>
</div>

<script>
// ========== 核心代码 ==========
const WS_URL = 'ws://127.0.0.1:8000/ws_roi';  // 或 /ws (赏罚算法)

let ws = null;
let expectingFrame = false;

function start() {
  // 1. 建立 WebSocket 连接
  ws = new WebSocket(WS_URL);
  ws.binaryType = 'arraybuffer';
  
  ws.onopen = () => {
    setStatus('已连接', true);
    // 2. 发送启动消息
    ws.send(JSON.stringify({
      type: 'start',
      source: document.getElementById('source').value
    }));
  };
  
  ws.onmessage = (event) => {
    // 3. 接收消息
    if (typeof event.data === 'string') {
      const msg = JSON.parse(event.data);
      
      if (msg.type === 'payload') {
        // 显示检测结果
        document.getElementById('result').textContent = JSON.stringify(msg.payload, null, 2);
      }
      else if (msg.type === 'frame') {
        // 下一条消息是图像
        expectingFrame = true;
      }
    }
    else if (event.data instanceof ArrayBuffer && expectingFrame) {
      // 4. 显示图像帧
      expectingFrame = false;
      const blob = new Blob([event.data], { type: 'image/jpeg' });
      document.getElementById('frame').src = URL.createObjectURL(blob);
    }
  };
  
  ws.onclose = () => setStatus('已断开', false);
  ws.onerror = () => setStatus('连接错误', false);
}

function stop() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    // 5. 发送停止消息
    ws.send(JSON.stringify({ type: 'stop' }));
  }
  if (ws) ws.close();
  ws = null;
  setStatus('已断开', false);
}

function setStatus(text, connected) {
  const el = document.getElementById('status');
  el.textContent = text;
  el.className = 'status ' + (connected ? 'connected' : 'disconnected');
}
</script>

</body>
</html>
```

### 核心代码提取 (30行)

```javascript
// 1. 连接
const ws = new WebSocket('ws://127.0.0.1:8000/ws_roi');
ws.binaryType = 'arraybuffer';

// 2. 启动检测
ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'start',
    source: 'rtsp://your-camera/stream'
  }));
};

// 3. 接收结果
let expectingFrame = false;
ws.onmessage = (event) => {
  if (typeof event.data === 'string') {
    const msg = JSON.parse(event.data);
    if (msg.type === 'payload') {
      console.log('检测结果:', msg.payload);
      // 处理 msg.payload.tracks 显示检测框
    }
    if (msg.type === 'frame') expectingFrame = true;
  } else if (expectingFrame) {
    expectingFrame = false;
    const url = URL.createObjectURL(new Blob([event.data], {type:'image/jpeg'}));
    document.getElementById('frame').src = url;
  }
};

// 4. 停止检测
ws.send(JSON.stringify({ type: 'stop' }));
ws.close();
```

---

## 🎨 渲染指南

### 画框颜色

```javascript
function getColor(status) {
  switch(status) {
    case '违规停车': return '#ff4444';  // 红色
    case '合法停车': return '#bb44ff';  // 紫色
    case '停车':     return '#ffcc00';  // 黄色
    default:        return '#44ff44';  // 绿色(移动)
  }
}
```

### 在 Canvas 上绘制

```javascript
function drawTracks(ctx, tracks) {
  for (const [id, track] of Object.entries(tracks)) {
    const [x1, y1, x2, y2] = track.bbox;
    const color = getColor(track.status);
    
    // 画框
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(x1, y1, x2-x1, y2-y1);
    
    // 显示信息
    const label = `${track.class_name} #${track.track_id} ${track.status}`;
    ctx.fillStyle = color;
    ctx.fillRect(x1, y1-20, ctx.measureText(label).width+10, 20);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, x1+5, y1-5);
  }
}
```

---

## ❓ 常见问题

### Q: 如何切换算法？

```javascript
// ROI 算法（推荐固定摄像头）
const ws = new WebSocket('ws://127.0.0.1:8000/ws_roi');

// 赏罚算法（动态场景）
const ws = new WebSocket('ws://127.0.0.1:8000/ws');
```

### Q: 如何只接收 payload 不接收图像？

目前服务端会同时推送 frame，前端可选择忽略二进制消息。

### Q: 视频源支持哪些格式？

| 类型 | 示例 |
|-----|------|
| RTSP | `rtsp://user:pass@ip:554/stream` |
| HTTP | `http://ip:port/video.mp4` |
| WebSocket | `ws://127.0.0.1:8011/stream` |
| 本地文件 | `/path/to/video.mp4` |

---

## 📚 检测目标

本算法默认检测以下车辆类型：

| 类型 | 说明 |
|------|------|
| 小汽车 | 私家车、轿车等 |
| 面包车 | 商务车、MPV 等 |
| 卡车 | 货车、大型车辆 |

---

## 🔮 后续算法扩展

新算法集成后，只需添加新的 WebSocket 端点，输入输出格式保持一致：

```
/ws_fire    - 火焰检测
/ws_crowd   - 人群聚集检测
/ws_intrude - 人员闯入检测
```

所有算法的 `payload.tracks` 结构保持统一，仅 `status` 和 `class_name` 取值不同。
