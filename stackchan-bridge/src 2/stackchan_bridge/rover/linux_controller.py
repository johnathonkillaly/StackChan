from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING
from uuid import uuid4

import msgpack

from stackchan_bridge.rover.planner import choose_motion
from stackchan_bridge.rover.protocol import (
    LoopState,
    MotionDecision,
    Observation,
    ObserveStepResult,
    ProtocolDialect,
    RoverCommand,
    RoverCommandName,
    RoverResponse,
    RoverStatus,
    encode_response,
    format_protocol_error,
    parse_command_auto,
)

if TYPE_CHECKING:
    from stackchan_bridge.server.device import BridgeDevice
    from stackchan_bridge.rover.uart_link import LineTransport


class RoverBridgeError(RuntimeError):
    """Raised when the Linux-side controller cannot reach the MCU bridge."""


class McuBridgeClient(Protocol):
    async def ping(self) -> Any: ...

    async def motor_stop(self) -> Any: ...

    async def motor_drive(self, left_pwm: int, right_pwm: int, duration_ms: int) -> Any: ...

    async def motor_turn(self, left_pwm: int, right_pwm: int, duration_ms: int) -> Any: ...

    async def motor_set(self, left_pwm: int, right_pwm: int) -> Any: ...

    async def get_status(self) -> Any: ...

    async def emergency_stop(self) -> Any: ...


class ObservationProvider(Protocol):
    async def observe(self, bridge_device: BridgeDevice | None = None) -> Observation: ...


class UnoQRpcClient:
    REQUEST_TYPE = 0
    RESPONSE_TYPE = 1

    def __init__(
        self,
        *,
        socket_path: str | None = "/var/run/arduino-router.sock",
        host: str = "127.0.0.1",
        port: int = 50051,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.socket_path = socket_path
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    async def ping(self) -> Any:
        return await self._call("ping")

    async def motor_stop(self) -> Any:
        return await self._call("motor_stop")

    async def motor_drive(self, left_pwm: int, right_pwm: int, duration_ms: int) -> Any:
        return await self._call("motor_drive", left_pwm, right_pwm, duration_ms)

    async def motor_turn(self, left_pwm: int, right_pwm: int, duration_ms: int) -> Any:
        return await self._call("motor_turn", left_pwm, right_pwm, duration_ms)

    async def motor_set(self, left_pwm: int, right_pwm: int) -> Any:
        return await self._call("motor_set", left_pwm, right_pwm)

    async def get_status(self) -> Any:
        return await self._call("get_status")

    async def emergency_stop(self) -> Any:
        return await self._call("emergency_stop")

    async def _call(self, method: str, *params: Any) -> Any:
        request_id = int(uuid4().int & 0x7FFFFFFF)
        message = [self.REQUEST_TYPE, request_id, method, list(params)]
        packed = msgpack.packb(message, use_bin_type=True)

        try:
            reader, writer = await asyncio.wait_for(
                self._open_connection(),
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - network failure path
            raise RoverBridgeError(f"Unable to connect to UNO Q RPC bridge at {self._target_label()}") from exc

        unpacker = msgpack.Unpacker(raw=False)
        try:
            writer.write(packed)
            await asyncio.wait_for(writer.drain(), timeout=self.timeout_seconds)

            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=self.timeout_seconds)
                if not chunk:
                    break
                unpacker.feed(chunk)
                for decoded in unpacker:
                    if not isinstance(decoded, list) or len(decoded) < 4:
                        continue
                    if decoded[0] != self.RESPONSE_TYPE or decoded[1] != request_id:
                        continue
                    error = decoded[2]
                    result = decoded[3]
                    if error:
                        raise RoverBridgeError(f"RPC {method} failed: {error}")
                    return result
        finally:
            writer.close()
            await writer.wait_closed()

        raise RoverBridgeError(f"RPC {method} returned no response")

    async def _open_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self.socket_path:
            return await asyncio.open_unix_connection(self.socket_path)
        return await asyncio.open_connection(self.host, self.port)

    def _target_label(self) -> str:
        if self.socket_path:
            return self.socket_path
        return f"{self.host}:{self.port}"


class FakeBridgeClient:
    def __init__(self, *, battery_mv: int = 7600, source: str = "simulation") -> None:
        self.call_log: list[dict[str, Any]] = []
        self._status = RoverStatus(
            source=source,
            motors="stopped",
            left_pwm=0,
            right_pwm=0,
            watchdog_ok=True,
            emergency_stop=False,
            last_cmd="INIT",
            loop_running=False,
            battery_mv=battery_mv,
        )

    async def ping(self) -> dict[str, Any]:
        self._record("ping")
        return {"reply": "pong"}

    async def motor_stop(self) -> dict[str, Any]:
        self._record("motor_stop")
        self._status.motors = "stopped"
        self._status.left_pwm = 0
        self._status.right_pwm = 0
        self._status.last_cmd = "STOP"
        return {"ok": True}

    async def motor_drive(self, left_pwm: int, right_pwm: int, duration_ms: int) -> dict[str, Any]:
        self._record("motor_drive", left_pwm=left_pwm, right_pwm=right_pwm, duration_ms=duration_ms)
        self._status.motors = "driving"
        self._status.left_pwm = left_pwm
        self._status.right_pwm = right_pwm
        self._status.last_cmd = "DRIVE"
        return {"ok": True}

    async def motor_turn(self, left_pwm: int, right_pwm: int, duration_ms: int) -> dict[str, Any]:
        self._record("motor_turn", left_pwm=left_pwm, right_pwm=right_pwm, duration_ms=duration_ms)
        self._status.motors = "turning"
        self._status.left_pwm = left_pwm
        self._status.right_pwm = right_pwm
        self._status.last_cmd = "TURN"
        return {"ok": True}

    async def motor_set(self, left_pwm: int, right_pwm: int) -> dict[str, Any]:
        self._record("motor_set", left_pwm=left_pwm, right_pwm=right_pwm)
        self._status.motors = "manual"
        self._status.left_pwm = left_pwm
        self._status.right_pwm = right_pwm
        self._status.last_cmd = "SET"
        return {"ok": True}

    async def get_status(self) -> dict[str, Any]:
        self._record("get_status")
        return self._status.model_dump(mode="json")

    async def emergency_stop(self) -> dict[str, Any]:
        self._record("emergency_stop")
        self._status.emergency_stop = True
        self._status.motors = "stopped"
        self._status.left_pwm = 0
        self._status.right_pwm = 0
        self._status.last_cmd = "ESTOP"
        return {"ok": True}

    def _record(self, method: str, **kwargs: Any) -> None:
        self.call_log.append({"method": method, **kwargs})


class CyclingObservationProvider:
    def __init__(self, states: list[str] | tuple[str, ...] | None = None) -> None:
        self.states = list(states or ["unknown"])
        self._index = 0

    async def observe(self, bridge_device: BridgeDevice | None = None) -> Observation:
        state = self.states[self._index % len(self.states)]
        self._index += 1
        return Observation(state=state, source="sequence")


class SnapshotPlaceholderObservationProvider:
    async def observe(self, bridge_device: BridgeDevice | None = None) -> Observation:
        if bridge_device is not None:
            hint = bridge_device.record.metadata.get("rover_observation_hint")
            if hint in {"clear", "blocked_left", "blocked_right", "blocked_ahead", "unknown"}:
                return Observation(state=hint, source="metadata_hint")
            if bridge_device.latest_snapshot:
                return Observation(
                    state="clear",
                    source="snapshot_placeholder",
                    details={"byte_length": len(bridge_device.latest_snapshot)},
                )
        return Observation(state="unknown", source="placeholder")


@dataclass(slots=True)
class RoverLinuxController:
    bridge_client: McuBridgeClient
    observation_provider: ObservationProvider
    loop_interval_ms: int = 500
    _command_lock: asyncio.Lock = field(init=False, repr=False)
    _loop_stop_event: asyncio.Event = field(init=False, repr=False)
    _loop_task: asyncio.Task[None] | None = field(init=False, default=None, repr=False)
    _last_command: str = field(init=False, default="INIT", repr=False)
    _emergency_stopped: bool = field(init=False, default=False, repr=False)
    _loop_state: LoopState = field(init=False, repr=False)
    _admin_server: asyncio.AbstractServer | None = field(init=False, default=None, repr=False)
    _admin_socket_path: Path | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._command_lock = asyncio.Lock()
        self._loop_stop_event = asyncio.Event()
        self._loop_state = LoopState(interval_ms=self.loop_interval_ms)

    async def execute_command(
        self,
        command: RoverCommand,
        *,
        bridge_device: BridgeDevice | None = None,
    ) -> RoverResponse:
        if command.cmd == RoverCommandName.PING:
            await self.ping()
            return RoverResponse.pong(dialect=command.dialect)
        if command.cmd == RoverCommandName.STOP:
            status = await self.stop()
            return RoverResponse.from_status(dialect=command.dialect, status=status)
        if command.cmd == RoverCommandName.ESTOP:
            status = await self.emergency_stop()
            return RoverResponse.from_status(dialect=command.dialect, status=status)
        if command.cmd == RoverCommandName.STATUS:
            return RoverResponse.from_status(dialect=command.dialect, status=await self.status())
        if command.cmd == RoverCommandName.OBSERVE:
            return RoverResponse.from_observation(dialect=command.dialect, observation=await self.observe(bridge_device))
        if command.cmd == RoverCommandName.SET:
            status = await self.set(command.left_pwm or 0, command.right_pwm or 0)
            return RoverResponse.from_status(dialect=command.dialect, status=status)
        if command.cmd == RoverCommandName.DRIVE:
            status = await self.drive(command.left_pwm or 0, command.right_pwm or 0, command.duration_ms or 0)
            return RoverResponse.from_status(dialect=command.dialect, status=status)
        if command.cmd == RoverCommandName.TURN:
            status = await self.turn(command.left_pwm or 0, command.right_pwm or 0, command.duration_ms or 0)
            return RoverResponse.from_status(dialect=command.dialect, status=status)
        return RoverResponse.error(dialect=command.dialect, code="unknown_cmd", message=f"Unsupported command {command.cmd}")

    async def ping(self) -> Any:
        async with self._command_lock:
            self._last_command = "PING"
            return await self.bridge_client.ping()

    async def stop(self) -> RoverStatus:
        async with self._command_lock:
            self._last_command = "STOP"
            await self.bridge_client.motor_stop()
        return await self.status()

    async def drive(self, left_pwm: int, right_pwm: int, duration_ms: int) -> RoverStatus:
        await self._ensure_not_estopped()
        async with self._command_lock:
            self._last_command = "DRIVE"
            await self.bridge_client.motor_drive(left_pwm, right_pwm, duration_ms)
        return await self.status()

    async def turn(self, left_pwm: int, right_pwm: int, duration_ms: int) -> RoverStatus:
        await self._ensure_not_estopped()
        async with self._command_lock:
            self._last_command = "TURN"
            await self.bridge_client.motor_turn(left_pwm, right_pwm, duration_ms)
        return await self.status()

    async def set(self, left_pwm: int, right_pwm: int) -> RoverStatus:
        await self._ensure_not_estopped()
        async with self._command_lock:
            self._last_command = "SET"
            await self.bridge_client.motor_set(left_pwm, right_pwm)
        return await self.status()

    async def status(self) -> RoverStatus:
        async with self._command_lock:
            raw = await self.bridge_client.get_status()
        status = _coerce_status_payload(raw)
        if not isinstance(self.bridge_client, FakeBridgeClient) and status.source == "simulation":
            status.source = "uno_q_rpc"
        if not status.last_cmd or status.last_cmd == "INIT":
            status.last_cmd = self._last_command
        status.loop_running = self._loop_state.running
        status.emergency_stop = self._emergency_stopped or status.emergency_stop
        return status

    async def emergency_stop(self) -> RoverStatus:
        async with self._command_lock:
            self._last_command = "ESTOP"
            self._emergency_stopped = True
            await self.bridge_client.emergency_stop()
        self._loop_state.emergency_stop = True
        await self.stop_loop()
        return await self.status()

    async def clear_emergency_stop(self) -> RoverStatus:
        self._emergency_stopped = False
        self._loop_state.emergency_stop = False
        return await self.stop()

    async def observe(self, bridge_device: BridgeDevice | None = None) -> Observation:
        observation = await self.observation_provider.observe(bridge_device)
        self._loop_state.last_observation = observation
        return observation

    async def observe_step(self, bridge_device: BridgeDevice | None = None) -> ObserveStepResult:
        if self._emergency_stopped:
            status = await self.status()
            observation = Observation(state="unknown", source="emergency_stop")
            decision = MotionDecision(action="stop", reason="emergency_stop")
            self._loop_state.last_observation = observation
            self._loop_state.last_decision = decision
            return ObserveStepResult(observation=observation, decision=decision, status=status)

        await self.stop()
        observation = await self.observe(bridge_device)
        decision = choose_motion(observation)
        self._loop_state.last_decision = decision

        if decision.action == "drive":
            await self.drive(decision.left_pwm, decision.right_pwm, decision.duration_ms)
        elif decision.action == "turn":
            await self.turn(decision.left_pwm, decision.right_pwm, decision.duration_ms)

        status = await self.stop()
        return ObserveStepResult(observation=observation, decision=decision, status=status)

    async def start_loop(self) -> LoopState:
        if self._loop_state.running:
            return self._loop_state
        await self._ensure_not_estopped()
        self._loop_stop_event = asyncio.Event()
        self._loop_state.running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        return self._loop_state

    async def stop_loop(self) -> LoopState:
        self._loop_stop_event.set()
        if self._loop_task is not None:
            await self._loop_task
            self._loop_task = None
        self._loop_state.running = False
        return self._loop_state

    def loop_status(self) -> LoopState:
        return self._loop_state

    async def serve_uart(self, transport: LineTransport) -> None:
        try:
            while True:
                line = await transport.read_line()
                if line is None:
                    break
                line = line.strip()
                if not line:
                    continue

                dialect = ProtocolDialect.JSON if line.lstrip().startswith("{") else ProtocolDialect.TEXT
                try:
                    command = parse_command_auto(line)
                    response = await self.execute_command(command)
                except Exception as exc:
                    response = format_protocol_error(exc, dialect=dialect)
                await transport.write_line(encode_response(response))
        finally:
            await transport.close()

    async def start_admin_server(self, socket_path: str | Path) -> None:
        path = Path(socket_path)
        if path.exists():
            path.unlink()
        self._admin_socket_path = path
        self._admin_server = await asyncio.start_unix_server(self._handle_admin_client, path=str(path))

    async def stop_admin_server(self) -> None:
        if self._admin_server is not None:
            self._admin_server.close()
            await self._admin_server.wait_closed()
            self._admin_server = None
        if self._admin_socket_path and self._admin_socket_path.exists():
            self._admin_socket_path.unlink()

    async def close(self) -> None:
        await self.stop_loop()
        await self.stop_admin_server()

    async def _handle_admin_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await reader.readline()
            if not raw:
                return
            payload = json.loads(raw.decode("utf-8"))
            response = await self.handle_admin_command(payload)
            writer.write((json.dumps(response) + "\n").encode("utf-8"))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def handle_admin_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = payload.get("command")
        if command == "loop-start":
            interval_ms = payload.get("interval_ms")
            if isinstance(interval_ms, int) and interval_ms > 0:
                self.loop_interval_ms = interval_ms
                self._loop_state.interval_ms = interval_ms
            state = await self.start_loop()
            return {"ok": True, "loop": state.model_dump(mode="json")}
        if command == "loop-stop":
            state = await self.stop_loop()
            return {"ok": True, "loop": state.model_dump(mode="json")}
        if command == "loop-status":
            return {"ok": True, "loop": self.loop_status().model_dump(mode="json")}
        if command == "emergency-stop":
            status = await self.emergency_stop()
            return {"ok": True, "status": status.model_dump(mode="json")}
        if command == "status":
            status = await self.status()
            return {"ok": True, "status": status.model_dump(mode="json")}
        return {"ok": False, "error": "unknown_admin_command"}

    async def _run_loop(self) -> None:
        while not self._loop_stop_event.is_set():
            try:
                await self.observe_step()
                self._loop_state.iterations += 1
                self._loop_state.last_error = None
            except Exception as exc:
                self._loop_state.last_error = str(exc)
                await self.stop()
            try:
                await asyncio.wait_for(
                    self._loop_stop_event.wait(),
                    timeout=self.loop_interval_ms / 1000.0,
                )
            except asyncio.TimeoutError:
                continue
        self._loop_state.running = False

    async def _ensure_not_estopped(self) -> None:
        if self._emergency_stopped:
            raise RoverBridgeError("Rover is in emergency-stop state.")


def _coerce_status_payload(raw: Any) -> RoverStatus:
    if isinstance(raw, RoverStatus):
        return raw
    if isinstance(raw, dict):
        return RoverStatus.model_validate(raw)
    if isinstance(raw, (bytes, bytearray)):
        return _coerce_status_payload(raw.decode("utf-8", errors="replace"))
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return RoverStatus()
        if stripped.startswith("{"):
            return RoverStatus.model_validate(json.loads(stripped))
        return RoverStatus.model_validate(_parse_key_value_payload(stripped))
    raise RoverBridgeError(f"Unsupported status payload type: {type(raw).__name__}")


def _parse_key_value_payload(line: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for token in line.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        payload[key] = _parse_scalar(value)
    return payload


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value
