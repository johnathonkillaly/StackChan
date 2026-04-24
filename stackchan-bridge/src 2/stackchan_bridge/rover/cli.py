from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from stackchan_bridge.rover.linux_controller import (
    CyclingObservationProvider,
    FakeBridgeClient,
    RoverLinuxController,
    UnoQRpcClient,
)
from stackchan_bridge.rover.protocol import ProtocolDialect, RoverCommand, parse_command_text, serialize_command
from stackchan_bridge.rover.uart_link import PtyMasterTransport, RealSerialTransport, create_pty_pair


async def run_service(args: argparse.Namespace) -> None:
    observation_states = [value.strip() for value in args.observation_sequence.split(",") if value.strip()]
    provider = CyclingObservationProvider(observation_states or ["unknown"])
    bridge = (
        FakeBridgeClient(source="simulation")
        if args.simulation
        else UnoQRpcClient(
            socket_path=args.rpc_socket or None,
            host=args.rpc_host,
            port=args.rpc_port,
            timeout_seconds=args.rpc_timeout_seconds,
        )
    )
    controller = RoverLinuxController(
        bridge_client=bridge,
        observation_provider=provider,
        loop_interval_ms=args.loop_interval_ms,
    )

    if args.pty:
        pair = create_pty_pair()
        transport = PtyMasterTransport(pair.master_fd, anchor_slave_fd=pair.slave_fd)
        print(f"PTY_SLAVE={pair.slave_path}", flush=True)
    elif args.serial_device:
        transport = RealSerialTransport(args.serial_device, baudrate=args.baudrate)
    else:
        raise SystemExit("serve requires either --serial-device or --pty")

    await controller.start_admin_server(args.admin_socket)
    print(f"ADMIN_SOCKET={args.admin_socket}", flush=True)
    try:
        await controller.serve_uart(transport)
    finally:
        await controller.close()


async def run_admin(args: argparse.Namespace) -> None:
    reader, writer = await asyncio.open_unix_connection(args.admin_socket)
    payload: dict[str, object] = {"command": args.command}
    if args.command == "loop-start" and args.interval_ms is not None:
        payload["interval_ms"] = args.interval_ms
    writer.write((json.dumps(payload) + "\n").encode("utf-8"))
    await writer.drain()
    raw = await reader.readline()
    if raw:
        print(raw.decode("utf-8").strip())
    writer.close()
    await writer.wait_closed()


async def run_replay(args: argparse.Namespace) -> None:
    transport = RealSerialTransport(args.serial_device, baudrate=args.baudrate)
    try:
        commands = load_replay_commands(args)
        dialect = ProtocolDialect(args.dialect)
        for command in commands:
            line = serialize_command(command, dialect=dialect)
            print(f">> {line}")
            await transport.write_line(line)
            response = await transport.read_line()
            print(f"<< {response}")
            if args.delay_ms:
                await asyncio.sleep(args.delay_ms / 1000.0)
    finally:
        await transport.close()


def load_replay_commands(args: argparse.Namespace) -> list[RoverCommand]:
    raw_commands: list[str] = []
    if args.script_file:
        for line in Path(args.script_file).read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            raw_commands.append(stripped)
    raw_commands.extend(args.command or [])
    if not raw_commands:
        raw_commands = ["PING", "STATUS", "DRIVE 120 120 300", "STOP"]
    return [parse_command_text(line) for line in raw_commands]


def build_service_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="StackChan rover Linux service.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    serve = subparsers.add_parser("serve", help="Run the UART rover service.")
    serve.add_argument("--simulation", action="store_true", help="Use the fake MCU bridge instead of UNO Q RPC.")
    serve.add_argument("--serial-device", help="Serial device path for the StackChan UART link.")
    serve.add_argument("--baudrate", type=int, default=115200, help="UART baudrate.")
    serve.add_argument("--pty", action="store_true", help="Create a PTY pair for desktop simulation.")
    serve.add_argument("--admin-socket", default="/tmp/stackchan-rover-admin.sock", help="UNIX socket for admin commands.")
    serve.add_argument(
        "--rpc-socket",
        default="/var/run/arduino-router.sock",
        help="UNO Q router UNIX socket path. Pass an empty string to force TCP host/port mode.",
    )
    serve.add_argument("--rpc-host", default="127.0.0.1", help="UNO Q RPC router host.")
    serve.add_argument("--rpc-port", type=int, default=50051, help="UNO Q RPC router port.")
    serve.add_argument("--rpc-timeout-seconds", type=float, default=2.0, help="UNO Q RPC timeout.")
    serve.add_argument("--loop-interval-ms", type=int, default=500, help="Observe-drive loop interval.")
    serve.add_argument(
        "--observation-sequence",
        default="unknown,clear,blocked_left,blocked_right",
        help="Comma-separated placeholder observation states for simulation.",
    )

    admin = subparsers.add_parser("admin", help="Control a running rover service.")
    admin.add_argument("command", choices=["loop-start", "loop-stop", "loop-status", "emergency-stop", "status"])
    admin.add_argument("--admin-socket", default="/tmp/stackchan-rover-admin.sock", help="UNIX socket for admin commands.")
    admin.add_argument("--interval-ms", type=int, help="Override loop interval when starting the loop.")

    return parser


def build_replay_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay fake StackChan serial commands to the rover service.")
    parser.add_argument("--serial-device", required=True, help="Serial or PTY device path to write to.")
    parser.add_argument("--baudrate", type=int, default=115200, help="UART baudrate.")
    parser.add_argument("--script-file", help="Text file of line-based rover commands.")
    parser.add_argument("--command", action="append", help="Additional line-based commands to send.")
    parser.add_argument("--dialect", choices=["text", "json"], default="text", help="Outbound protocol dialect.")
    parser.add_argument("--delay-ms", type=int, default=50, help="Delay between replayed commands.")
    return parser


def main_service() -> None:
    parser = build_service_parser()
    args = parser.parse_args()
    if args.subcommand == "serve":
        asyncio.run(run_service(args))
        return
    asyncio.run(run_admin(args))


def main_replay() -> None:
    parser = build_replay_parser()
    args = parser.parse_args()
    asyncio.run(run_replay(args))
