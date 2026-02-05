import asyncio
import websockets
import json
import cv2
import numpy as np


async def main():
    uri = "ws://127.0.0.1:8000/ws_roi"

    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as ws:
            print("✅ Connected to server!")

            # 1. 启动检测
            print("🚀 Sending start command...")
            await ws.send(json.dumps({
                "type": "start",
                "source": "rtsp://your-camera/stream"
            }))

            # 2. 接收 loop
            while True:
                try:
                    msg = await ws.recv()
                except websockets.exceptions.ConnectionClosed:
                    print("❌ Connection closed by server")
                    break

                # 二进制消息 = 视频帧 (JPEG)
                if isinstance(msg, bytes):
                    nparr = np.frombuffer(msg, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        cv2.imshow("Preview", frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            print("User pressed 'q', stopping...")
                            break
                    else:
                        print("⚠️ Failed to decode frame")
                    continue

                # JSON 消息
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    print("⚠️ Received invalid JSON")
                    continue

                msg_type = data.get("type")

                if msg_type == "payload":
                    payload = data.get("payload") or data.get("data") or {}
                    frame_index = payload.get("frame_index", payload.get("frame", "?"))
                    tracks = payload.get("tracks", {})
                    print(f"Frame {frame_index}: {len(tracks)} tracks")
                    for track_id, info in tracks.items():
                        status = info.get("status", "unknown")
                        area = info.get("parking_area", {})
                        area_name = area.get("area_name", "未命中停车区域")
                        area_type = area.get("area_type", "unknown")
                        print(f"  - #{track_id}: {status} | {area_name} ({area_type})")

                elif msg_type == "error":
                    print(f"❌ Error from server: {data.get('message') or data.get('error')}")

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
