from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from stackchan_bridge.protocol.compat import CompatFrameType, build_frame, decode_frame, encode_frame, frame_to_event
from stackchan_bridge.protocol.json_models import (
    DeviceAckEnvelope,
    DeviceErrorEnvelope,
    DeviceEventEnvelope,
    DeviceHelloEnvelope,
    ServerAckEnvelope,
    ServerErrorEnvelope,
)


logger = logging.getLogger(__name__)
router = APIRouter()


def _context(websocket: WebSocket):
    return websocket.app.state.context


@router.websocket("/ws/devices/{device_id}")
async def json_device_ws(websocket: WebSocket, device_id: str) -> None:
    ctx = _context(websocket)
    await websocket.accept()
    session = None
    auth_header = websocket.headers.get("authorization")

    try:
        while True:
            payload = await websocket.receive_json()
            message_type = payload.get("type")

            if message_type == "device.hello":
                hello = DeviceHelloEnvelope.model_validate(payload)
                session = await ctx.sessions.register_json_session(device_id, websocket, hello.payload, auth_header)
                await websocket.send_json(ServerAckEnvelope(message=f"registered {device_id}").model_dump(mode="json"))
                continue

            if session is None:
                await websocket.send_json(
                    ServerErrorEnvelope(
                        error={"code": "missing_hello", "message": "device.hello is required before events."}
                    ).model_dump(mode="json")
                )
                continue

            if message_type == "device.event":
                event = DeviceEventEnvelope.model_validate(payload)
                ctx.sessions.touch(device_id)
                await _handle_json_event(ctx, device_id, event)
                await websocket.send_json(ServerAckEnvelope(message=f"received {event.event.event_type}").model_dump(mode="json"))
                continue

            if message_type == "device.ack":
                ack = DeviceAckEnvelope.model_validate(payload)
                ctx.sessions.update_metadata(device_id, last_ack=ack.ack.model_dump(mode="json"))
                continue

            if message_type == "device.error":
                error = DeviceErrorEnvelope.model_validate(payload)
                ctx.sessions.update_metadata(device_id, last_error=error.error.model_dump(mode="json"))
                continue

            await websocket.send_json(
                ServerErrorEnvelope(
                    error={"code": "unknown_message_type", "message": f"Unsupported message type {message_type}"}
                ).model_dump(mode="json")
            )
    except WebSocketDisconnect:
        logger.info("json websocket disconnected")
    finally:
        ctx.sessions.remove(device_id, websocket)


@router.websocket("/stackChan/ws")
async def compat_device_ws(websocket: WebSocket) -> None:
    ctx = _context(websocket)
    device_type = websocket.query_params.get("deviceType")
    mac = websocket.query_params.get("mac")
    if not ctx.settings.compat_enabled:
        await websocket.close(code=1008)
        return
    if device_type != "StackChan":
        await websocket.accept()
        await websocket.close(code=1008)
        return

    await websocket.accept()
    auth_header = websocket.headers.get("authorization")
    device_id = _resolve_compat_device_id(websocket, mac=mac, auth_header=auth_header)
    await ctx.sessions.register_compat_session(device_id, websocket, auth_header, reported_mac=mac)

    try:
        while True:
            packet = await websocket.receive()
            if packet["type"] == "websocket.disconnect":
                break

            if text := packet.get("text"):
                ctx.sessions.touch(device_id)
                ctx.sessions.update_metadata(device_id, last_text_message=text)
                continue

            data = packet.get("bytes")
            if not data:
                continue

            frame = decode_frame(data)
            ctx.sessions.touch(device_id)
            await _handle_compat_frame(ctx, device_id, websocket, frame)
    except WebSocketDisconnect:
        logger.info("compat websocket disconnected")
    finally:
        ctx.sessions.remove(device_id, websocket)


def _resolve_compat_device_id(websocket: WebSocket, *, mac: str | None, auth_header: str | None) -> str:
    if mac:
        return mac

    client_host = websocket.client.host if websocket.client else "unknown-client"
    digest_source = auth_header or client_host
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
    return f"compat-{digest}"


async def _handle_json_event(ctx: Any, device_id: str, event: DeviceEventEnvelope) -> None:
    if event.event.event_type == "camera.snapshot":
        encoded = event.event.data.get("jpeg_base64")
        if encoded:
            ctx.sessions.store_snapshot(device_id, base64.b64decode(encoded))
        return
    ctx.sessions.update_metadata(device_id, last_event=event.event.model_dump(mode="json"))


async def _handle_compat_frame(ctx: Any, device_id: str, websocket: WebSocket, frame: Any) -> None:
    if frame.frame_type == CompatFrameType.HEARTBEAT_PING:
        pong = build_frame(CompatFrameType.HEARTBEAT_PONG)
        await websocket.send_bytes(encode_frame(pong))
        return

    if frame.frame_type == CompatFrameType.SET_DEVICE_NAME and frame.payload:
        ctx.sessions.update_metadata(device_id, device_name_payload=frame.payload.decode("utf-8"))
        session = ctx.sessions.get(device_id)
        if session:
            session.device_name = frame.payload.decode("utf-8")
        return

    event = frame_to_event(frame)
    if event["event_type"] == "camera.snapshot":
        ctx.sessions.store_snapshot(device_id, base64.b64decode(event["data"]["jpeg_base64"]))
    else:
        ctx.sessions.update_metadata(device_id, last_compat_event=event)
