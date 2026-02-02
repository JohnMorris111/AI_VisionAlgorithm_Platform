import asyncio
import websockets
import json
import cv2
import numpy as np

async def main():
    uri = "ws://127.0.0.1:8000/ws"
    
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected to server!")
            
            # 1. 启动检测
            print("🚀 Sending start command...")
            await ws.send(json.dumps({
                "type": "start",
                # 容器内部路径 (通过 -v 挂载映射)
                "source": "/app/source/侵占消防通道.mp4",
                "conf_thres": 0.65,
                "frame_gap": 2
            }))
            
            # 2. 接收 loop
            frame_count = 0
            while True:
                try:
                    msg = await ws.recv()
                except websockets.exceptions.ConnectionClosed:
                    print("❌ Connection closed by server")
                    break
                
                # 二进制消息 = 视频帧 (JPEG)
                if isinstance(msg, bytes):
                    frame_count += 1
                    # print(f"Received frame {frame_count}, size: {len(msg)} bytes")
                    nparr = np.frombuffer(msg, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        cv2.imshow("Preview", frame)
                        # MAC系统必须有 waitKey 才能刷新窗口
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            print("User pressed 'q', stopping...")
                            break
                    else:
                        print("⚠️ Failed to decode frame")
                    continue
                
                # JSON 消息
                try:
                    data = json.loads(msg)
                    # print(f"Received JSON: {data.get('type')}")
                except json.JSONDecodeError:
                    print("⚠️ Received invalid JSON")
                    continue
                
                msg_type = data.get("type")
                
                if msg_type == "payload":
                    # 处理检测结果
                    # 兼容不同接口返回的 payload 结构
                    payload = data.get('payload', {})
                    lanes = payload.get('lanes', [])
                    stats = payload.get('stats', {})
                    polluted_count = stats.get('occupied_lanes', 0)
                    
                    print(f"Frame {data.get('frame_idx', '?')}: {polluted_count} lanes polluted | Lanes: {len(lanes)}")
                    
                elif msg_type == "error":
                    print(f"❌ Error from server: {data.get('message')}")
                    # break # 遇到错误不一定退出，看情况
                    
                elif msg_type == "stopped":
                    print("⏹️ Server reported stopped")
                    break
                    
                elif msg_type == "started":
                    print("✅ Server confirmed started")

    except Exception as e:
        print(f"💥 Critical Error: {e}")
        import traceback
        traceback.print_exc()

    print("Closing windows...")
    cv2.destroyAllWindows()

asyncio.run(main())