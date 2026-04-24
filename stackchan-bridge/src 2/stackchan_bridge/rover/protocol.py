from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator


class ProtocolDialect(StrEnum):
    TEXT = "text"
    JSON = "json"


class RoverCommandName(StrEnum):
    PING = "PING"
    STOP = "STOP"
    ESTOP = "ESTOP"
    STATUS = "STATUS"
    OBSERVE = "OBSERVE"
    DRIVE = "DRIVE"
    TURN = "TURN"
    SET = "SET"


class RoverResponseType(StrEnum):
    OK = "ok"
    ERROR = "error"
    PONG = "pong"
    STATUS = "status"
    OBSERVATION = "observation"


class Observation(BaseModel):
    state: Literal["unknown", "clear", "blocked_left", "blocked_right", "blocked_ahead"] = "unknown"
    source: str = "placeholder"
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MotionDecision(BaseModel):
    action: Literal["stop", "drive", "turn"] = "stop"
    left_pwm: int = 0
    right_pwm: int = 0
    duration_ms: int = 0
    reason: str = "unknown"


class LoopState(BaseModel):
    running: bool = False
    interval_ms: int = 500
    iterations: int = 0
    emergency_stop: bool = False
    last_observation: Observation | None = None
    last_decision: MotionDecision | None = None
    last_error: str | None = None


class RoverStatus(BaseModel):
    source: str = "simulation"
    motors: str = "stopped"
    left_pwm: int = 0
    right_pwm: int = 0
    watchdog_ok: bool = True
    emergency_stop: bool = False
    last_cmd: str = "INIT"
    loop_running: bool = False
    battery_mv: int | None = None
    note: str | None = None


class ObserveStepResult(BaseModel):
    observation: Observation
    decision: MotionDecision
    status: RoverStatus
    requested_snapshot: bool = False


class RoverCommand(BaseModel):
    cmd: RoverCommandName
    dialect: ProtocolDialect = ProtocolDialect.TEXT
    left_pwm: int | None = None
    right_pwm: int | None = None
    duration_ms: int | None = None

    @model_validator(mode="after")
    def validate_args(self) -> "RoverCommand":
        if self.cmd in {
            RoverCommandName.PING,
            RoverCommandName.STOP,
            RoverCommandName.ESTOP,
            RoverCommandName.STATUS,
            RoverCommandName.OBSERVE,
        }:
            if self.left_pwm is not None or self.right_pwm is not None or self.duration_ms is not None:
                raise ValueError(f"{self.cmd} does not accept numeric arguments.")
            return self

        if self.cmd == RoverCommandName.SET:
            if self.left_pwm is None or self.right_pwm is None or self.duration_ms is not None:
                raise ValueError("SET requires left_pwm and right_pwm.")
            _validate_pwm(self.left_pwm)
            _validate_pwm(self.right_pwm)
            return self

        if self.cmd in {RoverCommandName.DRIVE, RoverCommandName.TURN}:
            if self.left_pwm is None or self.right_pwm is None or self.duration_ms is None:
                raise ValueError(f"{self.cmd} requires left_pwm, right_pwm, and duration_ms.")
            _validate_pwm(self.left_pwm)
            _validate_pwm(self.right_pwm)
            _validate_duration(self.duration_ms)
            return self

        raise ValueError(f"Unhandled command {self.cmd}.")


class RoverResponse(BaseModel):
    response_type: RoverResponseType
    dialect: ProtocolDialect = ProtocolDialect.TEXT
    code: str | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    status: RoverStatus | None = None
    observation: Observation | None = None

    @classmethod
    def ok(cls, *, dialect: ProtocolDialect, message: str | None = None, data: dict[str, Any] | None = None) -> "RoverResponse":
        return cls(response_type=RoverResponseType.OK, dialect=dialect, message=message, data=data or {})

    @classmethod
    def error(cls, *, dialect: ProtocolDialect, code: str, message: str | None = None) -> "RoverResponse":
        return cls(response_type=RoverResponseType.ERROR, dialect=dialect, code=code, message=message)

    @classmethod
    def pong(cls, *, dialect: ProtocolDialect, message: str | None = None) -> "RoverResponse":
        return cls(response_type=RoverResponseType.PONG, dialect=dialect, message=message or "pong")

    @classmethod
    def from_status(cls, *, dialect: ProtocolDialect, status: RoverStatus) -> "RoverResponse":
        return cls(response_type=RoverResponseType.STATUS, dialect=dialect, status=status)

    @classmethod
    def from_observation(cls, *, dialect: ProtocolDialect, observation: Observation) -> "RoverResponse":
        return cls(response_type=RoverResponseType.OBSERVATION, dialect=dialect, observation=observation)


def parse_command_auto(line: str) -> RoverCommand:
    dialect = guess_dialect(line)
    if dialect == ProtocolDialect.JSON:
        return parse_command_json(line)
    return parse_command_text(line)


def parse_command_text(line: str) -> RoverCommand:
    stripped = line.strip()
    if not stripped:
        raise ValueError("Empty command.")

    parts = stripped.split()
    try:
        cmd = RoverCommandName(parts[0].upper())
    except ValueError as exc:
        raise ValueError(f"Unknown command {parts[0]!r}.") from exc

    if cmd in {
        RoverCommandName.PING,
        RoverCommandName.STOP,
        RoverCommandName.ESTOP,
        RoverCommandName.STATUS,
        RoverCommandName.OBSERVE,
    }:
        if len(parts) != 1:
            raise ValueError(f"{cmd} does not accept arguments.")
        return RoverCommand(cmd=cmd, dialect=ProtocolDialect.TEXT)

    if cmd == RoverCommandName.SET:
        if len(parts) != 3:
            raise ValueError("SET requires left_pwm and right_pwm.")
        return RoverCommand(
            cmd=cmd,
            dialect=ProtocolDialect.TEXT,
            left_pwm=_to_int(parts[1]),
            right_pwm=_to_int(parts[2]),
        )

    if cmd in {RoverCommandName.DRIVE, RoverCommandName.TURN}:
        if len(parts) != 4:
            raise ValueError(f"{cmd} requires left_pwm, right_pwm, and duration_ms.")
        return RoverCommand(
            cmd=cmd,
            dialect=ProtocolDialect.TEXT,
            left_pwm=_to_int(parts[1]),
            right_pwm=_to_int(parts[2]),
            duration_ms=_to_int(parts[3]),
        )

    raise ValueError(f"Unknown command {parts[0]!r}.")


def parse_command_json(line: str) -> RoverCommand:
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise ValueError("JSON command must be an object.")
    cmd_value = str(payload.get("cmd", "")).upper()
    if not cmd_value:
        raise ValueError("JSON command missing cmd.")
    try:
        cmd = RoverCommandName(cmd_value)
    except ValueError as exc:
        raise ValueError(f"Unknown command {cmd_value!r}.") from exc
    return RoverCommand(
        cmd=cmd,
        dialect=ProtocolDialect.JSON,
        left_pwm=payload.get("left_pwm"),
        right_pwm=payload.get("right_pwm"),
        duration_ms=payload.get("duration_ms"),
    )


def serialize_command(command: RoverCommand, dialect: ProtocolDialect | None = None) -> str:
    target = dialect or command.dialect
    if target == ProtocolDialect.JSON:
        payload = {"cmd": command.cmd.value.lower()}
        if command.left_pwm is not None:
            payload["left_pwm"] = command.left_pwm
        if command.right_pwm is not None:
            payload["right_pwm"] = command.right_pwm
        if command.duration_ms is not None:
            payload["duration_ms"] = command.duration_ms
        return json.dumps(payload)

    if command.cmd in {
        RoverCommandName.PING,
        RoverCommandName.STOP,
        RoverCommandName.ESTOP,
        RoverCommandName.STATUS,
        RoverCommandName.OBSERVE,
    }:
        return command.cmd.value
    if command.cmd == RoverCommandName.SET:
        return f"SET {command.left_pwm} {command.right_pwm}"
    return f"{command.cmd.value} {command.left_pwm} {command.right_pwm} {command.duration_ms}"


def encode_response(response: RoverResponse) -> str:
    if response.dialect == ProtocolDialect.JSON:
        payload: dict[str, Any] = {"type": response.response_type.value}
        if response.code is not None:
            payload["code"] = response.code
        if response.message is not None:
            payload["message"] = response.message
        if response.data:
            payload["data"] = response.data
        if response.status is not None:
            payload["status"] = response.status.model_dump(mode="json")
        if response.observation is not None:
            payload["observation"] = response.observation.model_dump(mode="json")
        return json.dumps(payload)

    if response.response_type == RoverResponseType.PONG:
        return "PONG"
    if response.response_type == RoverResponseType.ERROR:
        parts = ["ERR", response.code or "unknown"]
        if response.message:
            parts.append(_sanitize_value(response.message))
        return " ".join(parts)
    if response.response_type == RoverResponseType.STATUS and response.status is not None:
        return "STATUS " + _format_key_values(response.status.model_dump(mode="json"))
    if response.response_type == RoverResponseType.OBSERVATION and response.observation is not None:
        return "OBSERVE " + _format_key_values(response.observation.model_dump(mode="json"))
    if response.data:
        return "OK " + _format_key_values(response.data)
    return "OK"


def guess_dialect(line: str) -> ProtocolDialect:
    stripped = line.lstrip()
    return ProtocolDialect.JSON if stripped.startswith("{") else ProtocolDialect.TEXT


def format_protocol_error(exc: Exception, *, dialect: ProtocolDialect | None = None) -> RoverResponse:
    target = dialect or ProtocolDialect.TEXT
    code = "bad_args"
    if isinstance(exc, json.JSONDecodeError):
        code = "bad_json"
    elif isinstance(exc, ValidationError):
        code = "bad_args"
    elif exc.__class__.__name__ == "RoverBridgeError":
        code = "safety_stop" if "emergency-stop" in str(exc) else "mcu_unavailable"
    elif isinstance(exc, ValueError) and "Unknown command" in str(exc):
        code = "unknown_cmd"
    return RoverResponse.error(dialect=target, code=code, message=str(exc))


def _to_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Expected integer argument, got {value!r}.") from exc


def _validate_pwm(value: int) -> None:
    if not -255 <= value <= 255:
        raise ValueError("PWM must be between -255 and 255.")


def _validate_duration(value: int) -> None:
    if not 1 <= value <= 5000:
        raise ValueError("duration_ms must be between 1 and 5000.")


def _format_key_values(values: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in values.items():
        if isinstance(value, dict):
            parts.append(f"{key}={json.dumps(value, separators=(',', ':'))}")
        elif isinstance(value, list):
            parts.append(f"{key}={json.dumps(value, separators=(',', ':'))}")
        else:
            parts.append(f"{key}={_sanitize_value(value)}")
    return " ".join(parts)


def _sanitize_value(value: Any) -> str:
    return str(value).replace(" ", "_")
