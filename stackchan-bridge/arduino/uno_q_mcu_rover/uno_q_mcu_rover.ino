#include "rover_service.h"

#if __has_include(<Arduino_RouterBridge.h>)
#include <Arduino_RouterBridge.h>
#define ROVER_HAVE_ROUTER_BRIDGE 1
#else
#define ROVER_HAVE_ROUTER_BRIDGE 0
#endif

rover::RoverService Rover;
bool gRpcHandlersRegistered = false;
unsigned long gLastBridgeAttemptMs = 0;
constexpr unsigned long kBridgeRetryMs = 1000;

void debug_log(const String& line)
{
  Serial.println(line);
}

String ping_handler()
{
  return Rover.ping();
}

String motor_stop_handler()
{
  return Rover.motor_stop() ? "OK action=motor_stop" : "ERROR code=stop_failed";
}

String motor_drive_handler(int left_pwm, int right_pwm, int duration_ms)
{
  if (Rover.motor_drive(left_pwm, right_pwm, duration_ms)) {
    return "OK action=motor_drive";
  }
  return "ERROR code=drive_rejected";
}

String motor_turn_handler(int left_pwm, int right_pwm, int duration_ms)
{
  if (Rover.motor_turn(left_pwm, right_pwm, duration_ms)) {
    return "OK action=motor_turn";
  }
  return "ERROR code=turn_rejected";
}

String motor_set_handler(int left_pwm, int right_pwm)
{
  if (Rover.motor_set(left_pwm, right_pwm)) {
    return "OK action=motor_set";
  }
  return "ERROR code=set_rejected";
}

String get_status_handler()
{
  return Rover.get_status();
}

String emergency_stop_handler()
{
  return Rover.emergency_stop() ? "OK action=emergency_stop" : "ERROR code=emergency_stop_failed";
}

#if ROVER_HAVE_ROUTER_BRIDGE
template <typename Handler>
bool register_safe_handler(const char* name, Handler handler)
{
  const bool ok = Bridge.provide_safe(name, handler);
  if (!ok) {
    debug_log(String("DEBUG rpc_register_failed method=") + name);
  }
  return ok;
}

bool register_rpc_handlers()
{
  return register_safe_handler("ping", ping_handler) &&
         register_safe_handler("motor_stop", motor_stop_handler) &&
         register_safe_handler("motor_drive", motor_drive_handler) &&
         register_safe_handler("motor_turn", motor_turn_handler) &&
         register_safe_handler("motor_set", motor_set_handler) &&
         register_safe_handler("get_status", get_status_handler) &&
         register_safe_handler("emergency_stop", emergency_stop_handler);
}

void ensure_bridge_ready(unsigned long now_ms)
{
  if (gRpcHandlersRegistered) {
    return;
  }
  if ((now_ms - gLastBridgeAttemptMs) < kBridgeRetryMs) {
    return;
  }

  gLastBridgeAttemptMs = now_ms;
  if (!Bridge.begin()) {
    debug_log("DEBUG bridge_begin_failed");
    return;
  }

  gRpcHandlersRegistered = register_rpc_handlers();
  if (gRpcHandlersRegistered) {
    debug_log("READY fw=uno_q_mcu_rover mode=BridgeRPC bridge_wire=Serial1");
  }
}
#endif

void setup()
{
  Serial.begin(115200);
  Rover.begin();

#if ROVER_HAVE_ROUTER_BRIDGE
  debug_log("BOOT fw=uno_q_mcu_rover mode=BridgeRPC");
  ensure_bridge_ready(millis());
#else
  Serial.println("Arduino_RouterBridge not installed; service logic is running without RPC bindings.");
#endif
}

void loop()
{
  Rover.update();
#if ROVER_HAVE_ROUTER_BRIDGE
  ensure_bridge_ready(millis());
#endif
}
