from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from stackchan_bridge.agent.types import LLMResponse, ToolCall, ToolDefinition
from stackchan_bridge.protocol.json_models import DeviceHello, SpeakTextAction
from stackchan_bridge.server.app import create_app
from stackchan_bridge.server.config import Settings
from stackchan_bridge.server.device import BridgeDevice
from stackchan_bridge.server.sessions import SessionManager


class ScriptedLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages: list[dict], tools: list[ToolDefinition]) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(id="1", name="set_expression", arguments={"name": "happy"}),
                    ToolCall(id="2", name="speak_text", arguments={"text": "Hello from the bridge"}),
                ],
            )
        return LLMResponse(content="Hello from the bridge")


class DummySocket:
    def __init__(self) -> None:
        self.sent_json: list[dict] = []
        self.sent_bytes: list[bytes] = []

    async def send_json(self, payload: dict) -> None:
        self.sent_json.append(payload)

    async def send_bytes(self, payload: bytes) -> None:
        self.sent_bytes.append(payload)


def demo_settings() -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8000,
        log_level="INFO",
        session_stale_seconds=30,
        compat_enabled=True,
        agent_max_iterations=3,
        lm_studio_base_url="http://127.0.0.1:1234/v1",
        lm_studio_model="demo",
        lm_studio_api_key="lm-studio",
        home_assistant_enabled=False,
    )


def test_post_chat_emits_actions_to_json_websocket() -> None:
    app = create_app(settings=demo_settings(), llm_adapter=ScriptedLLM())
    client = TestClient(app)

    with client.websocket_connect("/ws/devices/demo-1") as websocket:
        websocket.send_json(
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
        ack = websocket.receive_json()
        assert ack["type"] == "server.ack"

        response = client.post("/api/chat", json={"device_id": "demo-1", "text": "Say hello"})
        assert response.status_code == 200
        action_one = websocket.receive_json()
        action_two = websocket.receive_json()
        assert action_one["action"]["kind"] == "set_expression"
        assert action_two["action"]["kind"] == "speak_text"


def test_multi_device_dispatch_stays_isolated() -> None:
    async def run() -> None:
        manager = SessionManager()
        hello = DeviceHello.model_validate(
            {
                "device_id": "demo-1",
                "capabilities": {
                    "display": {"enabled": True},
                    "audio": {"enabled": True},
                    "motion": {"enabled": True},
                    "camera": {"enabled": True},
                },
            }
        )
        other = DeviceHello.model_validate(
            {
                "device_id": "demo-2",
                "capabilities": {
                    "display": {"enabled": True},
                    "audio": {"enabled": True},
                    "motion": {"enabled": True},
                    "camera": {"enabled": True},
                },
            }
        )
        ws1 = DummySocket()
        ws2 = DummySocket()
        await manager.register_json_session("demo-1", ws1, hello)
        await manager.register_json_session("demo-2", ws2, other)
        device = BridgeDevice(manager.get("demo-1"))
        await device.dispatch_actions([SpeakTextAction(text="hi")])
        assert len(ws1.sent_json) == 1
        assert ws2.sent_json == []

    asyncio.run(run())


def test_stale_session_is_reported() -> None:
    async def run() -> None:
        manager = SessionManager()
        ws = DummySocket()
        await manager.register_compat_session("AA:BB", ws)
        session = manager.get("AA:BB")
        assert session is not None
        session.last_heartbeat = datetime.now(UTC) - timedelta(seconds=120)
        stale = manager.expire_stale(30)
        assert "AA:BB" in stale

    asyncio.run(run())


def test_compat_websocket_accepts_missing_mac() -> None:
    app = create_app(settings=demo_settings(), llm_adapter=ScriptedLLM())
    client = TestClient(app)

    with client.websocket_connect("/stackChan/ws?deviceType=StackChan") as websocket:
        devices = client.get("/api/devices")
        assert devices.status_code == 200
        payload = devices.json()
        assert len(payload) == 1
        assert payload[0]["protocol_mode"] == "compat"
        assert payload[0]["device_id"].startswith("compat-")
