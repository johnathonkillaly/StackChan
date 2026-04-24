from __future__ import annotations

import json
import struct
from base64 import b64encode
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field

from stackchan_bridge.protocol.json_models import (
    CaptureSnapshotAction,
    DisplayRenderAction,
    MoveHeadAction,
    SetExpressionAction,
    SetLedsAction,
    SpeakTextAction,
)


class CompatFrameType(IntEnum):
    OPUS = 0x01
    JPEG = 0x02
    CONTROL_AVATAR = 0x03
    CONTROL_MOTION = 0x04
    START_CAMERA_STREAM = 0x05
    STOP_CAMERA_STREAM = 0x06
    TEXT_MESSAGE = 0x07
    REQUEST_CALL = 0x09
    DECLINE_CALL = 0x0A
    ACCEPT_CALL = 0x0B
    END_CALL = 0x0C
    SET_DEVICE_NAME = 0x0D
    GET_DEVICE_NAME = 0x0E
    HEARTBEAT_PING = 0x10
    HEARTBEAT_PONG = 0x11
    VIDEO_MODE_ON = 0x12
    VIDEO_MODE_OFF = 0x13
    DANCE_SEQUENCE = 0x14
    GET_AVATAR_POSTURE = 0x15
    DEVICE_OFFLINE = 0x16
    DEVICE_ONLINE = 0x17
    START_AUDIO_STREAM = 0x18
    STOP_AUDIO_STREAM = 0x19


class CompatFrame(BaseModel):
    frame_type: CompatFrameType
    payload: bytes = Field(default_factory=bytes)


class CompatTextPayload(BaseModel):
    name: str
    content: str


EXPRESSION_PRESETS: dict[str, dict[str, Any]] = {
    "neutral": {
        "leftEye": {"x": -40, "y": -10, "rotation": 0, "weight": 15, "size": 28},
        "rightEye": {"x": 40, "y": -10, "rotation": 0, "weight": 15, "size": 28},
        "mouth": {"x": 0, "y": 38, "rotation": 0, "weight": 10, "size": 24},
    },
    "happy": {
        "leftEye": {"x": -40, "y": -14, "rotation": -8, "weight": 18, "size": 24},
        "rightEye": {"x": 40, "y": -14, "rotation": 8, "weight": 18, "size": 24},
        "mouth": {"x": 0, "y": 40, "rotation": 0, "weight": 18, "size": 34},
    },
    "sad": {
        "leftEye": {"x": -40, "y": -2, "rotation": 10, "weight": 12, "size": 22},
        "rightEye": {"x": 40, "y": -2, "rotation": -10, "weight": 12, "size": 22},
        "mouth": {"x": 0, "y": 46, "rotation": 0, "weight": 8, "size": 18},
    },
    "surprised": {
        "leftEye": {"x": -40, "y": -10, "rotation": 0, "weight": 24, "size": 34},
        "rightEye": {"x": 40, "y": -10, "rotation": 0, "weight": 24, "size": 34},
        "mouth": {"x": 0, "y": 40, "rotation": 0, "weight": 22, "size": 28},
    },
}


def encode_frame(frame: CompatFrame) -> bytes:
    header = struct.pack(">BI", int(frame.frame_type), len(frame.payload))
    return header + frame.payload


def decode_frame(data: bytes) -> CompatFrame:
    if len(data) < 5:
        raise ValueError("Compat frame must contain at least 5 bytes.")
    frame_type = CompatFrameType(data[0])
    payload_len = struct.unpack(">I", data[1:5])[0]
    payload = data[5:]
    if len(payload) != payload_len:
        raise ValueError("Compat frame payload length mismatch.")
    return CompatFrame(frame_type=frame_type, payload=payload)


def build_frame(frame_type: CompatFrameType, payload: bytes | str | dict[str, Any] | list[Any] | None = None) -> CompatFrame:
    if payload is None:
        encoded = b""
    elif isinstance(payload, bytes):
        encoded = payload
    elif isinstance(payload, str):
        encoded = payload.encode("utf-8")
    else:
        encoded = json.dumps(payload).encode("utf-8")
    return CompatFrame(frame_type=frame_type, payload=encoded)


def parse_text_payload(payload: bytes) -> CompatTextPayload | None:
    if not payload:
        return None
    data = json.loads(payload.decode("utf-8"))
    return CompatTextPayload.model_validate(data)


def frame_to_event(frame: CompatFrame) -> dict[str, Any]:
    payload_text = ""
    if frame.payload:
        try:
            payload_text = frame.payload.decode("utf-8")
        except UnicodeDecodeError:
            payload_text = b64encode(frame.payload).decode("ascii")

    if frame.frame_type == CompatFrameType.TEXT_MESSAGE and frame.payload:
        parsed = parse_text_payload(frame.payload)
        return {"event_type": "compat.text_message", "data": parsed.model_dump()}
    if frame.frame_type == CompatFrameType.JPEG:
        return {
            "event_type": "camera.snapshot",
            "data": {
                "jpeg_base64": b64encode(frame.payload).decode("ascii"),
                "byte_length": len(frame.payload),
            },
        }

    return {
        "event_type": f"compat.{frame.frame_type.name.lower()}",
        "data": {
            "payload_text": payload_text,
            "byte_length": len(frame.payload),
        },
    }


def action_to_frames(
    action: MoveHeadAction
    | SetExpressionAction
    | SpeakTextAction
    | DisplayRenderAction
    | SetLedsAction
    | CaptureSnapshotAction,
    *,
    speaker_name: str = "Bridge",
) -> list[CompatFrame]:
    if isinstance(action, MoveHeadAction):
        payload = {
            "yawServo": {"angle": action.yaw},
            "pitchServo": {"angle": action.pitch},
        }
        return [build_frame(CompatFrameType.CONTROL_MOTION, payload)]

    if isinstance(action, SetExpressionAction):
        payload = EXPRESSION_PRESETS.get(action.name.lower(), EXPRESSION_PRESETS["neutral"])
        return [build_frame(CompatFrameType.CONTROL_AVATAR, payload)]

    if isinstance(action, SpeakTextAction):
        payload = CompatTextPayload(name=speaker_name, content=action.text).model_dump()
        return [build_frame(CompatFrameType.TEXT_MESSAGE, payload)]

    if isinstance(action, DisplayRenderAction):
        if action.text:
            payload = CompatTextPayload(name=speaker_name, content=action.text).model_dump()
            return [build_frame(CompatFrameType.TEXT_MESSAGE, payload)]
        return [build_frame(CompatFrameType.CONTROL_AVATAR, EXPRESSION_PRESETS["neutral"])]

    if isinstance(action, SetLedsAction):
        payload = [
            {
                "leftRgbColor": action.left_rgb_color,
                "rightRgbColor": action.right_rgb_color,
                "durationMs": action.duration_ms,
            }
        ]
        return [build_frame(CompatFrameType.DANCE_SEQUENCE, payload)]

    if isinstance(action, CaptureSnapshotAction):
        return [build_frame(CompatFrameType.START_CAMERA_STREAM)]

    raise TypeError(f"Unsupported action kind: {action!r}")

