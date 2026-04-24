from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from stackchan_bridge.protocol.json_models import DeviceCapabilities, DeviceHello, DeviceSummary


ProtocolMode = Literal["json", "compat"]


@dataclass(slots=True)
class SessionRecord:
    device_id: str
    websocket: Any
    protocol_mode: ProtocolMode
    capabilities: DeviceCapabilities
    device_name: str | None = None
    auth_header: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(UTC))
    latest_snapshot: bytes | None = None
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    connected: bool = True

    def summary(self, stale_after_seconds: int) -> DeviceSummary:
        stale = datetime.now(UTC) - self.last_heartbeat > timedelta(seconds=stale_after_seconds)
        return DeviceSummary(
            device_id=self.device_id,
            device_name=self.device_name,
            protocol_mode=self.protocol_mode,
            capabilities=self.capabilities,
            connected=self.connected,
            stale=stale,
            last_heartbeat=self.last_heartbeat,
            metadata=self.metadata,
        )


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}

    async def register_json_session(self, device_id: str, websocket: Any, hello: DeviceHello, auth_header: str | None = None) -> SessionRecord:
        capabilities = DeviceCapabilities.model_validate(getattr(hello, "capabilities", {}))
        record = SessionRecord(
            device_id=device_id,
            websocket=websocket,
            protocol_mode="json",
            capabilities=capabilities,
            device_name=getattr(hello, "device_name", None),
            auth_header=auth_header,
            metadata=dict(getattr(hello, "metadata", {})),
        )
        self._sessions[device_id] = record
        return record

    async def register_compat_session(
        self,
        device_id: str,
        websocket: Any,
        auth_header: str | None = None,
        *,
        reported_mac: str | None = None,
    ) -> SessionRecord:
        capabilities = DeviceCapabilities.model_validate(
            {
                "display": {"enabled": True, "width": 320, "height": 240, "color": True},
                "audio": {"enabled": True, "sample_rate_hz": 16000},
                "motion": {"enabled": True, "yaw_range": [-180, 180], "pitch_range": [-90, 90]},
                "camera": {"enabled": True, "snapshot_supported": True, "stream_supported": True},
            }
        )
        metadata: dict[str, Any] = {"compat_session": True}
        if reported_mac:
            metadata["compat_mac"] = reported_mac
        record = SessionRecord(
            device_id=device_id,
            websocket=websocket,
            protocol_mode="compat",
            capabilities=capabilities,
            device_name=reported_mac or device_id,
            auth_header=auth_header,
            metadata=metadata,
        )
        self._sessions[device_id] = record
        return record

    def get(self, device_id: str) -> SessionRecord | None:
        return self._sessions.get(device_id)

    def list_summaries(self, stale_after_seconds: int) -> list[DeviceSummary]:
        return [record.summary(stale_after_seconds) for record in self._sessions.values()]

    def touch(self, device_id: str) -> None:
        record = self._sessions.get(device_id)
        if record:
            record.last_heartbeat = datetime.now(UTC)

    def store_snapshot(self, device_id: str, snapshot: bytes) -> None:
        record = self._sessions.get(device_id)
        if record:
            record.latest_snapshot = snapshot
            record.last_heartbeat = datetime.now(UTC)

    def update_metadata(self, device_id: str, **metadata: Any) -> None:
        record = self._sessions.get(device_id)
        if record:
            record.metadata.update(metadata)
            record.last_heartbeat = datetime.now(UTC)

    def expire_stale(self, stale_after_seconds: int) -> list[str]:
        cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
        stale_ids: list[str] = []
        for device_id, record in self._sessions.items():
            if record.last_heartbeat < cutoff:
                stale_ids.append(device_id)
        return stale_ids

    def remove(self, device_id: str, websocket: Any | None = None) -> None:
        record = self._sessions.get(device_id)
        if not record:
            return
        if websocket is not None and websocket is not record.websocket:
            return
        record.connected = False
        self._sessions.pop(device_id, None)
