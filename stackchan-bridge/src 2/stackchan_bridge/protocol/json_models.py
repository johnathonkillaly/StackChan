from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class DisplayCapability(BaseModel):
    enabled: bool = False
    width: int | None = None
    height: int | None = None
    color: bool = True


class AudioCapability(BaseModel):
    enabled: bool = False
    sample_rate_hz: int | None = None


class MotionCapability(BaseModel):
    enabled: bool = False
    yaw_range: tuple[int, int] | None = None
    pitch_range: tuple[int, int] | None = None


class CameraCapability(BaseModel):
    enabled: bool = False
    snapshot_supported: bool = False
    stream_supported: bool = False


class DeviceCapabilities(BaseModel):
    display: DisplayCapability = Field(default_factory=DisplayCapability)
    audio: AudioCapability = Field(default_factory=AudioCapability)
    motion: MotionCapability = Field(default_factory=MotionCapability)
    camera: CameraCapability = Field(default_factory=CameraCapability)


class DeviceHello(BaseModel):
    device_id: str
    device_name: str | None = None
    session_id: str | None = None
    capabilities: DeviceCapabilities = Field(default_factory=DeviceCapabilities)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceHelloEnvelope(BaseModel):
    type: Literal["device.hello"] = "device.hello"
    payload: DeviceHello


class DeviceEvent(BaseModel):
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeviceEventEnvelope(BaseModel):
    type: Literal["device.event"] = "device.event"
    event: DeviceEvent


class DeviceAck(BaseModel):
    action_id: str | None = None
    status: Literal["ok", "error"] = "ok"
    detail: str | None = None


class DeviceAckEnvelope(BaseModel):
    type: Literal["device.ack"] = "device.ack"
    ack: DeviceAck


class DeviceError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DeviceErrorEnvelope(BaseModel):
    type: Literal["device.error"] = "device.error"
    error: DeviceError


class MoveHeadAction(BaseModel):
    kind: Literal["move_head"] = "move_head"
    yaw: int
    pitch: int


class SetExpressionAction(BaseModel):
    kind: Literal["set_expression"] = "set_expression"
    name: str


class SpeakTextAction(BaseModel):
    kind: Literal["speak_text"] = "speak_text"
    text: str


class DisplayRenderAction(BaseModel):
    kind: Literal["display_render"] = "display_render"
    text: str | None = None
    image_url: str | None = None
    layout: str | None = None


class SetLedsAction(BaseModel):
    kind: Literal["set_leds"] = "set_leds"
    left_rgb_color: str
    right_rgb_color: str
    duration_ms: int = 800


class CaptureSnapshotAction(BaseModel):
    kind: Literal["capture_snapshot"] = "capture_snapshot"


ActionModel = Annotated[
    MoveHeadAction
    | SetExpressionAction
    | SpeakTextAction
    | DisplayRenderAction
    | SetLedsAction
    | CaptureSnapshotAction,
    Field(discriminator="kind"),
]


class ServerActionEnvelope(BaseModel):
    type: Literal["server.action"] = "server.action"
    action_id: str = Field(default_factory=lambda: str(uuid4()))
    action: ActionModel


class ServerAckEnvelope(BaseModel):
    type: Literal["server.ack"] = "server.ack"
    message: str


class ServerErrorEnvelope(BaseModel):
    type: Literal["server.error"] = "server.error"
    error: DeviceError


class DeviceSummary(BaseModel):
    device_id: str
    device_name: str | None = None
    protocol_mode: Literal["json", "compat"]
    capabilities: DeviceCapabilities
    connected: bool = True
    stale: bool = False
    last_heartbeat: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    device_id: str
    text: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    device_id: str
    text: str
    actions_sent: list[str] = Field(default_factory=list)
    tool_results: list[str] = Field(default_factory=list)

