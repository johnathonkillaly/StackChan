from __future__ import annotations

import asyncio
import json
import tempfile

import msgpack

from stackchan_bridge.rover.linux_controller import (
    CyclingObservationProvider,
    FakeBridgeClient,
    RoverLinuxController,
    UnoQRpcClient,
)
from stackchan_bridge.rover.uart_link import create_memory_transport_pair


async def _admin_request(socket_path: str, payload: dict) -> dict:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    writer.write((json.dumps(payload) + "\n").encode("utf-8"))
    await writer.drain()
    response = json.loads((await reader.readline()).decode("utf-8"))
    writer.close()
    await writer.wait_closed()
    return response


def test_uart_dispatch_calls_fake_bridge() -> None:
    async def run() -> None:
        bridge = FakeBridgeClient()
        controller = RoverLinuxController(
            bridge_client=bridge,
            observation_provider=CyclingObservationProvider(["clear"]),
        )
        service_transport, client_transport = create_memory_transport_pair()
        task = asyncio.create_task(controller.serve_uart(service_transport))

        await client_transport.write_line("PING")
        assert await client_transport.read_line() == "PONG"

        await client_transport.write_line("DRIVE 120 120 300")
        assert (await client_transport.read_line()).startswith("STATUS ")

        await client_transport.write_line("STATUS")
        assert (await client_transport.read_line()).startswith("STATUS ")

        await client_transport.close()
        await task
        assert [entry["method"] for entry in bridge.call_log] == [
            "ping",
            "motor_drive",
            "get_status",
            "get_status",
        ]

    asyncio.run(run())


def test_admin_loop_commands_start_and_stop() -> None:
    async def run() -> None:
        bridge = FakeBridgeClient()
        controller = RoverLinuxController(
            bridge_client=bridge,
            observation_provider=CyclingObservationProvider(["clear"]),
            loop_interval_ms=10,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = f"{tmpdir}/rover-admin.sock"
            await controller.start_admin_server(socket_path)

            start = await _admin_request(socket_path, {"command": "loop-start", "interval_ms": 10})
            assert start["ok"] is True
            assert start["loop"]["running"] is True

            await asyncio.sleep(0.05)
            status = await _admin_request(socket_path, {"command": "loop-status"})
            assert status["loop"]["iterations"] >= 1

            stop = await _admin_request(socket_path, {"command": "loop-stop"})
            assert stop["loop"]["running"] is False
            await controller.close()

    asyncio.run(run())


def test_status_parses_json_string_from_bridge() -> None:
    class JsonStatusBridge:
        async def ping(self) -> str:
            return "pong"

        async def motor_stop(self) -> str:
            return "OK action=motor_stop"

        async def motor_drive(self, left_pwm: int, right_pwm: int, duration_ms: int) -> str:
            return "OK action=motor_drive"

        async def motor_turn(self, left_pwm: int, right_pwm: int, duration_ms: int) -> str:
            return "OK action=motor_turn"

        async def motor_set(self, left_pwm: int, right_pwm: int) -> str:
            return "OK action=motor_set"

        async def get_status(self) -> str:
            return '{"source":"uno_q_mcu","motors":"stopped","left_pwm":0,"right_pwm":0,"watchdog_ok":true,"emergency_stop":false,"last_cmd":"WATCHDOG_STOP"}'

        async def emergency_stop(self) -> str:
            return "OK action=emergency_stop"

    async def run() -> None:
        controller = RoverLinuxController(
            bridge_client=JsonStatusBridge(),
            observation_provider=CyclingObservationProvider(["clear"]),
        )
        status = await controller.status()
        assert status.source == "uno_q_mcu"
        assert status.last_cmd == "WATCHDOG_STOP"
        assert status.watchdog_ok is True

    asyncio.run(run())


def test_uno_q_rpc_client_uses_unix_socket() -> None:
    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        unpacker = msgpack.Unpacker(raw=False)
        chunk = await reader.read(4096)
        unpacker.feed(chunk)
        message = next(iter(unpacker))
        assert message[0] == 0
        assert message[2] == "get_status"
        response = [
            1,
            message[1],
            None,
            '{"source":"uno_q_mcu","motors":"stopped","left_pwm":0,"right_pwm":0,"watchdog_ok":true,"emergency_stop":false,"last_cmd":"STOP"}',
        ]
        writer.write(msgpack.packb(response, use_bin_type=True))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def run() -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = f"{tmpdir}/router.sock"
            server = await asyncio.start_unix_server(handle_client, path=socket_path)
            try:
                client = UnoQRpcClient(socket_path=socket_path, timeout_seconds=1.0)
                response = await client.get_status()
                assert "uno_q_mcu" in response
            finally:
                server.close()
                await server.wait_closed()

    asyncio.run(run())


def test_emergency_stop_interrupts_motion() -> None:
    async def run() -> None:
        bridge = FakeBridgeClient()
        controller = RoverLinuxController(
            bridge_client=bridge,
            observation_provider=CyclingObservationProvider(["clear"]),
        )

        status = await controller.emergency_stop()
        assert status.emergency_stop is True
        result = await controller.observe_step()
        assert result.decision.action == "stop"
        assert result.status.emergency_stop is True

    asyncio.run(run())
