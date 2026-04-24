from __future__ import annotations

import asyncio

from stackchan_bridge.adapters.home_assistant import HomeAssistantAdapter
from stackchan_bridge.rover.linux_controller import FakeBridgeClient, RoverLinuxController, SnapshotPlaceholderObservationProvider
from stackchan_bridge.server.device import BridgeDevice
from stackchan_bridge.server.sessions import SessionRecord
from stackchan_bridge.tools.registry import ToolContext, ToolRegistry


class DummyWebSocket:
    async def send_json(self, payload):
        self.last_json = payload

    async def send_bytes(self, payload):
        self.last_bytes = payload


def build_device(*, snapshot: bytes | None = None, hint: str | None = None) -> BridgeDevice:
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
    if hint:
        record.metadata["rover_observation_hint"] = hint
    return BridgeDevice(record)


def test_rover_tools_return_unavailable_when_disabled() -> None:
    async def run() -> None:
        registry = ToolRegistry(HomeAssistantAdapter(enabled=False))
        context = ToolContext(device=build_device(), home_assistant=registry.home_assistant)
        result = await registry.execute("rover_status", {}, context)
        assert result.data["status"] == "unavailable"

    asyncio.run(run())


def test_rover_observe_step_turns_with_hint() -> None:
    async def run() -> None:
        bridge = FakeBridgeClient()
        controller = RoverLinuxController(
            bridge_client=bridge,
            observation_provider=SnapshotPlaceholderObservationProvider(),
        )
        registry = ToolRegistry(HomeAssistantAdapter(enabled=False), rover_controller=controller)
        context = ToolContext(
            device=build_device(hint="blocked_left"),
            home_assistant=registry.home_assistant,
            rover_controller=controller,
        )
        result = await registry.execute("rover_observe_step", {}, context)
        assert result.data["decision"]["action"] == "turn"
        assert [entry["method"] for entry in bridge.call_log] == [
            "motor_stop",
            "get_status",
            "motor_turn",
            "get_status",
            "motor_stop",
            "get_status",
        ]

    asyncio.run(run())


def test_rover_observe_step_requests_snapshot_when_unknown() -> None:
    async def run() -> None:
        bridge = FakeBridgeClient()
        controller = RoverLinuxController(
            bridge_client=bridge,
            observation_provider=SnapshotPlaceholderObservationProvider(),
        )
        registry = ToolRegistry(HomeAssistantAdapter(enabled=False), rover_controller=controller)
        context = ToolContext(
            device=build_device(snapshot=None),
            home_assistant=registry.home_assistant,
            rover_controller=controller,
        )
        result = await registry.execute("rover_observe_step", {}, context)
        assert result.data["observation"]["state"] == "unknown"
        assert result.actions[0].kind == "capture_snapshot"

    asyncio.run(run())
