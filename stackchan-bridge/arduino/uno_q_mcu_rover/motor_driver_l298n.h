#pragma once

#include <Arduino.h>

#include "rover_config.h"

namespace rover {

inline int clamp_pwm(int value)
{
  if (value < kPwmMin) {
    return kPwmMin;
  }
  if (value > kPwmMax) {
    return kPwmMax;
  }
  return value;
}

class L298NMotorDriver {
 public:
  void begin()
  {
    pinMode(kPinEna, OUTPUT);
    pinMode(kPinIn1, OUTPUT);
    pinMode(kPinIn2, OUTPUT);
    pinMode(kPinIn3, OUTPUT);
    pinMode(kPinIn4, OUTPUT);
    pinMode(kPinEnb, OUTPUT);
    stop();
  }

  void stop()
  {
    analogWrite(kPinEna, 0);
    analogWrite(kPinEnb, 0);
    digitalWrite(kPinIn1, LOW);
    digitalWrite(kPinIn2, LOW);
    digitalWrite(kPinIn3, LOW);
    digitalWrite(kPinIn4, LOW);
  }

  void set(int left_pwm, int right_pwm)
  {
    apply_side(kPinEna, kPinIn1, kPinIn2, clamp_pwm(left_pwm));
    apply_side(kPinEnb, kPinIn3, kPinIn4, clamp_pwm(right_pwm));
  }

 private:
  void apply_side(int enable_pin, int in_a, int in_b, int pwm)
  {
    if (pwm > 0) {
      digitalWrite(in_a, HIGH);
      digitalWrite(in_b, LOW);
      analogWrite(enable_pin, pwm);
      return;
    }
    if (pwm < 0) {
      digitalWrite(in_a, LOW);
      digitalWrite(in_b, HIGH);
      analogWrite(enable_pin, -pwm);
      return;
    }

    digitalWrite(in_a, LOW);
    digitalWrite(in_b, LOW);
    analogWrite(enable_pin, 0);
  }
};

}  // namespace rover

