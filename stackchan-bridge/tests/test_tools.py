from __future__ import annotations

import asyncio

from stackchan_bridge.adapters.home_assistant import HomeAssistantAdapter
from stackchan_bridge.server.device import BridgeDevice
from stackchan_bridge.server.sessions import SessionRecord
from stackchan_bridge.tools.registry import ToolContext, ToolRegistry


class DummyWebSocket:
    async def send_json(self, payload):
        self.last_json = payload

    async def send_bytes(self, payload):
        self.last_bytes = payload


def build_device(snapshot: bytes | None = None) -> BridgeDevice:
    record = SessionRecord(
        device_id="demo-1",
        websocket=DummyWebSocket(),
        protocol_mode="json",
        capabilities={
            "display": {"enabled": True},
            "audio": {"enabled": True},
            "motion": {"enabled": True},
            "camera": {"enabled": True, "snapshot_supported": True},
        },
    )
    record.latest_snapshot = snapshot
    return BridgeDevice(record)


def test_tool_registry_definitions_and_snapshot_request() -> None:
    async def run() -> None:
        registry = ToolRegistry(HomeAssistantAdapter(enabled=False))
        names = {tool.name for tool in registry.definitions()}
        assert "move_head" in names
        context = ToolContext(device=build_device(), home_assistant=registry.home_assistant)
        result = await registry.execute("capture_snapshot", {}, context)
        assert result.actions[0].kind == "capture_snapshot"

    asyncio.run(run())


def test_capture_snapshot_uses_cached_image() -> None:
    async def run() -> None:
        registry = ToolRegistry(HomeAssistantAdapter(enabled=False))
        context = ToolContext(device=build_device(b"jpeg"), home_assistant=registry.home_assistant)
        result = await registry.execute("capture_snapshot", {}, context)
        assert result.actions == []
        assert result.data["byte_length"] == 4

    asyncio.run(run())


def test_home_assistant_stub_returns_disabled() -> None:
    async def run() -> None:
        registry = ToolRegistry(HomeAssistantAdapter(enabled=False))
        context = ToolContext(device=build_device(), home_assistant=registry.home_assistant)
        result = await registry.execute(
            "trigger_home_assistant_service",
            {"domain": "light", "service": "turn_on", "data": {"entity_id": "light.test"}},
            context,
        )
        assert result.data["status"] == "disabled"

    asyncio.run(run())

