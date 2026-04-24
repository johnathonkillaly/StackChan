#pragma once

#include <Arduino.h>

#include "motor_driver_l298n.h"

namespace rover {

struct Status {
  int left_pwm = 0;
  int right_pwm = 0;
  bool emergency_stop = false;
  bool watchdog_ok = true;
  unsigned long last_command_ms = 0;
  String last_cmd = "INIT";
};

class RoverService {
 public:
  void begin()
  {
    driver_.begin();
    status_.last_command_ms = millis();
    stop_with_reason("BOOT");
  }

  void update()
  {
    const unsigned long now = millis();
    if ((now - status_.last_command_ms) > kWatchdogTimeoutMs) {
      driver_.stop();
      status_.watchdog_ok = false;
      status_.left_pwm = 0;
      status_.right_pwm = 0;
      status_.last_cmd = "WATCHDOG_STOP";
    }
  }

  String ping()
  {
    status_.last_cmd = "PING";
    return "pong";
  }

  bool motor_stop()
  {
    stop_with_reason("STOP");
    return true;
  }

  bool motor_drive(int left_pwm, int right_pwm, int duration_ms)
  {
    if (!validate_timed_command(left_pwm, right_pwm, duration_ms)) {
      stop_with_reason("INVALID_DRIVE");
      return false;
    }
    if (status_.emergency_stop) {
      stop_with_reason("ESTOP_LATCHED");
      return false;
    }
    driver_.set(left_pwm, right_pwm);
    status_.left_pwm = clamp_pwm(left_pwm);
    status_.right_pwm = clamp_pwm(right_pwm);
    status_.watchdog_ok = true;
    status_.last_command_ms = millis();
    status_.last_cmd = "DRIVE";
    delay(duration_ms);
    driver_.stop();
    status_.left_pwm = 0;
    status_.right_pwm = 0;
    return true;
  }

  bool motor_turn(int left_pwm, int right_pwm, int duration_ms)
  {
    if (!validate_timed_command(left_pwm, right_pwm, duration_ms)) {
      stop_with_reason("INVALID_TURN");
      return false;
    }
    if (status_.emergency_stop) {
      stop_with_reason("ESTOP_LATCHED");
      return false;
    }
    driver_.set(left_pwm, right_pwm);
    status_.left_pwm = clamp_pwm(left_pwm);
    status_.right_pwm = clamp_pwm(right_pwm);
    status_.watchdog_ok = true;
    status_.last_command_ms = millis();
    status_.last_cmd = "TURN";
    delay(duration_ms);
    driver_.stop();
    status_.left_pwm = 0;
    status_.right_pwm = 0;
    return true;
  }

  bool motor_set(int left_pwm, int right_pwm)
  {
    if (!validate_pwm(left_pwm) || !validate_pwm(right_pwm)) {
      stop_with_reason("INVALID_SET");
      return false;
    }
    if (status_.emergency_stop) {
      stop_with_reason("ESTOP_LATCHED");
      return false;
    }
    driver_.set(left_pwm, right_pwm);
    status_.left_pwm = clamp_pwm(left_pwm);
    status_.right_pwm = clamp_pwm(right_pwm);
    status_.watchdog_ok = true;
    status_.last_command_ms = millis();
    status_.last_cmd = "SET";
    return true;
  }

  String get_status()
  {
    String json = "{";
    json += "\"source\":\"uno_q_mcu\",";
    json += "\"motors\":\"" + current_motor_state() + "\",";
    json += "\"left_pwm\":" + String(status_.left_pwm) + ",";
    json += "\"right_pwm\":" + String(status_.right_pwm) + ",";
    json += "\"emergency_stop\":" + String(status_.emergency_stop ? "true" : "false") + ",";
    json += "\"watchdog_ok\":" + String(status_.watchdog_ok ? "true" : "false") + ",";
    json += "\"loop_running\":false,";
    json += "\"last_cmd\":\"" + status_.last_cmd + "\"";
    json += "}";
    return json;
  }

  bool emergency_stop()
  {
    status_.emergency_stop = true;
    stop_with_reason("ESTOP");
    return true;
  }

  bool clear_emergency_stop()
  {
    status_.emergency_stop = false;
    stop_with_reason("CLEAR_ESTOP");
    return true;
  }

 private:
  bool validate_pwm(int value)
  {
    return value >= kPwmMin && value <= kPwmMax;
  }

  bool validate_timed_command(int left_pwm, int right_pwm, int duration_ms)
  {
    if (!validate_pwm(left_pwm) || !validate_pwm(right_pwm)) {
      return false;
    }
    return duration_ms >= 1 && static_cast<unsigned long>(duration_ms) <= kMaxTimedCommandMs;
  }

  void stop_with_reason(const String& reason)
  {
    driver_.stop();
    status_.left_pwm = 0;
    status_.right_pwm = 0;
    status_.watchdog_ok = true;
    status_.last_command_ms = millis();
    status_.last_cmd = reason;
  }

  String current_motor_state() const
  {
    if (status_.emergency_stop) {
      return "stopped";
    }
    if (status_.left_pwm == 0 && status_.right_pwm == 0) {
      return "stopped";
    }
    return "active";
  }

  L298NMotorDriver driver_;
  Status status_;
};

}  // namespace rover
