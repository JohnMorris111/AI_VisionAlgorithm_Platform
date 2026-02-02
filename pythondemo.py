import asyncio
import websockets
import json
import cv2
import numpy as np

async def main():
    uri = "ws://127.0.0.1:8000/ws_roi"
    
    async with websockets.connect(uri) as ws:
        # 先停止之前可能存在的流
        await ws.send(json.dumps({"type": "stop"}))
        
        # 等待 stopped 确认或超时
        try:
            await asyncio.wait_for(wait_for_stopped(ws), timeout=2.0)
        except asyncio.TimeoutError:
            pass  # 可能本来就没在运行
        
        # 启动检测
        await ws.send(json.dumps({
            "type": "start",
            "source": "/Volumes/John/yolov8-visdrone/aiparking125Beta2RoiAiRepotBeta/source/车辆违停.mp4"
        }))
        
        # 接收结果
        while True:
            response = await ws.recv()
            
            # 二进制消息 = 视频帧 (JPEG)
            if isinstance(response, bytes):
                arr = np.frombuffer(response, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    cv2.imshow("AI违停检测", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                continue
            
            # JSON 消息
            data = json.loads(response)
            
            if data["type"] == "payload":
                print(json.dumps(data["payload"], indent=2, ensure_ascii=False))
                tracks = data["payload"]["tracks"]
                for track_id, info in tracks.items():
                    print(f"车辆 {track_id}: {info['status']}")
            
            elif data["type"] == "frame":
                pass
            
            elif data["type"] == "started":
                print(f"检测已启动: {data.get('algorithm', 'unknown')}")
            
            elif data["type"] == "error":
                print(f"错误: {data.get('message') or data.get('error')}")
                break
            
            elif data["type"] == "stopped":
                print("检测已停止")
                break
        
        cv2.destroyAllWindows()


async def wait_for_stopped(ws):
    """等待 stopped 消息"""
    while True:
        response = await ws.recv()
        if isinstance(response, str):
            data = json.loads(response)
            if data["type"] == "stopped":
                return


asyncio.run(main())