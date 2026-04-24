from __future__ import annotations

import json

import pytest

from stackchan_bridge.rover.protocol import (
    Observation,
    ProtocolDialect,
    RoverCommandName,
    RoverResponse,
    RoverStatus,
    encode_response,
    format_protocol_error,
    parse_command_auto,
    parse_command_text,
    serialize_command,
)


def test_text_protocol_parses_and_serializes_drive() -> None:
    command = parse_command_text("DRIVE 120 120 300")
    assert command.cmd == RoverCommandName.DRIVE
    assert command.left_pwm == 120
    assert command.right_pwm == 120
    assert command.duration_ms == 300
    assert serialize_command(command) == "DRIVE 120 120 300"


def test_json_protocol_parses_and_serializes_turn() -> None:
    command = parse_command_auto('{"cmd":"turn","left_pwm":-120,"right_pwm":120,"duration_ms":180}')
    assert command.dialect == ProtocolDialect.JSON
    assert command.cmd == RoverCommandName.TURN
    assert command.left_pwm == -120
    payload = json.loads(serialize_command(command, dialect=ProtocolDialect.JSON))
    assert payload["cmd"] == "turn"
    assert payload["duration_ms"] == 180


def test_text_and_json_responses_mirror_dialects() -> None:
    status = RoverStatus(source="simulation", last_cmd="STATUS", loop_running=False)
    text = encode_response(RoverResponse.from_status(dialect=ProtocolDialect.TEXT, status=status))
    assert text.startswith("STATUS ")

    obs = Observation(state="clear", source="test")
    encoded = encode_response(RoverResponse.from_observation(dialect=ProtocolDialect.JSON, observation=obs))
    payload = json.loads(encoded)
    assert payload["type"] == "observation"
    assert payload["observation"]["state"] == "clear"


def test_protocol_rejects_invalid_args_and_unknown_commands() -> None:
    with pytest.raises(ValueError):
        parse_command_text("DRIVE 999 0 10")

    unknown = format_protocol_error(ValueError("Unknown command 'FLY'"), dialect=ProtocolDialect.TEXT)
    assert encode_response(unknown).startswith("ERR unknown_cmd")

    bad_json = format_protocol_error(json.JSONDecodeError("bad", "{}", 1), dialect=ProtocolDialect.JSON)
    assert json.loads(encode_response(bad_json))["code"] == "bad_json"

