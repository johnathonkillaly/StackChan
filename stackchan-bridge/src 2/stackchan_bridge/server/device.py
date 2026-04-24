from __future__ import annotations

from typing import Any

from stackchan_bridge.protocol.compat import action_to_frames, encode_frame
from stackchan_bridge.protocol.json_models import (
    ActionModel,
    CaptureSnapshotAction,
    DisplayRenderAction,
    MoveHeadAction,
    ServerActionEnvelope,
    SetExpressionAction,
    SetLedsAction,
    SpeakTextAction,
)
from stackchan_bridge.server.sessions import SessionRecord


class BridgeDevice:
    def __init__(self, record: SessionRecord, *, speaker_name: str = "Bridge") -> None:
        self.record = record
        self.speaker_name = speaker_name

    @property
    def latest_snapshot(self) -> bytes | None:
        return self.record.latest_snapshot

    def supports(self, action: ActionModel) -> bool:
        capabilities = self.record.capabilities
        if isinstance(action, (MoveHeadAction,)):
            return capabilities.motion.enabled
        if isinstance(action, (SetExpressionAction, DisplayRenderAction, SetLedsAction)):
            return capabilities.display.enabled
        if isinstance(action, SpeakTextAction):
            return capabilities.audio.enabled
        if isinstance(action, CaptureSnapshotAction):
            return capabilities.camera.enabled
        return True

    async def dispatch_actions(self, actions: list[ActionModel]) -> list[str]:
        sent: list[str] = []
        for action in actions:
            if not self.supports(action):
                continue
            if self.record.protocol_mode == "json":
                await self._send_json_action(action)
            else:
                await self._send_compat_action(action)
            sent.append(action.kind)
        return sent

    async def _send_json_action(self, action: ActionModel) -> None:
        envelope = ServerActionEnvelope(action=action)
        async with self.record.send_lock:
            await self.record.websocket.send_json(envelope.model_dump(mode="json"))

    async def _send_compat_action(self, action: ActionModel) -> None:
        frames = action_to_frames(action, speaker_name=self.speaker_name)
        async with self.record.send_lock:
            for frame in frames:
                await self.record.websocket.send_bytes(encode_frame(frame))

