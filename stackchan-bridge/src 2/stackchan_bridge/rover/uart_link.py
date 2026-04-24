from __future__ import annotations

import asyncio
import errno
import os
import pty
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class LineTransport(Protocol):
    async def read_line(self) -> str | None: ...

    async def write_line(self, line: str) -> None: ...

    async def close(self) -> None: ...


class RealSerialTransport:
    def __init__(self, device: str | Path, *, baudrate: int = 115200, timeout: float = 1.0) -> None:
        import serial

        self.device = str(device)
        self._serial = serial.Serial(self.device, baudrate=baudrate, timeout=timeout)

    async def read_line(self) -> str | None:
        raw = await asyncio.to_thread(self._serial.readline)
        if raw == b"":
            return None
        return raw.decode("utf-8", errors="replace").strip()

    async def write_line(self, line: str) -> None:
        payload = line if line.endswith("\n") else f"{line}\n"
        await asyncio.to_thread(self._serial.write, payload.encode("utf-8"))
        await asyncio.to_thread(self._serial.flush)

    async def close(self) -> None:
        await asyncio.to_thread(self._serial.close)


@dataclass(slots=True)
class InMemoryTransport:
    _rx: asyncio.Queue[str | None]
    _tx: asyncio.Queue[str | None]

    async def read_line(self) -> str | None:
        value = await self._rx.get()
        if value is None:
            return None
        return value.rstrip("\n")

    async def write_line(self, line: str) -> None:
        payload = line if line.endswith("\n") else f"{line}\n"
        await self._tx.put(payload)

    async def close(self) -> None:
        await self._tx.put(None)


def create_memory_transport_pair() -> tuple[InMemoryTransport, InMemoryTransport]:
    left_rx: asyncio.Queue[str | None] = asyncio.Queue()
    right_rx: asyncio.Queue[str | None] = asyncio.Queue()
    return InMemoryTransport(left_rx, right_rx), InMemoryTransport(right_rx, left_rx)


class LoopbackTransport:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def read_line(self) -> str | None:
        value = await self._queue.get()
        if value is None:
            return None
        return value.rstrip("\n")

    async def write_line(self, line: str) -> None:
        payload = line if line.endswith("\n") else f"{line}\n"
        await self._queue.put(payload)

    async def close(self) -> None:
        await self._queue.put(None)


@dataclass(slots=True)
class PtyPair:
    master_fd: int
    slave_fd: int
    slave_path: str


def create_pty_pair() -> PtyPair:
    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)
    return PtyPair(master_fd=master_fd, slave_fd=slave_fd, slave_path=slave_path)


class PtyMasterTransport:
    def __init__(self, master_fd: int, *, anchor_slave_fd: int | None = None) -> None:
        self.master_fd = master_fd
        self.anchor_slave_fd = anchor_slave_fd
        self._buffer = bytearray()
        self._closed = False

    async def read_line(self) -> str | None:
        while b"\n" not in self._buffer:
            try:
                chunk = await asyncio.to_thread(os.read, self.master_fd, 1024)
            except OSError as exc:
                if exc.errno == errno.EIO and not self._closed:
                    await asyncio.sleep(0.05)
                    continue
                return None
            if not chunk:
                await asyncio.sleep(0.05)
                continue
            self._buffer.extend(chunk)

        line, _, remainder = self._buffer.partition(b"\n")
        self._buffer = bytearray(remainder)
        return line.decode("utf-8", errors="replace").strip()

    async def write_line(self, line: str) -> None:
        payload = line if line.endswith("\n") else f"{line}\n"
        await asyncio.to_thread(os.write, self.master_fd, payload.encode("utf-8"))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.anchor_slave_fd is not None:
            await asyncio.to_thread(os.close, self.anchor_slave_fd)
        await asyncio.to_thread(os.close, self.master_fd)
