# Protocol Notes

## Generic Bridge Protocol

The JSON bridge protocol is the long-term default for `stackchan-bridge`.

Why:
- It is easy to inspect and debug.
- It is stable for local tooling and tests.
- It maps directly to typed Pydantic models.
- It leaves room for future tool exposure and richer event streams without hard-coding ESP32 packet details into the agent stack.

Core ideas:
- `device.hello` advertises capabilities.
- `device.event` carries sensor or state updates.
- `server.action` carries one typed device command.
- `server.ack` and `server.error` keep the protocol explicit.

## Current StackChan Binary Envelope

The existing firmware in this repo already uses a websocket binary envelope with one-byte message types and a four-byte payload length. Notable properties:
- It is compact and device-friendly.
- Avatar and motion payloads already carry JSON bodies inside the envelope.
- Camera and audio streaming concepts are present even if the bridge MVP does not implement full duplex media orchestration.

Bridge strategy:
- Accept the current envelope unchanged on `/stackChan/ws`.
- Decode it into typed internal events.
- Map bridge actions back into compatibility frames when talking to current hardware.

## XiaoZhi-Style MCP Concepts

XiaoZhi-style systems tend to blur three layers:
- transport
- agent runtime
- tool invocation

For `stackchan-bridge`, those layers stay separate:
- WebSocket transport handles delivery.
- The agent loop decides what to do.
- Tool execution produces typed outcomes and device actions.

That separation is important because future MCP-style exposure should not dictate how the hardware speaks on the wire.

## Future ESPHome / Home Assistant Bridge

The Home Assistant path should be additive, not invasive.

Recommended bridge strategy:
- Keep StackChan actions as the source-of-truth API.
- Add a Home Assistant adapter that can trigger services and eventually publish sensor/state updates.
- Add an ESPHome translation layer only when the physical device path requires entity modeling or HA-native discovery.

In practice:
- `move_head` could later map to HA services or ESPHome APIs.
- `capture_snapshot` could publish a camera entity update.
- device capability and health state could become HA entities.

The bridge MVP keeps those seams explicit so local-first use stays simple now and HA integration stays clean later.

