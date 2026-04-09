"""Traffic capture, logging, and replay for FF55 protocol analysis."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from ..transport.base import Transport
from .ff55 import find_packets


@dataclass
class CaptureEntry:
    """A single captured traffic entry."""

    timestamp: float  # epoch seconds with ms precision
    direction: str  # "tx" or "rx"
    raw: bytes  # raw bytes
    decoded: dict | None  # decoded FF55 packet fields, or None if not parseable


class CaptureTransport:
    """Transport wrapper that captures all TX/RX traffic.

    Wraps any Transport implementation, tees all bytes to a JSONL log file.
    The wrapped transport is used for actual I/O.
    """

    def __init__(self, inner: Transport, log_path: Path | None = None):
        """Initialize the capture transport.

        Args:
            inner: The actual transport to wrap.
            log_path: Path to JSONL log file. If None, capture to memory only.
        """
        self._inner = inner
        self._log_file: TextIO | None = None
        self._log_path = log_path
        self._entries: list[CaptureEntry] = []

        if log_path:
            self._log_file = open(log_path, "a", encoding="utf-8")

    def connect(self, target: str) -> None:
        """Open connection to target via the inner transport."""
        self._inner.connect(target)

    def disconnect(self) -> None:
        """Close the connection via the inner transport."""
        self._inner.disconnect()

    def send(self, data: bytes) -> None:
        """Send data via the inner transport and record as TX."""
        self._inner.send(data)
        self._record("tx", data)

    def receive(self, timeout: float = 1.0) -> bytes:
        """Receive data via the inner transport and record as RX if non-empty."""
        data = self._inner.receive(timeout)
        if data:
            self._record("rx", data)
        return data

    @property
    def is_connected(self) -> bool:
        """Whether the inner transport has an active connection."""
        return self._inner.is_connected

    def _record(self, direction: str, data: bytes) -> None:
        """Record a traffic entry.

        Attempts to decode the data as FF55 packets. If successful, stores
        the decoded fields alongside the raw bytes.

        Args:
            direction: Either "tx" or "rx".
            data: The raw bytes to record.
        """
        decoded = None
        packets = find_packets(data)
        if packets:
            pkt = packets[0][0]  # Take first packet
            decoded = {
                "index": pkt.index,
                "action": pkt.action.name,
                "device": f"0x{pkt.device:02X}",
                "data_hex": pkt.data.hex(),
                "data_len": len(pkt.data),
            }

        entry = CaptureEntry(
            timestamp=time.time(),
            direction=direction,
            raw=data,
            decoded=decoded,
        )
        self._entries.append(entry)

        if self._log_file:
            line = json.dumps({
                "ts": entry.timestamp,
                "dir": entry.direction,
                "raw": entry.raw.hex(),
                "decoded": entry.decoded,
            })
            self._log_file.write(line + "\n")
            self._log_file.flush()

    @property
    def entries(self) -> list[CaptureEntry]:
        """Return a copy of all captured entries."""
        return list(self._entries)

    def clear(self) -> None:
        """Clear all captured entries from memory."""
        self._entries.clear()

    def close(self) -> None:
        """Close the log file."""
        if self._log_file:
            self._log_file.close()
            self._log_file = None


def load_capture(path: Path) -> list[CaptureEntry]:
    """Load capture entries from a JSONL file.

    Args:
        path: Path to the JSONL capture file.

    Returns:
        List of CaptureEntry instances.
    """
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            entries.append(CaptureEntry(
                timestamp=data["ts"],
                direction=data["dir"],
                raw=bytes.fromhex(data["raw"]),
                decoded=data.get("decoded"),
            ))
    return entries


def format_hex_dump(entries: list[CaptureEntry]) -> str:
    """Format capture entries as annotated hex dump.

    Output format::

        TX 14:32:01.003  FF 55 05 01 01 1E 00 00
                         ^^^^^ hdr  ^len ^idx ^act ^dev ^data...
        RX 14:32:01.015  FF 55 04 01 02 1A 3F
                         ^^^^^ hdr  ^len ^idx ^act ^dev

    Args:
        entries: List of CaptureEntry instances to format.

    Returns:
        Multi-line formatted string.
    """
    lines = []
    for entry in entries:
        # Format timestamp as HH:MM:SS.mmm
        ts = time.localtime(entry.timestamp)
        ms = int((entry.timestamp % 1) * 1000)
        ts_str = f"{ts.tm_hour:02d}:{ts.tm_min:02d}:{ts.tm_sec:02d}.{ms:03d}"

        direction = entry.direction.upper()
        hex_bytes = " ".join(f"{b:02X}" for b in entry.raw)

        lines.append(f"{direction} {ts_str}  {hex_bytes}")

        # Add annotation line if this is an FF55 packet
        if entry.decoded:
            prefix = " " * (len(direction) + 1 + len(ts_str) + 2)
            annotation = prefix + "^^^^^ hdr  ^len ^idx ^act ^dev"
            if entry.decoded.get("data_len", 0) > 0:
                annotation += " ^data..."
            lines.append(annotation)

    return "\n".join(lines)
