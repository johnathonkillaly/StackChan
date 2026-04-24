from __future__ import annotations

import argparse
import asyncio
import base64
import json
from typing import Any

import websockets


def build_hello(device_id: str) -> dict[str, Any]:
    return {
        "type": "device.hello",
        "payload": {
            "device_id": device_id,
            "device_name": "Fake StackChan",
            "capabilities": {
                "display": {"enabled": True, "width": 320, "height": 240, "color": True},
                "audio": {"enabled": True, "sample_rate_hz": 16000},
                "motion": {"enabled": True, "yaw_range": [-90, 90], "pitch_range": [-30, 30]},
                "camera": {"enabled": True, "snapshot_supported": True, "stream_supported": False},
            },
        },
    }


async def run_client(url: str, device_id: str) -> None:
    async with websockets.connect(f"{url.rstrip('/')}/ws/devices/{device_id}") as websocket:
        await websocket.send(json.dumps(build_hello(device_id)))
        print(f"[fake-device] connected as {device_id}")

        async for message in websocket:
            payload = json.loads(message)
            print(f"[fake-device] <- {json.dumps(payload, indent=2)}")

            if payload.get("type") != "server.action":
                continue

            action = payload["action"]
            kind = action["kind"]
            if kind == "capture_snapshot":
                fake_jpeg = base64.b64encode(b"fake-jpeg-bytes").decode("ascii")
                await websocket.send(
                    json.dumps(
                        {
                            "type": "device.event",
                            "event": {
                                "event_type": "camera.snapshot",
                                "data": {"jpeg_base64": fake_jpeg},
                            },
                        }
                    )
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake StackChan JSON bridge client.")
    parser.add_argument("--url", default="ws://127.0.0.1:8000", help="Bridge base WebSocket URL.")
    parser.add_argument("--device-id", default="demo-1", help="Device id to register.")
    args = parser.parse_args()
    asyncio.run(run_client(args.url, args.device_id))


if __name__ == "__main__":
    main()

