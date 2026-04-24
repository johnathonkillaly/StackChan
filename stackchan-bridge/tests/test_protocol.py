from __future__ import annotations

import asyncio

from stackchan_bridge.protocol.compat import CompatFrameType, build_frame, decode_frame, encode_frame
from stackchan_bridge.protocol.json_models import DeviceHelloEnvelope
from stackchan_bridge.server.sessions import SessionManager


class DummyWebSocket:
    async def send_json(self, payload):
        self.last_json = payload

    async def send_bytes(self, payload):
        self.last_bytes = payload


def test_json_hello_parses() -> None:
    envelope = DeviceHelloEnvelope.model_validate(
        {
            "type": "device.hello",
            "payload": {
                "device_id": "demo-1",
                "device_name": "Demo",
                "capabilities": {
                    "display": {"enabled": True, "width": 320, "height": 240, "color": True},
                    "audio": {"enabled": True, "sample_rate_hz": 16000},
                    "motion": {"enabled": True, "yaw_range": [-90, 90], "pitch_range": [-30, 30]},
                    "camera": {"enabled": True, "snapshot_supported": True, "stream_supported": False},
                },
            },
        }
    )
    assert envelope.payload.device_id == "demo-1"
    assert envelope.payload.capabilities.motion.enabled is True


def test_compat_frame_round_trip() -> None:
    frame = build_frame(CompatFrameType.TEXT_MESSAGE, {"name": "Bridge", "content": "Hello"})
    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)
    assert decoded.frame_type == CompatFrameType.TEXT_MESSAGE
    assert b"Hello" in decoded.payload


def test_session_manager_registers_json_and_compat() -> None:
    async def run() -> None:
        manager = SessionManager()
        hello = DeviceHelloEnvelope.model_validate(
            {
                "type": "device.hello",
                "payload": {"device_id": "demo-1"},
            }
        )
        json_session = await manager.register_json_session("demo-1", DummyWebSocket(), hello.payload)
        compat_session = await manager.register_compat_session("AA:BB", DummyWebSocket())
        assert json_session.protocol_mode == "json"
        assert compat_session.protocol_mode == "compat"

    asyncio.run(run())

