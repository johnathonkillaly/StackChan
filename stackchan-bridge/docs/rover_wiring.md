# Rover Wiring Guide

This rover extension assumes a split-brain setup:

- StackChan/CoreS3 is the expressive head.
- Arduino UNO Q Linux side runs the UART rover service.
- Arduino UNO Q MCU side drives the motors in real time.
- L298N drives two TT yellow motors from a separate motor power rail.

## Topology

```text
StackChan Grove UART
  -> UART breakout
  -> UNO Q UART pins

UNO Q MCU pins
  -> L298N ENA / IN1 / IN2 / IN3 / IN4 / ENB
  -> TT motor pair
```

## Power Rules

- Power the UNO Q independently, for example from a USB-C battery bank.
- Power the motors from a dedicated motor supply connected to the L298N motor rail.
- Share ground between StackChan, UNO Q, and the L298N motor driver.
- Do not try to power the motors from StackChan or from the UNO Q signal pins.

## StackChan To UNO Q UART

The first version assumes:

- StackChan uses the CoreS3 Grove UART path through an external Grove HY2.0-4P breakout.
- UNO Q receives those UART lines on a board-specific UART-capable header or carrier mapping.

Before powering hardware:

1. Verify the CoreS3 UART-capable Grove port mapping on your actual StackChan/CoreS3 setup.
2. Verify the final UNO Q pin mapping on the exact carrier or breakout you are using.
3. Confirm both ends are using 3.3 V UART logic.
4. Confirm TX/RX are crossed correctly:
   - StackChan TX -> UNO Q RX
   - StackChan RX -> UNO Q TX
   - GND -> GND

## UNO Q To L298N

The sketch keeps motor pin assignments in [rover_config.h](/Users/johnathonkillaly/Documents/GitHub/StackChan/stackchan-bridge/arduino/uno_q_mcu_rover/rover_config.h).

Default placeholders:

- `ENA`
- `IN1`
- `IN2`
- `IN3`
- `IN4`
- `ENB`

These are deliberately centralized so you can change them after checking the current official UNO Q pin map.

Control-line count matters here:

- Your old Elegoo TB6612 shield setup used five MCU control pins because it had one shared standby pin plus one PWM and one direction line per side.
- A typical L298N board wants six control lines for full dual-motor speed and direction control: `ENA`, `IN1`, `IN2`, `IN3`, `IN4`, `ENB`.
- If you leave the `ENA` and `ENB` jumpers installed, you can get down to four direction-only control lines, but then you give up per-side PWM speed control from the MCU.
- For this rover stack, the first software target assumes the full six-line layout.

## L298N Notes

- Remove the `ENA` and `ENB` jumpers if you want PWM speed control from the MCU.
- Keep motor power and logic power wiring correct for your specific L298N board.
- Expect voltage drop and inefficiency from L298N; the software layer keeps a driver abstraction ready so you can later swap to TB6612FNG.
- Verify that your specific L298N input board treats 3.3 V as a valid logic-high level before wiring the UNO Q directly.

## Power Cautions

- Do not plan on powering the UNO Q from the L298N board's `5V` pin in the first bring-up. Many L298N boards expose a weak onboard regulator intended for light logic loads, not a Linux-capable controller board.
- Do not plan on back-powering the UNO Q from StackChan's 5 V rail in the first bring-up either.
- The safest first bench setup is still:
  - UNO Q on its own USB-C power source
  - StackChan on its own normal power path
  - motors on a separate motor rail
  - shared ground across all three
- If you later want a single-battery build, treat that as a separate power-design pass after motion and UART are stable.

## Pre-Power Checklist

1. Shared ground is present across all signal domains.
2. The UNO Q logic pins are not being driven with 5 V UART levels.
3. Motor power is separate from UNO Q and StackChan logic power.
4. The L298N enable jumpers are configured for PWM control.
5. The pin mapping in `rover_config.h` matches your real wiring.
