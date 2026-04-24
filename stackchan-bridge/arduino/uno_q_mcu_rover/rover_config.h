#pragma once

namespace rover {

// Verify these assignments against the official UNO Q pin map and your carrier.
// Keep them centralized here so the motor driver can be swapped later.
constexpr int kPinEna = 9;
constexpr int kPinIn1 = 6;
constexpr int kPinIn2 = 7;
constexpr int kPinIn3 = 8;
constexpr int kPinIn4 = 12;
constexpr int kPinEnb = 10;

constexpr int kPwmMin = -255;
constexpr int kPwmMax = 255;
constexpr unsigned long kWatchdogTimeoutMs = 750;
constexpr unsigned long kMaxTimedCommandMs = 5000;

}  // namespace rover

