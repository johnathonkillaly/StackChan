# UNO Q MCU Rover Sketch

This sketch is the MCU-side safety and motor-control layer for the rover extension.

Files:

- [uno_q_mcu_rover.ino](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/arduino/uno_q_mcu_rover/uno_q_mcu_rover.ino)
- [rover_config.h](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/arduino/uno_q_mcu_rover/rover_config.h)
- [motor_driver_l298n.h](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/arduino/uno_q_mcu_rover/motor_driver_l298n.h)
- [rover_service.h](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/arduino/uno_q_mcu_rover/rover_service.h)

Notes:

- The service logic and safety behavior are fully implemented in the local sketch files.
- The RPC binding section now follows the same UNO Q pattern already used in `elegoo_conquerer_arduino_q_edition`: `Bridge.begin()` plus `Bridge.provide_safe(...)` with retry until the router is ready.
- The sketch does not call a manual `Bridge.process()` loop; the router bridge service handles request dispatch once the handlers are registered.
- If your installed `Arduino_RouterBridge` release exposes a slightly different safe-registration overload, adjust only the binding lines in the sketch. The service logic and method names should stay unchanged.

Manual verification:

1. Flash the sketch with motor power disconnected.
2. Verify `ping()` returns `pong`.
3. Verify `get_status()` returns JSON with `source`, `motors`, and `last_cmd`.
4. Verify invalid PWM or duration requests return false and stop outputs.
5. Verify leaving the board idle causes the watchdog stop path to trigger.
