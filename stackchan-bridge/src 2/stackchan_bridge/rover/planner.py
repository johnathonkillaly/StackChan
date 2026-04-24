from __future__ import annotations

from stackchan_bridge.rover.protocol import MotionDecision, Observation


def choose_motion(observation: Observation) -> MotionDecision:
    if observation.state == "clear":
        return MotionDecision(
            action="drive",
            left_pwm=120,
            right_pwm=120,
            duration_ms=200,
            reason="clear_ahead",
        )
    if observation.state == "blocked_left":
        return MotionDecision(
            action="turn",
            left_pwm=120,
            right_pwm=-120,
            duration_ms=180,
            reason="left_blocked_turn_right",
        )
    if observation.state == "blocked_right":
        return MotionDecision(
            action="turn",
            left_pwm=-120,
            right_pwm=120,
            duration_ms=180,
            reason="right_blocked_turn_left",
        )
    return MotionDecision(
        action="stop",
        left_pwm=0,
        right_pwm=0,
        duration_ms=0,
        reason="unknown_or_unsafe",
    )

