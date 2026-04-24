# Rover Bring-Up

This document covers four stages:

1. Desktop simulation
2. UNO Q Linux service
3. UNO Q MCU sketch
4. First StackChan-to-rover motion path

For packaging and SCP deployment to the UNO Q Linux side, see [uno_q_deployment.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/uno_q_deployment.md).

## 1. Desktop Simulation

Install dependencies:

```bash
cd /Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge
uv sync
```

Start the rover service with a PTY and fake MCU bridge:

```bash
uv run stackchan-rover-service serve --simulation --pty
```

Expected output:

```text
PTY_SLAVE=/dev/ttysXXX
ADMIN_SOCKET=/tmp/stackchan-rover-admin.sock
```

In another terminal, replay fake StackChan commands:

```bash
uv run stackchan-rover-replay \
  --serial-device /dev/ttysXXX \
  --script-file tests/fixtures/rover_replay.txt
```

This demo path proves:

- UART command parsing
- Linux-side dispatch
- mocked MCU bridge calls
- response formatting

Admin loop control:

```bash
uv run stackchan-rover-service admin loop-start --interval-ms 250
uv run stackchan-rover-service admin loop-status
uv run stackchan-rover-service admin loop-stop
```

Emergency stop:

```bash
uv run stackchan-rover-service admin emergency-stop
```

## 2. UNO Q Linux Service

When moving from simulation to UNO Q Linux:

1. Deploy the Python package and dependencies.
2. Configure access to the UNO Q Bridge / RPC router.
3. Connect StackChan UART to the selected UNO Q UART pins.

Example service command shape:

```bash
uv run stackchan-rover-service serve \
  --serial-device /dev/ttyS0 \
  --rpc-socket /var/run/arduino-router.sock
```

If your UNO Q App Lab runtime exposes the bridge/router differently, adjust only the Linux-side RPC adapter or settings. The rover command protocol and tool surface stay unchanged.

TCP fallback remains available if you intentionally expose the router another way:

```bash
uv run stackchan-rover-service serve \
  --serial-device /dev/ttyS0 \
  --rpc-socket '' \
  --rpc-host 127.0.0.1 \
  --rpc-port 50051
```

## 3. UNO Q MCU Sketch

The sketch scaffold lives at:

[arduino/uno_q_mcu_rover/uno_q_mcu_rover.ino](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/arduino/uno_q_mcu_rover/uno_q_mcu_rover.ino)

Before flashing:

1. Verify pin assignments in `rover_config.h`.
2. Install the UNO Q board support.
3. Install `Arduino_RouterBridge` if your App Lab environment does not already include it.
4. Confirm the wiring guide in [rover_wiring.md](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/docs/rover_wiring.md).
5. Expect the bridge binding style to match your older UNO Q sketch: `Bridge.begin()` followed by `Bridge.provide_safe(...)`.

First dry test:

- Power the UNO Q only.
- Leave motor power disconnected.
- Flash the sketch.
- Call `ping` and `get_status` through the Linux bridge path first.
- Then test `motor_set(0, 0)` and `motor_stop()`.

Only after those succeed should you connect motor power.

## 4. First Motor Test

With motors connected and the rover lifted off the desk:

1. Start the Linux rover service.
2. Send `PING`.
3. Send `STATUS`.
4. Send a low-power bounded test such as `DRIVE 80 80 150`.
5. Send `STOP`.
6. Test `TURN 80 -80 150`.
7. Test `ESTOP`.

Do not begin with long durations or high PWM values.

## 5. First StackChan-To-Rover Integration

The MVP does not add new StackChan firmware yet. The immediate integration path is:

1. Keep StackChan connected to the existing `stackchan-bridge` websocket service.
2. Enable in-process rover support with:

```bash
ROVER_ENABLED=true
ROVER_SIMULATION_MODE=true
```

3. Run the normal bridge server:

```bash
uv run stackchan-bridge
```

4. Connect StackChan or the fake device client.
5. Send bridge prompts that map to rover tools or `rover_observe_step`.

The observe-step tool uses the existing StackChan snapshot seam as a placeholder perception source:

- metadata hint if present
- otherwise latest cached snapshot => treated as `clear`
- otherwise `unknown` and the rover holds position

## Manual Verification Checklist

- `PING` returns `PONG`
- invalid commands return `ERR bad_args` or `ERR unknown_cmd`
- `STATUS` reports loop and emergency-stop state
- `ESTOP` halts motion and blocks later drive commands
- the admin loop can start and stop cleanly
- the MCU watchdog stops motors after command timeout
