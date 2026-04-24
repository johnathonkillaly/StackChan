# Rover Architecture

## Data Flow

```text
StackChan
  -> UART text / JSONL commands
UNO Q Linux rover service
  -> parse / validate / acknowledge
  -> UNO Q Bridge / RPC client seam (default: /var/run/arduino-router.sock)
UNO Q MCU rover sketch
  -> motor safety / watchdog / PWM clamp
L298N
  -> left and right TT motors
```

## Software Layers

### UART protocol

Implemented in [protocol.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/rover/protocol.py).

Properties:

- canonical human-debuggable line commands
- equal JSONL support for future structured emitters
- mirrored response dialect
- explicit parse and validation errors

Supported commands:

- `PING`
- `STOP`
- `ESTOP`
- `STATUS`
- `OBSERVE`
- `DRIVE <left_pwm> <right_pwm> <duration_ms>`
- `TURN <left_pwm> <right_pwm> <duration_ms>`
- `SET <left_pwm> <right_pwm>`

### Linux-side rover controller

Implemented in [linux_controller.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/rover/linux_controller.py).

Responsibilities:

- read and decode UART commands
- call the MCU bridge adapter
- expose admin loop control over a UNIX socket
- provide simulation mode and fake bridge support
- run the bounded observe-drive loop

### Planner

Implemented in [planner.py](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/src/stackchan_bridge/rover/planner.py).

Current policy:

- `unknown` -> stop
- `clear` -> short forward drive
- `blocked_left` -> turn right
- `blocked_right` -> turn left

The planner stays intentionally small so a future local model or local vision module can replace only the perception or decision layer without rewriting transport or motor safety code.

### FastAPI bridge integration

The existing `stackchan-bridge` app can optionally create an in-process rover controller and expose bridge tools:

- `rover_stop`
- `rover_drive`
- `rover_turn`
- `rover_status`
- `rover_observe_step`

This does not add new public HTTP routes in the MVP.

### MCU motor service

Implemented as a sketch scaffold in [arduino/uno_q_mcu_rover](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/arduino/uno_q_mcu_rover).

Responsibilities:

- enforce PWM clamp and duration bounds
- stop on boot
- stop on invalid input
- stop on watchdog timeout
- drive L298N pins deterministically

## Safety Model

- Linux side rejects malformed commands.
- MCU side independently clamps PWM and rejects invalid durations.
- `ESTOP` latches an emergency-stop state until explicitly cleared or rebooted.
- The observe-drive loop is bounded and always brackets movement with stops.
- Continuous looping is controlled only from the local admin channel, not from the agent tools.
