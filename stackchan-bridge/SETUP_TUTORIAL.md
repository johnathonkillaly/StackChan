# stackchan-bridge Setup Tutorial

This guide is for the case you described: you have a StackChan/CoreS3-class device on your desk, you are comfortable with ESP32 work, but you have not done this kind of local agent bridge before.

The short version is:

1. Run the bridge on your Mac or Linux box.
2. Run LM Studio locally as the model backend.
3. First prove the full loop with the included fake device client.
4. Then point your real device firmware at the bridge and verify it shows up in `/api/devices`.
5. Send typed chat requests to the bridge and watch the robot receive motion/expression/text actions.

The bridge is already useful, but it is important to understand what “useful” means today:

- It already accepts real device websocket connections.
- It already exposes a small tool-calling agent loop through LM Studio.
- It already translates actions into StackChan-compatible binary frames.
- It does **not** yet implement a full microphone-to-LLM-to-speech streaming stack.
- The current `speak_text` path is best thought of as “send text for the device to present/speak in its current firmware model,” not “guaranteed full TTS audio pipeline.”

## 1. Understand The Pieces

There are four moving parts:

### A. The bridge server

This is the Python app in [pyproject.toml](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/pyproject.toml) and [src/stackchan_bridge/server/app.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/server/app.py).

It provides:
- `GET /healthz`
- `GET /api/devices`
- `POST /api/chat`
- `WS /ws/devices/{device_id}` for the clean JSON protocol
- `WS /stackChan/ws` for current StackChan-style compatibility

### B. The local model backend

This is LM Studio, reached through its OpenAI-compatible API. The bridge talks to it through [src/stackchan_bridge/adapters/lm_studio.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/adapters/lm_studio.py).

### C. The agent loop

This is [src/stackchan_bridge/agent/runtime.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/agent/runtime.py).

Current behavior:
- takes your text input
- sends it to the local model
- offers tool schemas
- executes returned tools
- converts tool results into device actions
- dispatches those actions back to the connected device

If the model does not produce usable tool calls, the bridge still falls back to a visible response path.

### D. The device

There are two supported device styles:

- the included fake JSON client in [fake_device_client.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/fake_device_client.py)
- a real StackChan-like device using the compatibility websocket route

## 2. What Works Today On Real Hardware

The most important thing to internalize is the current control model.

Today’s built-in tools are:
- `move_head(yaw, pitch)`
- `set_expression(name)`
- `speak_text(text)`
- `get_time()`
- `capture_snapshot()`
- `trigger_home_assistant_service(domain, service, data)`

Those are defined in [src/stackchan_bridge/tools/registry.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/tools/registry.py).

On the compatibility route, those map into StackChan-style frames in [src/stackchan_bridge/protocol/compat.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/protocol/compat.py):

- `move_head` becomes `CONTROL_MOTION`
- `set_expression` becomes `CONTROL_AVATAR`
- `speak_text` becomes `TEXT_MESSAGE`
- `capture_snapshot` becomes `START_CAMERA_STREAM`

What that means in practice:

- Head movement should map naturally to servo motion.
- Expression changes map to a small set of preset eye/mouth JSON shapes.
- `speak_text` currently maps to the device’s text-message path. In the firmware in this repo, that path drives visible speech/animation behavior in the avatar app. It is not yet a full bridge-managed TTS/audio stream.
- Snapshot support is present, but it depends on the device actually sending JPEG frames back after capture/stream start.

## 3. Prerequisites

On your host machine:

- Python 3.11 or newer
- `uv`
- LM Studio installed
- the host and the StackChan on the same network

Optional but recommended:

- `curl`
- two or three terminal windows

## 4. First-Time Setup On The Host

From the repo root:

```bash
cd /Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge
cp .env.example .env
uv sync
```

Edit `.env` and start with these values:

```bash
STACKCHAN_BRIDGE_HOST=0.0.0.0
STACKCHAN_BRIDGE_PORT=8000
STACKCHAN_BRIDGE_LOG_LEVEL=INFO
STACKCHAN_BRIDGE_COMPAT_ENABLED=true

LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LM_STUDIO_MODEL=your-loaded-model-id
LM_STUDIO_API_KEY=lm-studio

HOME_ASSISTANT_ENABLED=false
```

Why `0.0.0.0` matters:

- `127.0.0.1` is only reachable from the host itself.
- your real StackChan will need the bridge to listen on a LAN-reachable interface

If macOS prompts about incoming connections when you launch the server, allow them.

## 5. Start LM Studio

In LM Studio:

1. Load a model.
2. Enable the local server / OpenAI-compatible API.
3. Confirm the listening URL, usually `http://127.0.0.1:1234/v1`.
4. Copy the exact model id into `.env` as `LM_STUDIO_MODEL`.

Model advice for first success:

- use an instruct model
- do not start with the smallest model you can find
- if tool-calling support is weak, the bridge still has a fallback parser, but better instruction-following models give better behavior

## 6. Start The Bridge

```bash
cd /Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge
uv run stackchan-bridge
```

In a second terminal, verify the server:

```bash
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/api/devices
```

Expected results:

- `/healthz` should return `{"status":"ok"}`
- `/api/devices` should return `[]` before any device connects

## 7. Do The Software-Only Dry Run First

Do not start with real hardware. First prove the whole loop locally.

In a second terminal:

```bash
cd /Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge
uv run python fake_device_client.py --device-id demo-1
```

This client:

- opens `WS /ws/devices/demo-1`
- sends a `device.hello`
- prints every action the server sends back
- sends a fake camera snapshot if the server requests one

Now check connected devices:

```bash
curl http://127.0.0.1:8000/api/devices
```

You should see `demo-1`.

Then send a chat request:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"device_id":"demo-1","text":"Act happy and say hello from the bridge."}'
```

Expected outcome:

- the server calls LM Studio
- the agent either uses tools or falls back
- the fake device prints one or more `server.action` messages
- typically you will see `set_expression` and `speak_text`

This is the first milestone. Do not move on to the real device until this works.

## 8. What The Agent Is Actually Doing

When you call `POST /api/chat`, the bridge:

1. finds the connected session in [src/stackchan_bridge/server/sessions.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/server/sessions.py)
2. wraps it as a `BridgeDevice` in [src/stackchan_bridge/server/device.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/server/device.py)
3. asks LM Studio for a response and possible tool calls
4. executes tool calls through the registry
5. turns those tool results into action objects
6. dispatches those actions to the device using either:
   - JSON envelopes on `/ws/devices/{device_id}`
   - compatibility frames on `/stackChan/ws`

That means the model never talks to the robot directly. It only chooses tools. The bridge owns actual device control.

## 9. Moving To The Real StackChan

Once the fake client works, switch to the real device.

### Step 9.1: Point The Firmware At Your Host

In this repo, the relevant firmware helper is:

[firmware/main/hal/utils/secret_logic/secret_logic.cpp](/Users/johnathonkillaly/Documents/GitHub/StackChan/firmware/main/hal/utils/secret_logic/secret_logic.cpp)

Right now the default is:

```cpp
return "http://localhost:3000";
```

That will not work for a device on your desk. Change it to your host machine’s LAN IP and the bridge port, for example:

```cpp
return "http://192.168.1.50:8000";
```

Important:

- use the host’s LAN IP, not `localhost`
- keep the scheme as `http://`
- do not add `/stackChan/ws` here, because the firmware appends that path itself

### Step 9.2: Flash Or Rebuild Firmware If Needed

The firmware README in [firmware/README.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/firmware/README.md) uses:

```bash
cd /Users/johnathonkillaly/Documents/GitHub/StackChan/firmware
python3 ./fetch_repos.py
idf.py build
idf.py flash
```

If you already have a custom firmware flow, use that. The key point is simply that the device must connect to your host’s bridge URL.

### Step 9.3: Open The Avatar App / WebSocket Client Path

In the firmware in this repo, the websocket avatar service is started from the avatar app path in [firmware/main/apps/app_avatar/app_avatar.cpp](/Users/johnathonkillaly/Documents/GitHub/StackChan/firmware/main/apps/app_avatar/app_avatar.cpp).

In practice, that means:

- boot the device
- open the relevant avatar/websocket-driven mode on the device
- watch the bridge logs for a compat device connection

### Step 9.4: Find The Device ID The Bridge Sees

With the updated bridge, the compatibility route now accepts either:

- `deviceType=StackChan&mac=...`
- or just `deviceType=StackChan`

This matters because the firmware snippet in this repo currently builds the URL with only `deviceType=StackChan`.

If the firmware does **not** send a `mac` query parameter:

- the bridge will synthesize a compat device id such as `compat-xxxxxxxxxxxx`
- you can discover it with:

```bash
curl http://127.0.0.1:8000/api/devices
```

If you want a stable and obvious id:

- patch the firmware later to include `mac` in the websocket URL
- or at minimum use `/api/devices` before calling `/api/chat`

### Step 9.5: Send Your First Real Command

Once the device shows up in `/api/devices`, send:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"device_id":"YOUR_DEVICE_ID_FROM_API_DEVICES","text":"Look happy and greet me."}'
```

If the current firmware path is working, you should see some combination of:

- expression change
- motion
- visible speech text / speaking animation

## 10. Good First Prompts

Start with prompts that are obviously mappable to the current tools:

- `Act happy and say hello.`
- `Turn your head slightly left and say good morning.`
- `Tell me the current time.`
- `Take a snapshot.`

Avoid starting with:

- long multi-step tasks
- open-ended assistant conversations
- voice streaming expectations
- Home Assistant automations

Those come later.

## 11. Using Snapshot Capture

Current behavior:

- the `capture_snapshot` tool requests a snapshot if one is not already cached
- on the JSON demo path, the fake client answers with a fake JPEG payload
- on the compat path, the bridge expects the device to send JPEG frames back

For real hardware, the important check is:

1. the device receives the capture/stream request
2. the device actually starts sending JPEG frames
3. `/api/chat` or future logic can then use the cached snapshot

This is a control-path MVP, not yet a polished vision pipeline.

## 12. Using Home Assistant Later

The Home Assistant adapter is intentionally conservative right now.

If `HOME_ASSISTANT_ENABLED=false`, the tool returns a disabled/config-missing result instead of pretending it worked.

That is deliberate:

- you can wire the rest of the bridge first
- then enable HA once the robot connection and local model loop are stable

## 13. Troubleshooting

### The server starts, but the real device never appears in `/api/devices`

Check these in order:

1. `STACKCHAN_BRIDGE_HOST` is `0.0.0.0`
2. the device and host are on the same network
3. the firmware `get_server_url()` points to your host IP and port `8000`
4. macOS firewall is not blocking inbound connections
5. the device is actually in the avatar/websocket mode

### `/api/chat` returns 404 for the device

That means the bridge has no active session for that `device_id`.

Run:

```bash
curl http://127.0.0.1:8000/api/devices
```

Use exactly the id listed there.

### The model replies, but motion/expression behavior is weak

Use simpler prompts first:

- `set_expression happy and say hello`
- `move your head left a little and greet me`

Also verify the LM Studio model is a strong instruct model.

### The device connects, but `speak_text` does not produce real spoken audio

That is expected with the current MVP. Today’s bridge sends a text/speaking action through the current firmware-compatible path. It is not yet a full host-managed TTS audio streaming implementation.

### Snapshot capture does nothing visible

That usually means one of two things:

1. the device received the action but is not actually sending JPEG frames back
2. the device is not in a mode where camera streaming is active

### The compat device id changes or is not very readable

If your firmware does not supply `mac`, the bridge synthesizes an id. For a cleaner setup, patch the firmware websocket URL to include a unique device identifier later.

## 14. Recommended Bring-Up Order

Use this order exactly:

1. `uv sync`
2. LM Studio running locally
3. bridge starts and `/healthz` is good
4. fake JSON client connects
5. `/api/chat` works with the fake client
6. firmware points to host IP
7. real device appears in `/api/devices`
8. simple prompts work on the real device
9. only then start adding HA or richer device features

That order prevents you from debugging four systems at once.

## 15. What I Would Do Next If This Were My Desk Setup

Once you have a successful first hardware loop, the next practical improvements are:

1. patch the firmware URL logic to send a stable device id or `mac`
2. add a tiny manual command CLI for actions like “move head now” without involving the LLM
3. add a real TTS/audio output strategy if you want spoken audio instead of only text/speaking animation
4. add a simple snapshot-inspection endpoint so camera bring-up is easier
5. then add Home Assistant or ESPHome integration

That sequence keeps the physical control loop reliable before you layer in more automation.

