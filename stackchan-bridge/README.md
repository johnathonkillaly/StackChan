# stackchan-bridge

`stackchan-bridge` is a local-first Python backend for StackChan / CoreS3 class devices. It gives the device a stable control channel for expressions, motion, LEDs, display updates, and speech while heavier LLM work runs on a Mac or Linux host.

The project is intentionally modular:
- FastAPI handles HTTP and WebSocket transport.
- Pydantic models keep the bridge protocol typed.
- A protocol-agnostic device/session layer hides whether the client is using the new JSON bridge or the current StackChan binary websocket envelope.
- LM Studio is the default local model backend through its OpenAI-compatible API.

For a step-by-step bring-up guide aimed at a real desk device, see [SETUP_TUTORIAL.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/SETUP_TUTORIAL.md).
For the StackChan + UNO Q + L298N rover extension, see [docs/rover_bringup.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/rover_bringup.md), [docs/rover_wiring.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/rover_wiring.md), [docs/rover_architecture.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/rover_architecture.md), and [docs/uno_q_deployment.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/uno_q_deployment.md).

## Architecture

```mermaid
flowchart LR
    Device["StackChan / Fake Device"] -->|JSON WS /ws/devices/{id}| Bridge["FastAPI stackchan-bridge"]
    Compat["Current StackChan Firmware"] -->|Binary WS /stackChan/ws| Bridge
    Bridge --> Sessions["Session Manager"]
    Bridge --> Agent["Agent Runtime"]
    Agent --> Tools["Tool Registry"]
    Tools --> HA["Home Assistant Adapter (optional)"]
    Agent --> LLM["LM Studio OpenAI-Compatible API"]
    Sessions --> Actions["Device Action Dispatch"]
```

## Project Layout

- `src/stackchan_bridge/server`: FastAPI app, config, session manager, device facade, routers.
- `src/stackchan_bridge/protocol`: JSON bridge models and current StackChan binary compatibility codec.
- `src/stackchan_bridge/rover`: UART protocol, Linux controller, planner, and UNO Q integration seams.
- `src/stackchan_bridge/adapters`: LM Studio and Home Assistant integrations.
- `src/stackchan_bridge/agent`: prompt construction and tool-driven agent loop.
- `src/stackchan_bridge/tools`: built-in tool registry and tool execution.
- `tests`: protocol, tools, adapter, and server smoke coverage.
- `fake_device_client.py`: demo JSON WebSocket client.
- `arduino/uno_q_mcu_rover`: UNO Q MCU sketch scaffold for rover motor control.
- `protocol-notes.md`: protocol comparison notes and future bridge direction.

## Local Development

```bash
cd stackchan-bridge
uv sync
uv run stackchan-bridge
```

Health check:

```bash
curl http://127.0.0.1:8000/healthz
```

Run tests:

```bash
uv run pytest
```

## Rover Service

The rover extension lets `stackchan-bridge` control a small two-motor rover through an Arduino UNO Q + L298N split:

- StackChan/CoreS3 remains the expressive head.
- UNO Q Linux handles UART parsing and higher-level rover orchestration.
- UNO Q MCU handles real-time motor output and safety.

Standalone rover service entrypoints:

```bash
cd stackchan-bridge
uv run stackchan-rover-service serve --simulation --pty
uv run stackchan-rover-replay --serial-device /path/from/service --script-file tests/fixtures/rover_replay.txt
```

For wiring and bring-up, see:
- [docs/rover_wiring.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/rover_wiring.md)
- [docs/rover_architecture.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/rover_architecture.md)
- [docs/rover_bringup.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/rover_bringup.md)
- [docs/uno_q_deployment.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/uno_q_deployment.md)

## LM Studio Setup

1. Start LM Studio locally.
2. Load a model that can follow instructions. Tool support helps, but the bridge includes a fallback parser for simple inline tool requests.
3. Enable the OpenAI-compatible local server in LM Studio.
4. Copy `.env.example` to `.env` and set:

```bash
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LM_STUDIO_MODEL=your-loaded-model-id
LM_STUDIO_API_KEY=lm-studio
```

## Demo Path

1. Start the bridge:

```bash
cd stackchan-bridge
uv run stackchan-bridge
```

2. Start the fake device client in another terminal:

```bash
cd stackchan-bridge
uv run python fake_device_client.py --device-id demo-1
```

3. Send a chat message:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"device_id":"demo-1","text":"Say hello and act cheerful."}'
```

4. The fake device client will print the returned action sequence, typically `set_expression` followed by `speak_text`.

## HTTP API

### `GET /healthz`

Returns a minimal readiness response.

### `GET /api/devices`

Returns the connected device list, protocol mode, stale status, and capabilities.

### `POST /api/chat`

Example:

```json
{
  "device_id": "demo-1",
  "text": "Wave hello and tell me the time."
}
```

## JSON WebSocket Protocol

Primary endpoint:

```text
ws://127.0.0.1:8000/ws/devices/demo-1
```

Device hello:

```json
{
  "type": "device.hello",
  "payload": {
    "device_id": "demo-1",
    "device_name": "Fake StackChan",
    "capabilities": {
      "display": { "enabled": true, "width": 320, "height": 240, "color": true },
      "audio": { "enabled": true, "sample_rate_hz": 16000 },
      "motion": { "enabled": true, "yaw_range": [-90, 90], "pitch_range": [-30, 30] },
      "camera": { "enabled": true, "snapshot_supported": true, "stream_supported": false }
    }
  }
}
```

Server action:

```json
{
  "type": "server.action",
  "action_id": "4a3d8f42-8b9e-4f7a-b865-7b7f903d5425",
  "action": {
    "kind": "speak_text",
    "text": "Hello from stackchan-bridge."
  }
}
```

Device event:

```json
{
  "type": "device.event",
  "event": {
    "event_type": "camera.snapshot",
    "data": {
      "jpeg_base64": "/9j/4AAQSkZJRgABAQ..."
    }
  }
}
```

## Current StackChan Compatibility Endpoint

Compatibility endpoint:

```text
ws://127.0.0.1:8000/stackChan/ws?deviceType=StackChan&mac=AA:BB:CC:DD:EE:FF
```

The `mac` query parameter is preferred, but the bridge can now also accept firmware that connects with only `deviceType=StackChan`. In that case it synthesizes a compatibility device id, which you can discover via `GET /api/devices`.

This route accepts the current binary envelope used in the firmware in this repo and translates it into the bridge’s internal events/actions. Supported frame families include:
- text
- avatar control
- motion control
- heartbeat
- device name
- JPEG snapshots
- camera and audio toggles
- call and video mode flags
- dance sequence payloads

The bridge uses protocol translation internally, so tool execution stays independent from the on-wire format.

## Future Integration Ideas

- Voice streaming: add dedicated audio chunk events and a duplex speech pipeline.
- MCP-style tool exposure: surface device actions as externally consumable tools for other local agents.
- Home Assistant / ESPHome: move the current adapter stub into a richer entity/service bridge and publish device state into Home Assistant.
- Real hardware compatibility: add a bridge-side command adapter for more StackChan-native visual presets and richer LED choreography.
