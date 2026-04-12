# CyberPi Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor MakeBlock Explorer from FF55 to F3 protocol, add FastAPI backend with WebSocket sensor streaming, and build a Next.js dashboard with live sensors, device controls, and push notifications to CyberPi.

**Architecture:** Python FastAPI server owns serial connections via background-threaded DeviceManagers. F3 protocol engine encodes MicroPython scripts into framed packets. Next.js React frontend connects via WebSocket (live sensors) and REST (commands). Multi-device support via DeviceRegistry managing multiple DeviceManager instances.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pyserial, Next.js 14+ (App Router), React 18+, Tailwind CSS, Recharts, native WebSocket.

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `src/makeblock_explorer/protocol/f3.py` | F3/F4 packet encode/decode, frame finding, constants |
| `src/makeblock_explorer/device/__init__.py` | Package init, exports DeviceManager + DeviceRegistry |
| `src/makeblock_explorer/device/manager.py` | Single-device serial bridge thread with async command interface |
| `src/makeblock_explorer/device/registry.py` | Multi-device registry: scan, connect, disconnect, route |
| `src/makeblock_explorer/api/__init__.py` | Package init |
| `src/makeblock_explorer/api/server.py` | FastAPI app factory, CORS, lifespan, mount routes |
| `src/makeblock_explorer/api/models.py` | Pydantic request/response schemas |
| `src/makeblock_explorer/api/routes/__init__.py` | Package init |
| `src/makeblock_explorer/api/routes/devices.py` | GET /api/devices, POST /api/connect, POST /api/disconnect, GET /api/status |
| `src/makeblock_explorer/api/routes/commands.py` | POST /api/command, POST /api/led, POST /api/notify |
| `src/makeblock_explorer/api/routes/stream.py` | WS /api/stream — WebSocket sensor broadcast |
| `tests/test_f3.py` | F3 protocol unit tests |
| `tests/test_manager.py` | DeviceManager unit tests (mocked serial) |
| `tests/test_api.py` | FastAPI endpoint integration tests |
| `web/` | Entire Next.js frontend (scaffolded in Task 5) |

### Modified Files
| File | Changes |
|------|---------|
| `src/makeblock_explorer/protocol/__init__.py` | Add F3 exports alongside existing FF55 exports |
| `src/makeblock_explorer/__init__.py` | Update description |
| `pyproject.toml` | Add fastapi, uvicorn, websockets, httpx dependencies; add `mbx-server` script entry |

### Preserved (No Changes)
| File | Reason |
|------|--------|
| `src/makeblock_explorer/protocol/ff55.py` | Valid for mBot/MegaPi — keep as-is |
| `src/makeblock_explorer/protocol/types.py` | Shared data type encoding — still useful |
| `src/makeblock_explorer/protocol/capture.py` | Traffic capture — still useful |
| `src/makeblock_explorer/transport/base.py` | DeviceInfo + scan_serial_ports — reused by DeviceRegistry |
| `src/makeblock_explorer/transport/serial.py` | SerialTransport — reused by DeviceManager |
| `tests/test_ff55.py` | All 48 existing tests stay green |
| `tests/test_transport.py` | All 22 existing tests stay green |
| `tests/test_capture.py` | All 24 existing tests stay green |
| `tests/test_registry.py` | All 15 existing tests stay green |
| `tests/test_cli.py` | All 6 existing tests stay green |

---

## Task 1: F3 Protocol Engine

**Files:**
- Create: `src/makeblock_explorer/protocol/f3.py`
- Create: `tests/test_f3.py`
- Modify: `src/makeblock_explorer/protocol/__init__.py`

### Step 1.1: Write failing tests for `build_f3_packet`

- [ ] Create `tests/test_f3.py` with packet building tests:

```python
"""Tests for F3/F4 protocol engine."""

import pytest

from makeblock_explorer.protocol.f3 import (
    F3Packet,
    F3Response,
    build_f3_packet,
    parse_f3_response,
    find_f3_frames,
    HEADER,
    FOOTER,
    ONLINE_MODE_PACKET,
    OFFLINE_MODE_PACKET,
    PacketType,
    Mode,
)


class TestBuildF3Packet:
    """Test F3 packet building."""

    def test_simple_script_packet(self):
        """Build a basic script packet and verify structure."""
        packet = build_f3_packet("cyberpi.get_bri()", index=1, mode=Mode.WITH_RESPONSE)
        assert packet[0] == 0xF3  # header
        assert packet[-1] == 0xF4  # footer
        # Script bytes should be in the payload
        assert b"cyberpi.get_bri()" in packet

    def test_header_checksum(self):
        """Header checksum = (0xF3 + datalen_lo + datalen_hi) & 0xFF."""
        packet = build_f3_packet("x", index=1, mode=Mode.WITH_RESPONSE)
        datalen_lo = packet[2]
        datalen_hi = packet[3]
        expected_checksum = (0xF3 + datalen_lo + datalen_hi) & 0xFF
        assert packet[1] == expected_checksum

    def test_body_checksum(self):
        """Body checksum = (type + mode + idx_lo + idx_hi + sum(data)) & 0xFF."""
        packet = build_f3_packet("hi", index=5, mode=Mode.WITHOUT_RESPONSE)
        type_byte = packet[4]
        mode_byte = packet[5]
        idx_lo = packet[6]
        idx_hi = packet[7]
        data_bytes = packet[8:-2]  # between idx_hi and body_checksum
        expected = (type_byte + mode_byte + idx_lo + idx_hi + sum(data_bytes)) & 0xFF
        assert packet[-2] == expected

    def test_datalen_includes_header_fields(self):
        """DataLen = len(script_data) + 4 (for type, mode, idx_lo, idx_hi)."""
        script = "test"
        packet = build_f3_packet(script, index=1, mode=Mode.WITH_RESPONSE)
        datalen = packet[2] + (packet[3] << 8)
        # data = [script_len_lo, script_len_hi] + script_bytes
        # datalen = len(data) + 4
        expected = len(script.encode("utf-8")) + 2 + 4  # +2 for script_len prefix
        assert datalen == expected

    def test_index_two_bytes_little_endian(self):
        """Index is encoded as two bytes, little-endian."""
        packet = build_f3_packet("x", index=258, mode=Mode.WITH_RESPONSE)
        idx_lo = packet[6]
        idx_hi = packet[7]
        assert idx_lo == 2  # 258 & 0xFF
        assert idx_hi == 1  # 258 >> 8

    def test_fire_and_forget_mode(self):
        """Mode=0x00 for fire-and-forget commands."""
        packet = build_f3_packet("cyberpi.led.on(255,0,0)", index=1, mode=Mode.WITHOUT_RESPONSE)
        assert packet[5] == 0x00

    def test_with_response_mode(self):
        """Mode=0x01 for commands expecting a response."""
        packet = build_f3_packet("cyberpi.get_bri()", index=1, mode=Mode.WITH_RESPONSE)
        assert packet[5] == 0x01

    def test_packet_type_is_script(self):
        """All script packets use TYPE_SCRIPT (0x28)."""
        packet = build_f3_packet("x", index=1, mode=Mode.WITH_RESPONSE)
        assert packet[4] == 0x28

    def test_utf8_encoding(self):
        """Script is encoded as UTF-8."""
        packet = build_f3_packet("cyberpi.display.show_label(\"Hello\")", index=1, mode=Mode.WITHOUT_RESPONSE)
        assert b'cyberpi.display.show_label("Hello")' in packet

    def test_empty_script_raises(self):
        """Empty script should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            build_f3_packet("", index=1, mode=Mode.WITH_RESPONSE)


class TestConstants:
    """Test protocol constants."""

    def test_header_footer(self):
        assert HEADER == 0xF3
        assert FOOTER == 0xF4

    def test_online_mode_packet(self):
        assert ONLINE_MODE_PACKET == bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x01, 0x0E, 0xF4])

    def test_offline_mode_packet(self):
        assert OFFLINE_MODE_PACKET == bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x00, 0x0D, 0xF4])
```

- [ ] Run: `pytest tests/test_f3.py -v`
  Expected: FAIL — `ModuleNotFoundError: No module named 'makeblock_explorer.protocol.f3'`

### Step 1.2: Implement `build_f3_packet` and constants

- [ ] Create `src/makeblock_explorer/protocol/f3.py`:

```python
"""F3/F4 protocol engine for MakeBlock CyberPi and HaloCode devices.

Implements the F3 framed protocol used by CyberPi and HaloCode:
    [0xF3][HeaderChecksum][DataLen_Lo][DataLen_Hi][Type][Mode][Idx_Lo][Idx_Hi][Data...][BodyChecksum][0xF4]

Commands are MicroPython script strings wrapped in F3 frames.
Responses contain JSON payloads: {"ret": value} or {"err": "message"}.

This is a pure-logic layer with no I/O or hardware dependencies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


HEADER = 0xF3
FOOTER = 0xF4
MIN_FRAME_SIZE = 10  # header(1) + hdr_cksum(1) + datalen(2) + type(1) + mode(1) + idx(2) + body_cksum(1) + footer(1)

ONLINE_MODE_PACKET = bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x01, 0x0E, 0xF4])
OFFLINE_MODE_PACKET = bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x00, 0x0D, 0xF4])


class PacketType(IntEnum):
    """F3 packet types."""

    RUN_WITHOUT_RESPONSE = 0x00
    RUN_WITH_RESPONSE = 0x01
    RESET = 0x02
    RUN_IMMEDIATE = 0x03
    ONLINE = 0x0D
    SCRIPT = 0x28
    SUBSCRIBE = 0x29


class Mode(IntEnum):
    """F3 command modes."""

    WITHOUT_RESPONSE = 0x00
    WITH_RESPONSE = 0x01
    IMMEDIATE = 0x03


@dataclass
class F3Packet:
    """A parsed F3 protocol packet.

    Attributes:
        type: Packet type (0x28 for script execution).
        mode: Command mode (0x00=fire-and-forget, 0x01=with response).
        index: Command index for request/response correlation (0-65535).
        data: Raw data payload bytes.
        script: Decoded MicroPython script string (if TYPE_SCRIPT).
        raw: Original complete packet bytes.
    """

    type: int
    mode: int
    index: int
    data: bytes
    script: str | None
    raw: bytes


@dataclass
class F3Response:
    """A parsed F3 response.

    Attributes:
        index: Correlates to the request index.
        value: Parsed value from {"ret": ...}, or None.
        error: Error message from {"err": ...}, or None.
        raw: Original complete response bytes.
    """

    index: int
    value: Any
    error: str | None
    raw: bytes


def build_f3_packet(script: str, index: int, mode: int = Mode.WITH_RESPONSE) -> bytes:
    """Encode a MicroPython script into an F3 wire packet.

    Args:
        script: MicroPython code to execute on the device (e.g., "cyberpi.get_bri()").
        index: Command index for response correlation (0-65535).
        mode: Command mode — Mode.WITH_RESPONSE (0x01) or Mode.WITHOUT_RESPONSE (0x00).

    Returns:
        Complete F3 packet as bytes, ready to send over serial.

    Raises:
        ValueError: If script is empty or index is out of range.
    """
    if not script:
        raise ValueError("Script cannot be empty")
    if not 0 <= index <= 0xFFFF:
        raise ValueError(f"Index must be 0-65535, got {index}")

    script_bytes = script.encode("utf-8")
    script_len = len(script_bytes)

    # Data = [script_len_lo, script_len_hi] + script_bytes
    data = [script_len & 0xFF, (script_len >> 8) & 0xFF] + list(script_bytes)

    type_byte = PacketType.SCRIPT
    mode_byte = mode
    idx_lo = index & 0xFF
    idx_hi = (index >> 8) & 0xFF

    # datalen includes: type(1) + mode(1) + idx(2) + data(N)
    datalen = len(data) + 4
    header_checksum = (HEADER + (datalen & 0xFF) + ((datalen >> 8) & 0xFF)) & 0xFF
    body_checksum = (type_byte + mode_byte + idx_lo + idx_hi + sum(data)) & 0xFF

    packet = bytearray()
    packet.append(HEADER)
    packet.append(header_checksum)
    packet.append(datalen & 0xFF)
    packet.append((datalen >> 8) & 0xFF)
    packet.append(type_byte)
    packet.append(mode_byte)
    packet.append(idx_lo)
    packet.append(idx_hi)
    packet.extend(data)
    packet.append(body_checksum)
    packet.append(FOOTER)

    return bytes(packet)


def parse_f3_response(data: bytes) -> list[F3Response]:
    """Parse F3 response frames from a byte stream.

    Scans for F3 frames containing JSON response payloads.
    Tolerates non-F3 data (boot messages, error text) in the stream.

    Args:
        data: Raw bytes received from the device.

    Returns:
        List of parsed F3Response objects for all complete frames found.
    """
    responses: list[F3Response] = []

    for frame, _ in find_f3_frames(data):
        if frame.type != PacketType.SCRIPT:
            continue

        # Extract the script/response text from frame data
        if len(frame.data) < 2:
            continue

        text_len = frame.data[0] + (frame.data[1] << 8)
        text_bytes = frame.data[2 : 2 + text_len]

        try:
            text = text_bytes.decode("utf-8")
        except UnicodeDecodeError:
            continue

        # Parse JSON response
        value = None
        error = None

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                if "ret" in parsed:
                    value = parsed["ret"]
                if "err" in parsed:
                    error = parsed["err"]
        except json.JSONDecodeError:
            # Response might be raw text (error messages)
            error = text

        responses.append(F3Response(
            index=frame.index,
            value=value,
            error=error,
            raw=frame.raw,
        ))

    return responses


def find_f3_frames(buffer: bytes) -> list[tuple[F3Packet, int]]:
    """Find all F3 frames in raw bytes.

    Scans the buffer for F3 headers (0xF3), validates header checksum,
    reads the declared data length, validates body checksum and footer.

    Args:
        buffer: Raw byte buffer to scan.

    Returns:
        List of (F3Packet, end_offset) tuples. end_offset is the index
        of the first byte after the frame in the buffer.
    """
    results: list[tuple[F3Packet, int]] = []
    pos = 0

    while pos <= len(buffer) - MIN_FRAME_SIZE:
        if buffer[pos] != HEADER:
            pos += 1
            continue

        # Read header checksum and datalen
        if pos + 4 > len(buffer):
            break

        hdr_checksum = buffer[pos + 1]
        datalen_lo = buffer[pos + 2]
        datalen_hi = buffer[pos + 3]
        datalen = datalen_lo + (datalen_hi << 8)

        # Validate header checksum
        expected_hdr_cksum = (HEADER + datalen_lo + datalen_hi) & 0xFF
        if hdr_checksum != expected_hdr_cksum:
            pos += 1
            continue

        # Calculate total frame size: header(1) + hdr_cksum(1) + datalen_field(2) + payload(datalen) + body_cksum(1) + footer(1)
        frame_size = 4 + datalen + 2
        frame_end = pos + frame_size

        if frame_end > len(buffer):
            break  # Partial frame

        # Validate footer
        if buffer[frame_end - 1] != FOOTER:
            pos += 1
            continue

        # Parse payload fields
        payload_start = pos + 4
        type_byte = buffer[payload_start]
        mode_byte = buffer[payload_start + 1]
        idx_lo = buffer[payload_start + 2]
        idx_hi = buffer[payload_start + 3]
        data = bytes(buffer[payload_start + 4 : frame_end - 2])

        # Validate body checksum
        body_cksum = buffer[frame_end - 2]
        expected_body = (type_byte + mode_byte + idx_lo + idx_hi + sum(data)) & 0xFF
        if body_cksum != expected_body:
            pos += 1
            continue

        # Decode script if TYPE_SCRIPT
        script = None
        if type_byte == PacketType.SCRIPT and len(data) >= 2:
            script_len = data[0] + (data[1] << 8)
            if len(data) >= 2 + script_len:
                try:
                    script = data[2 : 2 + script_len].decode("utf-8")
                except UnicodeDecodeError:
                    pass

        packet = F3Packet(
            type=type_byte,
            mode=mode_byte,
            index=idx_lo + (idx_hi << 8),
            data=data,
            script=script,
            raw=bytes(buffer[pos:frame_end]),
        )
        results.append((packet, frame_end))
        pos = frame_end

    return results
```

- [ ] Run: `pytest tests/test_f3.py::TestBuildF3Packet -v`
  Expected: All 10 tests PASS

- [ ] Run: `pytest tests/test_f3.py::TestConstants -v`
  Expected: All 3 tests PASS

### Step 1.3: Write failing tests for `parse_f3_response` and `find_f3_frames`

- [ ] Add to `tests/test_f3.py`:

```python
class TestFindF3Frames:
    """Test F3 frame finding in byte streams."""

    def test_find_single_frame(self):
        """Find a single valid F3 frame."""
        packet = build_f3_packet("x", index=1, mode=Mode.WITH_RESPONSE)
        frames = find_f3_frames(packet)
        assert len(frames) == 1
        assert frames[0][0].index == 1
        assert frames[0][0].script == "x"

    def test_find_frame_with_garbage_prefix(self):
        """Skip garbage bytes before a valid frame."""
        garbage = b"\x00\x01\x02WARNING: wifi\r\n"
        packet = build_f3_packet("test", index=5, mode=Mode.WITH_RESPONSE)
        frames = find_f3_frames(garbage + packet)
        assert len(frames) == 1
        assert frames[0][0].index == 5
        assert frames[0][0].script == "test"

    def test_find_multiple_frames(self):
        """Find multiple consecutive F3 frames."""
        p1 = build_f3_packet("a", index=1, mode=Mode.WITH_RESPONSE)
        p2 = build_f3_packet("b", index=2, mode=Mode.WITHOUT_RESPONSE)
        frames = find_f3_frames(p1 + p2)
        assert len(frames) == 2
        assert frames[0][0].script == "a"
        assert frames[1][0].script == "b"

    def test_partial_frame_at_end(self):
        """Partial frame at end of buffer is skipped."""
        packet = build_f3_packet("full", index=1, mode=Mode.WITH_RESPONSE)
        partial = build_f3_packet("cut", index=2, mode=Mode.WITH_RESPONSE)[:5]
        frames = find_f3_frames(packet + partial)
        assert len(frames) == 1

    def test_bad_header_checksum_skipped(self):
        """Frame with wrong header checksum is skipped."""
        packet = bytearray(build_f3_packet("x", index=1, mode=Mode.WITH_RESPONSE))
        packet[1] = 0x00  # corrupt header checksum
        frames = find_f3_frames(bytes(packet))
        assert len(frames) == 0

    def test_bad_body_checksum_skipped(self):
        """Frame with wrong body checksum is skipped."""
        packet = bytearray(build_f3_packet("x", index=1, mode=Mode.WITH_RESPONSE))
        packet[-2] = 0x00  # corrupt body checksum
        frames = find_f3_frames(bytes(packet))
        assert len(frames) == 0

    def test_empty_buffer(self):
        """Empty buffer returns no frames."""
        assert find_f3_frames(b"") == []

    def test_online_mode_packet_found(self):
        """Online mode packet is found as a frame."""
        frames = find_f3_frames(ONLINE_MODE_PACKET)
        assert len(frames) == 1
        assert frames[0][0].type == PacketType.ONLINE


class TestParseF3Response:
    """Test F3 response parsing."""

    def _build_response_frame(self, json_str: str, index: int = 1) -> bytes:
        """Helper: build an F3 response frame wrapping a JSON string."""
        # Response frames have the same structure as script frames
        # but the data payload is the JSON response text
        return build_f3_packet(json_str, index=index, mode=Mode.WITH_RESPONSE)

    def test_parse_integer_response(self):
        """Parse {"ret": 42} response."""
        frame = self._build_response_frame('{"ret": 42}', index=3)
        responses = parse_f3_response(frame)
        assert len(responses) == 1
        assert responses[0].index == 3
        assert responses[0].value == 42
        assert responses[0].error is None

    def test_parse_float_response(self):
        """Parse {"ret": 0.2} response."""
        frame = self._build_response_frame('{"ret": 0.2}')
        responses = parse_f3_response(frame)
        assert len(responses) == 1
        assert responses[0].value == pytest.approx(0.2)

    def test_parse_string_response(self):
        """Parse {"ret": "44.01.011"} response."""
        frame = self._build_response_frame('{"ret": "44.01.011"}')
        responses = parse_f3_response(frame)
        assert len(responses) == 1
        assert responses[0].value == "44.01.011"

    def test_parse_null_response(self):
        """Parse {"ret": null} response (e.g., show_label returns None)."""
        frame = self._build_response_frame('{"ret": null}')
        responses = parse_f3_response(frame)
        assert len(responses) == 1
        assert responses[0].value is None
        assert responses[0].error is None

    def test_parse_error_response(self):
        """Parse {"err": "TypeError"} response."""
        frame = self._build_response_frame('{"err": "TypeError"}')
        responses = parse_f3_response(frame)
        assert len(responses) == 1
        assert responses[0].error == "TypeError"

    def test_parse_multiple_responses(self):
        """Parse multiple responses in one stream."""
        f1 = self._build_response_frame('{"ret": 6}', index=1)
        f2 = self._build_response_frame('{"ret": 10}', index=2)
        responses = parse_f3_response(f1 + f2)
        assert len(responses) == 2
        assert responses[0].value == 6
        assert responses[1].value == 10

    def test_skip_garbage_between_responses(self):
        """Garbage bytes between frames are tolerated."""
        f1 = self._build_response_frame('{"ret": 1}', index=1)
        garbage = b"WARNING: wifi\r\n"
        f2 = self._build_response_frame('{"ret": 2}', index=2)
        responses = parse_f3_response(f1 + garbage + f2)
        assert len(responses) == 2

    def test_empty_data_returns_empty(self):
        """Empty byte stream returns no responses."""
        assert parse_f3_response(b"") == []
```

- [ ] Run: `pytest tests/test_f3.py -v`
  Expected: All tests PASS (implementation already in place from Step 1.2)

### Step 1.4: Update protocol `__init__.py` and verify all existing tests still pass

- [ ] Modify `src/makeblock_explorer/protocol/__init__.py` — add F3 exports:

```python
"""Protocol engines for MakeBlock devices.

FF55: Binary protocol for MegaPi, mBot, mCore, MeAuriga.
F3: Framed script protocol for CyberPi, HaloCode.
"""

from .capture import CaptureEntry, CaptureTransport, format_hex_dump, load_capture
from .f3 import (
    F3Packet,
    F3Response,
    FOOTER as F3_FOOTER,
    HEADER as F3_HEADER,
    MIN_FRAME_SIZE as F3_MIN_FRAME_SIZE,
    Mode,
    OFFLINE_MODE_PACKET,
    ONLINE_MODE_PACKET,
    PacketType,
    build_f3_packet,
    find_f3_frames,
    parse_f3_response,
)
from .ff55 import HEADER, Action, Packet, build_packet, find_packets, parse_packet
from .types import DataType, decode_value, encode_value

__all__ = [
    # FF55 protocol
    "Action",
    "HEADER",
    "Packet",
    "build_packet",
    "decode_value",
    "encode_value",
    "find_packets",
    "parse_packet",
    # F3 protocol
    "F3Packet",
    "F3Response",
    "F3_FOOTER",
    "F3_HEADER",
    "F3_MIN_FRAME_SIZE",
    "Mode",
    "OFFLINE_MODE_PACKET",
    "ONLINE_MODE_PACKET",
    "PacketType",
    "build_f3_packet",
    "find_f3_frames",
    "parse_f3_response",
    # Capture
    "CaptureEntry",
    "CaptureTransport",
    "format_hex_dump",
    "load_capture",
    # Types
    "DataType",
]
```

- [ ] Run: `pytest tests/ -v`
  Expected: All existing 115 tests + new F3 tests PASS

- [ ] Commit:
```bash
git add src/makeblock_explorer/protocol/f3.py tests/test_f3.py src/makeblock_explorer/protocol/__init__.py
git commit -m "feat: add F3/F4 protocol engine for CyberPi and HaloCode"
```

---

## Task 2: DeviceManager (Serial Bridge)

**Files:**
- Create: `src/makeblock_explorer/device/__init__.py`
- Create: `src/makeblock_explorer/device/manager.py`
- Create: `src/makeblock_explorer/device/registry.py`
- Create: `tests/test_manager.py`
- Modify: `pyproject.toml`

### Step 2.1: Update `pyproject.toml` with new dependencies

- [ ] Modify `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "makeblock-explorer"
version = "0.2.0"
description = "MakeBlock Device Explorer — F3/FF55 Protocol Dashboard"
requires-python = ">=3.11"
dependencies = [
    "pyserial>=3.5",
    "click>=8.1",
    "rich>=13.0",
    "pyyaml>=6.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "websockets>=12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[project.scripts]
mbx = "makeblock_explorer.cli:main"
mbx-server = "makeblock_explorer.api.server:run"

[tool.hatch.build.targets.wheel]
packages = ["src/makeblock_explorer"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
```

- [ ] Run: `pip install -e ".[dev]"`
  Expected: All new dependencies installed successfully

- [ ] Commit:
```bash
git add pyproject.toml
git commit -m "chore: add FastAPI, uvicorn, websockets, pytest-asyncio dependencies"
```

### Step 2.2: Write failing tests for DeviceManager

- [ ] Create `tests/test_manager.py`:

```python
"""Tests for DeviceManager serial bridge."""

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from makeblock_explorer.device.manager import DeviceManager
from makeblock_explorer.protocol.f3 import (
    ONLINE_MODE_PACKET,
    build_f3_packet,
    Mode,
)


@pytest.fixture
def mock_serial():
    """Create a mock serial port that simulates F3 handshake."""
    mock = MagicMock()
    mock.is_open = True
    mock.in_waiting = 0

    # Build a fake response for cyberpi.get_bri() -> {"ret": 42}
    response_packet = build_f3_packet('{"ret": 42}', index=1, mode=Mode.WITH_RESPONSE)

    read_queue = list(response_packet)

    def mock_read(size=1):
        if read_queue:
            result = bytes([read_queue.pop(0)])
            return result
        return b""

    def mock_read_all():
        if read_queue:
            result = bytes(read_queue)
            read_queue.clear()
            return result
        return b""

    mock.read = mock_read
    mock.read_all = mock_read_all
    mock.write = MagicMock()
    mock.flush = MagicMock()
    mock.close = MagicMock()
    mock.reset_input_buffer = MagicMock()
    mock.reset_output_buffer = MagicMock()

    return mock


class TestDeviceManagerInit:
    """Test DeviceManager initialization."""

    def test_initial_state(self):
        manager = DeviceManager()
        assert manager.is_connected is False
        assert manager.device_id is None
        assert manager.port is None
        assert manager.sensor_cache == {}

    def test_device_id_format(self):
        """Device ID is derived from port."""
        manager = DeviceManager()
        assert manager._make_device_id("COM5") == "device-COM5"


class TestDeviceManagerConnect:
    """Test connection lifecycle."""

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_connect_opens_serial(self, mock_serial_class, mock_serial):
        mock_serial_class.return_value = mock_serial
        manager = DeviceManager()
        await manager.connect("COM5")
        mock_serial_class.assert_called_once_with(
            port="COM5",
            baudrate=115200,
            bytesize=8,
            stopbits=1,
            parity="N",
            timeout=1.0,
        )
        assert manager.is_connected is True
        assert manager.port == "COM5"

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_disconnect_closes_serial(self, mock_serial_class, mock_serial):
        mock_serial_class.return_value = mock_serial
        manager = DeviceManager()
        await manager.connect("COM5")
        await manager.disconnect()
        mock_serial.close.assert_called_once()
        assert manager.is_connected is False


class TestDeviceManagerExecute:
    """Test script execution."""

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_execute_sends_f3_packet(self, mock_serial_class, mock_serial):
        mock_serial_class.return_value = mock_serial
        # Setup mock to return a valid F3 response
        response = build_f3_packet('{"ret": 42}', index=1, mode=Mode.WITH_RESPONSE)
        mock_serial.in_waiting = len(response)
        mock_serial.read = MagicMock(return_value=response)

        manager = DeviceManager()
        await manager.connect("COM5")
        result = await manager.execute("cyberpi.get_bri()")

        # Verify a packet was written to serial
        assert mock_serial.write.called
        written_bytes = mock_serial.write.call_args[0][0]
        assert written_bytes[0] == 0xF3  # F3 header
        assert written_bytes[-1] == 0xF4  # F4 footer

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_execute_not_connected_raises(self, mock_serial_class):
        manager = DeviceManager()
        with pytest.raises(ConnectionError, match="Not connected"):
            await manager.execute("cyberpi.get_bri()")
```

- [ ] Run: `pytest tests/test_manager.py -v`
  Expected: FAIL — `ModuleNotFoundError: No module named 'makeblock_explorer.device'`

### Step 2.3: Implement DeviceManager

- [ ] Create `src/makeblock_explorer/device/__init__.py`:

```python
"""Device management for MakeBlock hardware."""

from .manager import DeviceManager
from .registry import DeviceRegistry

__all__ = ["DeviceManager", "DeviceRegistry"]
```

- [ ] Create `src/makeblock_explorer/device/manager.py`:

```python
"""DeviceManager — serial bridge for a single MakeBlock device.

Manages the serial connection lifecycle, F3 handshake, command execution,
and sensor polling for one device. Uses asyncio.to_thread for blocking
serial operations to avoid blocking the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import serial

from makeblock_explorer.protocol.f3 import (
    F3Response,
    Mode,
    ONLINE_MODE_PACKET,
    build_f3_packet,
    parse_f3_response,
)

logger = logging.getLogger(__name__)

BAUD_RATE = 115200
HANDSHAKE_PROBE = "cyberpi.get_bri()"
BOOT_WAIT_SECONDS = 4.0
HANDSHAKE_TIMEOUT = 2.0

# Default sensors to poll (CyberPi)
DEFAULT_SENSOR_COMMANDS = {
    "brightness": "cyberpi.get_bri()",
    "battery": "cyberpi.get_battery()",
    "pitch": "cyberpi.get_pitch()",
    "roll": "cyberpi.get_roll()",
    "accel_x": 'cyberpi.get_acc("x")',
    "accel_y": 'cyberpi.get_acc("y")',
    "accel_z": 'cyberpi.get_acc("z")',
}


class DeviceManager:
    """Manages a serial connection to a single MakeBlock device.

    All serial I/O runs via asyncio.to_thread to avoid blocking.
    """

    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self._index_counter: int = 0
        self._subscribers: dict[str, Callable[[dict], None]] = {}
        self._polling_task: asyncio.Task | None = None
        self.port: str | None = None
        self.device_id: str | None = None
        self.device_type: str = "unknown"
        self.sensor_cache: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def _make_device_id(self, port: str) -> str:
        return f"device-{port}"

    def _next_index(self) -> int:
        self._index_counter = (self._index_counter + 1) % 0xFFFF
        return self._index_counter

    async def connect(self, port: str) -> None:
        """Open serial, reset device, run F3 handshake.

        Args:
            port: COM port (e.g., "COM5").

        Raises:
            serial.SerialException: If the port cannot be opened.
            TimeoutError: If the handshake fails.
        """
        if self.is_connected:
            await self.disconnect()

        self._serial = await asyncio.to_thread(
            serial.Serial,
            port=port,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            stopbits=serial.STOPBITS_ONE,
            parity=serial.PARITY_NONE,
            timeout=1.0,
        )

        self.port = port
        self.device_id = self._make_device_id(port)

        # Reset device via DTR/RTS toggle
        await asyncio.to_thread(self._reset_device)

        # Run F3 handshake
        await asyncio.to_thread(self._handshake)

        logger.info("Connected to %s on %s", self.device_id, port)

    def _reset_device(self) -> None:
        """Toggle DTR/RTS to reset the ESP32."""
        assert self._serial is not None
        self._serial.dtr = False
        self._serial.rts = True
        time.sleep(0.1)
        self._serial.dtr = True
        self._serial.rts = False
        time.sleep(0.1)
        self._serial.dtr = False
        time.sleep(BOOT_WAIT_SECONDS)
        # Drain boot output
        while self._serial.in_waiting:
            self._serial.read(self._serial.in_waiting)
            time.sleep(0.1)

    def _handshake(self) -> None:
        """Perform F3 handshake: probe + online mode."""
        assert self._serial is not None

        # Send probe
        probe = build_f3_packet(HANDSHAKE_PROBE, index=self._next_index(), mode=Mode.WITH_RESPONSE)
        self._serial.write(probe)
        self._serial.flush()
        time.sleep(1.5)
        # Drain probe response (may contain boot text)
        while self._serial.in_waiting:
            self._serial.read(self._serial.in_waiting)
            time.sleep(0.1)

        # Send online mode
        self._serial.write(ONLINE_MODE_PACKET)
        self._serial.flush()
        time.sleep(0.5)
        while self._serial.in_waiting:
            self._serial.read(self._serial.in_waiting)
            time.sleep(0.1)

        # Sync read to confirm pipeline
        sync = build_f3_packet(HANDSHAKE_PROBE, index=self._next_index(), mode=Mode.WITH_RESPONSE)
        self._serial.write(sync)
        self._serial.flush()
        time.sleep(0.8)
        while self._serial.in_waiting:
            self._serial.read(self._serial.in_waiting)
            time.sleep(0.1)

    async def disconnect(self) -> None:
        """Stop polling and close the serial port."""
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None

        if self._serial and self._serial.is_open:
            await asyncio.to_thread(self._serial.close)

        self._serial = None
        self.port = None
        self.device_id = None
        self._subscribers.clear()
        self.sensor_cache.clear()
        logger.info("Disconnected")

    async def execute(self, script: str, expect_response: bool = True) -> F3Response | None:
        """Send a MicroPython script to the device.

        Args:
            script: MicroPython code (e.g., "cyberpi.get_bri()").
            expect_response: If True, wait for and parse the F3 response.

        Returns:
            F3Response if expect_response is True and a response was received, else None.

        Raises:
            ConnectionError: If not connected.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected. Call connect() first.")

        mode = Mode.WITH_RESPONSE if expect_response else Mode.WITHOUT_RESPONSE
        index = self._next_index()
        packet = build_f3_packet(script, index=index, mode=mode)

        response = await asyncio.to_thread(self._send_and_receive, packet, expect_response)
        return response

    def _send_and_receive(self, packet: bytes, expect_response: bool) -> F3Response | None:
        """Blocking serial send + optional receive."""
        assert self._serial is not None

        self._serial.write(packet)
        self._serial.flush()

        if not expect_response:
            time.sleep(0.05)  # Brief pause for fire-and-forget
            return None

        time.sleep(0.3)

        # Read response
        data = b""
        deadline = time.time() + HANDSHAKE_TIMEOUT
        while time.time() < deadline:
            if self._serial.in_waiting:
                data += self._serial.read(self._serial.in_waiting)
                time.sleep(0.05)
            else:
                time.sleep(0.05)
            # Check if we got a complete F3 response
            if data and 0xF4 in data:
                time.sleep(0.05)  # Brief extra for trailing bytes
                while self._serial.in_waiting:
                    data += self._serial.read(self._serial.in_waiting)
                break

        if not data:
            return None

        responses = parse_f3_response(data)
        return responses[0] if responses else None

    async def start_sensor_polling(self, hz: float = 5.0) -> None:
        """Begin continuous sensor reads, broadcasting to subscribers.

        Args:
            hz: Polling frequency in Hz (default 5.0).
        """
        if self._polling_task and not self._polling_task.done():
            return  # Already polling

        self._polling_task = asyncio.create_task(self._poll_loop(hz))

    async def _poll_loop(self, hz: float) -> None:
        """Continuous sensor polling loop."""
        interval = 1.0 / hz

        while self.is_connected:
            start = time.monotonic()

            for name, cmd in DEFAULT_SENSOR_COMMANDS.items():
                if not self.is_connected:
                    return
                try:
                    response = await self.execute(cmd, expect_response=True)
                    if response and response.value is not None:
                        self.sensor_cache[name] = response.value
                except Exception as e:
                    logger.warning("Sensor poll failed for %s: %s", name, e)

            # Broadcast to subscribers
            for callback in list(self._subscribers.values()):
                try:
                    callback(dict(self.sensor_cache))
                except Exception as e:
                    logger.warning("Subscriber callback failed: %s", e)

            elapsed = time.monotonic() - start
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

    def subscribe(self, callback: Callable[[dict], None]) -> str:
        """Subscribe to sensor updates. Returns subscription ID."""
        sub_id = str(uuid.uuid4())
        self._subscribers[sub_id] = callback
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        """Remove a sensor subscription."""
        self._subscribers.pop(sub_id, None)
```

- [ ] Create `src/makeblock_explorer/device/registry.py`:

```python
"""DeviceRegistry — manages multiple connected DeviceManagers."""

from __future__ import annotations

import logging

from makeblock_explorer.device.manager import DeviceManager
from makeblock_explorer.transport.base import DeviceInfo, scan_serial_ports

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """Manages multiple connected DeviceManagers.

    Tracks all connected devices, handles scan/connect/disconnect,
    and routes commands to the correct DeviceManager by device_id.
    """

    def __init__(self) -> None:
        self._devices: dict[str, DeviceManager] = {}

    async def scan(self) -> list[DeviceInfo]:
        """Scan COM ports for CH340 devices."""
        return scan_serial_ports()

    async def connect(self, port: str) -> DeviceManager:
        """Create and connect a DeviceManager for the given port.

        Args:
            port: COM port (e.g., "COM5").

        Returns:
            Connected DeviceManager instance.

        Raises:
            ValueError: If the port is already connected.
        """
        # Check if already connected on this port
        for manager in self._devices.values():
            if manager.port == port:
                raise ValueError(f"Already connected to {port}")

        manager = DeviceManager()
        await manager.connect(port)

        if manager.device_id:
            self._devices[manager.device_id] = manager

        return manager

    async def disconnect(self, device_id: str) -> None:
        """Disconnect and remove a DeviceManager."""
        manager = self._devices.pop(device_id, None)
        if manager:
            await manager.disconnect()
        else:
            raise ValueError(f"No device with id {device_id}")

    async def disconnect_all(self) -> None:
        """Disconnect all devices. Called during server shutdown."""
        for manager in list(self._devices.values()):
            try:
                await manager.disconnect()
            except Exception as e:
                logger.warning("Error disconnecting %s: %s", manager.device_id, e)
        self._devices.clear()

    def get(self, device_id: str) -> DeviceManager | None:
        """Get a connected DeviceManager by ID."""
        return self._devices.get(device_id)

    def list_connected(self) -> list[DeviceManager]:
        """List all connected devices."""
        return list(self._devices.values())
```

- [ ] Run: `pytest tests/test_manager.py -v`
  Expected: All tests PASS

- [ ] Run: `pytest tests/ -v`
  Expected: All existing + new tests PASS

- [ ] Commit:
```bash
git add src/makeblock_explorer/device/ tests/test_manager.py pyproject.toml
git commit -m "feat: add DeviceManager serial bridge and DeviceRegistry"
```

---

## Task 3: FastAPI Backend

**Files:**
- Create: `src/makeblock_explorer/api/__init__.py`
- Create: `src/makeblock_explorer/api/server.py`
- Create: `src/makeblock_explorer/api/models.py`
- Create: `src/makeblock_explorer/api/routes/__init__.py`
- Create: `src/makeblock_explorer/api/routes/devices.py`
- Create: `src/makeblock_explorer/api/routes/commands.py`
- Create: `src/makeblock_explorer/api/routes/stream.py`
- Create: `tests/test_api.py`

### Step 3.1: Write failing API tests

- [ ] Create `tests/test_api.py`:

```python
"""Tests for FastAPI endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from makeblock_explorer.api.server import create_app
from makeblock_explorer.device.manager import DeviceManager
from makeblock_explorer.device.registry import DeviceRegistry
from makeblock_explorer.transport.base import DeviceInfo


@pytest.fixture
def mock_registry():
    registry = MagicMock(spec=DeviceRegistry)
    registry.scan = AsyncMock(return_value=[
        DeviceInfo(port="COM5", description="USB-SERIAL CH340", vid=0x1A86, pid=0x7523, serial_number=None),
    ])
    registry.list_connected = MagicMock(return_value=[])
    registry.disconnect_all = AsyncMock()
    return registry


@pytest.fixture
def mock_manager():
    manager = MagicMock(spec=DeviceManager)
    manager.device_id = "device-COM5"
    manager.port = "COM5"
    manager.device_type = "cyberpi"
    manager.is_connected = True
    manager.sensor_cache = {"brightness": 42, "battery": 80}
    manager.execute = AsyncMock()
    manager.start_sensor_polling = AsyncMock()
    return manager


@pytest.fixture
def app(mock_registry):
    return create_app(registry=mock_registry)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestDeviceRoutes:
    """Test device management endpoints."""

    async def test_scan_devices(self, client, mock_registry):
        resp = await client.get("/api/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 1
        assert data["devices"][0]["port"] == "COM5"

    async def test_connect_device(self, client, mock_registry, mock_manager):
        mock_registry.connect = AsyncMock(return_value=mock_manager)
        resp = await client.post("/api/connect", json={"port": "COM5"})
        assert resp.status_code == 200
        assert resp.json()["device_id"] == "device-COM5"

    async def test_disconnect_device(self, client, mock_registry):
        mock_registry.disconnect = AsyncMock()
        resp = await client.post("/api/disconnect", json={"device_id": "device-COM5"})
        assert resp.status_code == 200

    async def test_status(self, client, mock_registry, mock_manager):
        mock_registry.list_connected = MagicMock(return_value=[mock_manager])
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 1
        assert data["devices"][0]["device_id"] == "device-COM5"


class TestCommandRoutes:
    """Test command execution endpoints."""

    async def test_execute_command(self, client, mock_registry, mock_manager):
        mock_registry.get = MagicMock(return_value=mock_manager)
        mock_manager.execute = AsyncMock(return_value=MagicMock(value=42, error=None))
        resp = await client.post("/api/command", json={
            "device_id": "device-COM5",
            "script": "cyberpi.get_bri()",
        })
        assert resp.status_code == 200
        assert resp.json()["value"] == 42

    async def test_led_command(self, client, mock_registry, mock_manager):
        mock_registry.get = MagicMock(return_value=mock_manager)
        mock_manager.execute = AsyncMock(return_value=None)
        resp = await client.post("/api/led", json={
            "device_id": "device-COM5",
            "red": 255,
            "green": 0,
            "blue": 0,
        })
        assert resp.status_code == 200

    async def test_notify_command(self, client, mock_registry, mock_manager):
        mock_registry.get = MagicMock(return_value=mock_manager)
        mock_manager.execute = AsyncMock(return_value=None)
        resp = await client.post("/api/notify", json={
            "device_id": "device-COM5",
            "text": "Hi Chat!",
            "color": [0, 255, 0],
            "size": 24,
            "flash_leds": True,
        })
        assert resp.status_code == 200

    async def test_sensors_cached(self, client, mock_registry, mock_manager):
        mock_registry.get = MagicMock(return_value=mock_manager)
        resp = await client.get("/api/sensors/device-COM5")
        assert resp.status_code == 200
        assert resp.json()["brightness"] == 42

    async def test_command_device_not_found(self, client, mock_registry):
        mock_registry.get = MagicMock(return_value=None)
        resp = await client.post("/api/command", json={
            "device_id": "nonexistent",
            "script": "x",
        })
        assert resp.status_code == 404
```

- [ ] Run: `pytest tests/test_api.py -v`
  Expected: FAIL — `ModuleNotFoundError: No module named 'makeblock_explorer.api'`

### Step 3.2: Implement FastAPI app and models

- [ ] Create `src/makeblock_explorer/api/__init__.py`:

```python
"""FastAPI web API for MakeBlock Explorer."""
```

- [ ] Create `src/makeblock_explorer/api/models.py`:

```python
"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConnectRequest(BaseModel):
    port: str = Field(..., description="COM port to connect to (e.g., 'COM5')")


class DisconnectRequest(BaseModel):
    device_id: str = Field(..., description="Device ID to disconnect")


class CommandRequest(BaseModel):
    device_id: str
    script: str = Field(..., description="MicroPython script to execute")


class LedRequest(BaseModel):
    device_id: str
    red: int = Field(..., ge=0, le=255)
    green: int = Field(..., ge=0, le=255)
    blue: int = Field(..., ge=0, le=255)
    led_id: int | None = Field(None, ge=1, le=5, description="Specific LED (1-5), or None for all")


class NotifyRequest(BaseModel):
    device_id: str
    text: str = Field(..., max_length=30)
    color: list[int] = Field(default=[255, 255, 255], description="RGB color [r, g, b]")
    size: int = Field(default=24, ge=12, le=48)
    flash_leds: bool = Field(default=True)


class DeviceInfoResponse(BaseModel):
    port: str
    description: str
    vid: int | None
    pid: int | None


class DeviceStatusResponse(BaseModel):
    device_id: str
    port: str
    device_type: str
    is_connected: bool
    sensor_cache: dict
```

- [ ] Create `src/makeblock_explorer/api/routes/__init__.py`:

```python
"""API route modules."""
```

### Step 3.3: Implement route modules

- [ ] Create `src/makeblock_explorer/api/routes/devices.py`:

```python
"""Device management routes: scan, connect, disconnect, status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from makeblock_explorer.api.models import (
    ConnectRequest,
    DeviceInfoResponse,
    DeviceStatusResponse,
    DisconnectRequest,
)
from makeblock_explorer.device.registry import DeviceRegistry

router = APIRouter(prefix="/api", tags=["devices"])


def get_registry() -> DeviceRegistry:
    """Get the global DeviceRegistry. Set by server.py at startup."""
    if _registry is None:
        raise RuntimeError("DeviceRegistry not initialized")
    return _registry


_registry: DeviceRegistry | None = None


def init_router(registry: DeviceRegistry) -> None:
    """Initialize the router with a DeviceRegistry."""
    global _registry
    _registry = registry


@router.get("/devices")
async def scan_devices():
    """Scan for available MakeBlock devices."""
    devices = await get_registry().scan()
    return {
        "devices": [
            DeviceInfoResponse(
                port=d.port,
                description=d.description,
                vid=d.vid,
                pid=d.pid,
            )
            for d in devices
        ]
    }


@router.post("/connect")
async def connect_device(req: ConnectRequest):
    """Connect to a device by COM port."""
    try:
        manager = await get_registry().connect(req.port)
        await manager.start_sensor_polling()
        return {"device_id": manager.device_id, "port": manager.port}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect_device(req: DisconnectRequest):
    """Disconnect a device."""
    try:
        await get_registry().disconnect(req.device_id)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/status")
async def device_status():
    """Get status of all connected devices."""
    devices = get_registry().list_connected()
    return {
        "devices": [
            DeviceStatusResponse(
                device_id=d.device_id or "",
                port=d.port or "",
                device_type=d.device_type,
                is_connected=d.is_connected,
                sensor_cache=d.sensor_cache,
            )
            for d in devices
        ]
    }
```

- [ ] Create `src/makeblock_explorer/api/routes/commands.py`:

```python
"""Command execution routes: script, LED, notify, sensors."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from makeblock_explorer.api.models import CommandRequest, LedRequest, NotifyRequest
from makeblock_explorer.api.routes.devices import get_registry

router = APIRouter(prefix="/api", tags=["commands"])


def _get_manager(device_id: str):
    """Get a connected DeviceManager or raise 404."""
    manager = get_registry().get(device_id)
    if not manager:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    return manager


@router.post("/command")
async def execute_command(req: CommandRequest):
    """Execute an arbitrary MicroPython script on the device."""
    manager = _get_manager(req.device_id)
    response = await manager.execute(req.script, expect_response=True)
    if response:
        return {"value": response.value, "error": response.error}
    return {"value": None, "error": "No response"}


@router.get("/sensors/{device_id}")
async def get_sensors(device_id: str):
    """Get latest cached sensor readings."""
    manager = _get_manager(device_id)
    return manager.sensor_cache


@router.post("/led")
async def set_led(req: LedRequest):
    """Set LED color(s) on the device."""
    manager = _get_manager(req.device_id)
    if req.led_id is not None:
        script = f"cyberpi.led.set({req.led_id},{req.red},{req.green},{req.blue})"
    else:
        script = f"cyberpi.led.on({req.red},{req.green},{req.blue})"
    await manager.execute(script, expect_response=False)
    return {"status": "ok"}


@router.post("/notify")
async def push_notification(req: NotifyRequest):
    """Push a text notification to the device display."""
    manager = _get_manager(req.device_id)
    r, g, b = req.color[0], req.color[1], req.color[2]

    # Clear and display text
    await manager.execute("cyberpi.display.clear()", expect_response=False)
    await manager.execute(f"cyberpi.display.set_brush({r},{g},{b})", expect_response=False)

    # Auto-center: rough estimate — 128px wide display
    char_width = req.size * 0.6
    text_width = len(req.text) * char_width
    x = max(0, int((128 - text_width) / 2))
    y = max(0, int((128 - req.size) / 2))

    await manager.execute(
        f'cyberpi.display.show_label("{req.text}",{req.size},{x},{y})',
        expect_response=False,
    )

    # Flash LEDs if requested
    if req.flash_leds:
        for _ in range(3):
            await manager.execute(f"cyberpi.led.on({r},{g},{b})", expect_response=False)
            await asyncio.sleep(0.5)
            await manager.execute("cyberpi.led.on(0,0,0)", expect_response=False)
            await asyncio.sleep(0.3)

    return {"status": "ok", "device_id": req.device_id}
```

- [ ] Create `src/makeblock_explorer/api/routes/stream.py`:

```python
"""WebSocket sensor streaming route."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from makeblock_explorer.api.routes.devices import get_registry

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])


@router.websocket("/api/stream")
async def sensor_stream(websocket: WebSocket):
    """WebSocket endpoint for live sensor data streaming.

    Client sends: {"type": "subscribe", "device_id": "device-COM5"} or "all"
    Server sends: {"type": "sensor", "device_id": "...", "data": {...}} at poll rate
    """
    await websocket.accept()

    subscribed_devices: set[str] = set()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    sub_ids: dict[str, str] = {}  # device_id -> subscription_id

    def on_sensor_update(device_id: str):
        def callback(data: dict):
            queue.put_nowait({"type": "sensor", "device_id": device_id, "data": data})
        return callback

    try:
        # Receive task: listen for subscribe messages
        async def receive_loop():
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                if msg.get("type") == "subscribe":
                    target = msg.get("device_id", "all")
                    if target == "all":
                        for manager in get_registry().list_connected():
                            did = manager.device_id
                            if did and did not in subscribed_devices:
                                sub_id = manager.subscribe(on_sensor_update(did))
                                sub_ids[did] = sub_id
                                subscribed_devices.add(did)
                    else:
                        manager = get_registry().get(target)
                        if manager and target not in subscribed_devices:
                            sub_id = manager.subscribe(on_sensor_update(target))
                            sub_ids[target] = sub_id
                            subscribed_devices.add(target)

        # Send task: forward sensor data from queue
        async def send_loop():
            while True:
                msg = await queue.get()
                await websocket.send_json(msg)

        await asyncio.gather(
            receive_loop(),
            send_loop(),
        )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
    finally:
        # Unsubscribe all
        for device_id, sub_id in sub_ids.items():
            manager = get_registry().get(device_id)
            if manager:
                manager.unsubscribe(sub_id)
```

### Step 3.4: Implement FastAPI app factory and server runner

- [ ] Create `src/makeblock_explorer/api/server.py`:

```python
"""FastAPI application factory and server runner."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from makeblock_explorer.api.routes import commands, devices, stream
from makeblock_explorer.device.registry import DeviceRegistry


def create_app(registry: DeviceRegistry | None = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        registry: Optional DeviceRegistry instance. If None, creates a new one.

    Returns:
        Configured FastAPI app.
    """
    if registry is None:
        registry = DeviceRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        yield
        # Shutdown — disconnect all devices
        await registry.disconnect_all()

    app = FastAPI(
        title="MakeBlock Explorer API",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS for Next.js dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize routes with registry
    devices.init_router(registry)

    # Mount routers
    app.include_router(devices.router)
    app.include_router(commands.router)
    app.include_router(stream.router)

    return app


def run():
    """Run the server via uvicorn. Entry point for `mbx-server`."""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] Run: `pytest tests/test_api.py -v`
  Expected: All API tests PASS

- [ ] Run: `pytest tests/ -v`
  Expected: All tests PASS (existing + F3 + manager + API)

- [ ] Commit:
```bash
git add src/makeblock_explorer/api/ tests/test_api.py
git commit -m "feat: add FastAPI backend with REST + WebSocket API"
```

---

## Task 4: Update `__init__.py` and Verify Full Test Suite

**Files:**
- Modify: `src/makeblock_explorer/__init__.py`

### Step 4.1: Update package init

- [ ] Modify `src/makeblock_explorer/__init__.py`:

```python
"""MakeBlock Device Explorer — F3/FF55 Protocol Dashboard."""

__version__ = "0.2.0"
```

- [ ] Run: `pytest tests/ -v`
  Expected: ALL tests PASS — existing 115 + new F3 + manager + API tests

- [ ] Commit:
```bash
git add src/makeblock_explorer/__init__.py
git commit -m "chore: update package version and description to 0.2.0"
```

---

## Task 5: Next.js Frontend Scaffold

**Files:**
- Create: `web/` (entire Next.js project)

### Step 5.1: Scaffold the Next.js project

- [ ] Run:
```bash
cd C:/Dev/projects/stem/cyberpi
npx create-next-app@latest web --typescript --tailwind --eslint --app --src-dir --no-import-alias --use-npm
```
  Expected: Next.js project created in `web/`

- [ ] Commit:
```bash
git add web/
git commit -m "chore: scaffold Next.js frontend project"
```

### Step 5.2: Install additional frontend dependencies

- [ ] Run:
```bash
cd C:/Dev/projects/stem/cyberpi/web
npm install recharts
```

- [ ] Commit:
```bash
git add web/package.json web/package-lock.json
git commit -m "chore: add recharts dependency for sensor charts"
```

### Step 5.3: Create API client and WebSocket hook

- [ ] Create `web/src/lib/api.ts`:

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface DeviceInfo {
  port: string;
  description: string;
  vid: number | null;
  pid: number | null;
}

export interface DeviceStatus {
  device_id: string;
  port: string;
  device_type: string;
  is_connected: boolean;
  sensor_cache: Record<string, number>;
}

export async function scanDevices(): Promise<DeviceInfo[]> {
  const res = await fetch(`${API_BASE}/api/devices`);
  const data = await res.json();
  return data.devices;
}

export async function connectDevice(port: string): Promise<{ device_id: string }> {
  const res = await fetch(`${API_BASE}/api/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ port }),
  });
  return res.json();
}

export async function disconnectDevice(deviceId: string): Promise<void> {
  await fetch(`${API_BASE}/api/disconnect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId }),
  });
}

export async function getStatus(): Promise<DeviceStatus[]> {
  const res = await fetch(`${API_BASE}/api/status`);
  const data = await res.json();
  return data.devices;
}

export async function getSensors(deviceId: string): Promise<Record<string, number>> {
  const res = await fetch(`${API_BASE}/api/sensors/${deviceId}`);
  return res.json();
}

export async function executeCommand(deviceId: string, script: string) {
  const res = await fetch(`${API_BASE}/api/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId, script }),
  });
  return res.json();
}

export async function setLed(deviceId: string, r: number, g: number, b: number, ledId?: number) {
  await fetch(`${API_BASE}/api/led`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId, red: r, green: g, blue: b, led_id: ledId }),
  });
}

export async function pushNotify(
  deviceId: string,
  text: string,
  color: [number, number, number] = [255, 255, 255],
  size: number = 24,
  flashLeds: boolean = true
) {
  await fetch(`${API_BASE}/api/notify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId, text, color, size, flash_leds: flashLeds }),
  });
}
```

- [ ] Create `web/src/hooks/useWebSocket.ts`:

```typescript
"use client";

import { useEffect, useRef, useState, useCallback } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/api/stream";

interface SensorMessage {
  type: "sensor";
  device_id: string;
  data: Record<string, number>;
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [sensorData, setSensorData] = useState<Record<string, Record<string, number>>>({});

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setIsConnected(true);
      // Subscribe to all devices
      ws.send(JSON.stringify({ type: "subscribe", device_id: "all" }));
    };

    ws.onmessage = (event) => {
      const msg: SensorMessage = JSON.parse(event.data);
      if (msg.type === "sensor") {
        setSensorData((prev) => ({
          ...prev,
          [msg.device_id]: msg.data,
        }));
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      // Reconnect after 2 seconds
      setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  return { isConnected, sensorData };
}
```

- [ ] Commit:
```bash
git add web/src/lib/api.ts web/src/hooks/useWebSocket.ts
git commit -m "feat: add API client and WebSocket hook for frontend"
```

### Step 5.4: Create dashboard page with device cards

- [ ] Create `web/src/components/DeviceCard.tsx`:

```tsx
"use client";

interface DeviceCardProps {
  deviceId: string;
  port: string;
  sensors: Record<string, number>;
  onDisconnect: () => void;
}

export function DeviceCard({ deviceId, port, sensors, onDisconnect }: DeviceCardProps) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
          <h3 className="text-lg font-semibold text-white">CyberPi ({port})</h3>
        </div>
        <button
          onClick={onDisconnect}
          className="text-sm text-red-400 hover:text-red-300 transition"
        >
          Disconnect
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <SensorBar label="Brightness" value={sensors.brightness} max={100} unit="" color="yellow" />
        <SensorBar label="Battery" value={sensors.battery} max={100} unit="%" color="green" />
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <SensorValue label="Pitch" value={sensors.pitch} unit="°" />
        <SensorValue label="Roll" value={sensors.roll} unit="°" />
        <SensorValue label="Accel X" value={sensors.accel_x} unit="g" />
      </div>
    </div>
  );
}

function SensorBar({ label, value, max, unit, color }: {
  label: string; value: number | undefined; max: number; unit: string; color: string;
}) {
  const pct = value !== undefined ? Math.min(100, (value / max) * 100) : 0;
  const colorClass = color === "green" ? "bg-green-500" : "bg-yellow-500";
  return (
    <div>
      <div className="flex justify-between text-sm text-gray-400 mb-1">
        <span>{label}</span>
        <span>{value !== undefined ? `${value}${unit}` : "—"}</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full ${colorClass} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function SensorValue({ label, value, unit }: { label: string; value: number | undefined; unit: string }) {
  return (
    <div className="bg-gray-800 rounded-lg p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-lg font-mono text-white">
        {value !== undefined ? `${typeof value === "number" ? value.toFixed(1) : value}${unit}` : "—"}
      </div>
    </div>
  );
}
```

- [ ] Replace `web/src/app/page.tsx` with:

```tsx
"use client";

import { useEffect, useState } from "react";
import { DeviceCard } from "@/components/DeviceCard";
import { useWebSocket } from "@/hooks/useWebSocket";
import { scanDevices, connectDevice, disconnectDevice, getStatus, DeviceInfo, DeviceStatus } from "@/lib/api";

export default function Dashboard() {
  const { isConnected: wsConnected, sensorData } = useWebSocket();
  const [availableDevices, setAvailableDevices] = useState<DeviceInfo[]>([]);
  const [connectedDevices, setConnectedDevices] = useState<DeviceStatus[]>([]);
  const [scanning, setScanning] = useState(false);

  const refreshStatus = async () => {
    try {
      const devices = await getStatus();
      setConnectedDevices(devices);
    } catch {
      // Server not running
    }
  };

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleScan = async () => {
    setScanning(true);
    try {
      const devices = await scanDevices();
      setAvailableDevices(devices);
    } finally {
      setScanning(false);
    }
  };

  const handleConnect = async (port: string) => {
    await connectDevice(port);
    await refreshStatus();
    setAvailableDevices([]);
  };

  const handleDisconnect = async (deviceId: string) => {
    await disconnectDevice(deviceId);
    await refreshStatus();
  };

  return (
    <main className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">MakeBlock Explorer</h1>
            <p className="text-gray-500 mt-1">CyberPi Dashboard</p>
          </div>
          <div className="flex items-center gap-4">
            <div className={`flex items-center gap-2 text-sm ${wsConnected ? "text-green-400" : "text-red-400"}`}>
              <div className={`w-2 h-2 rounded-full ${wsConnected ? "bg-green-400" : "bg-red-400"}`} />
              {wsConnected ? "Live" : "Offline"}
            </div>
            <button
              onClick={handleScan}
              disabled={scanning}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition disabled:opacity-50"
            >
              {scanning ? "Scanning..." : "Scan Devices"}
            </button>
          </div>
        </header>

        {availableDevices.length > 0 && (
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-4">
            <h2 className="text-sm font-semibold text-gray-400 mb-3">Available Devices</h2>
            {availableDevices.map((d) => (
              <div key={d.port} className="flex items-center justify-between py-2">
                <span className="text-gray-300">{d.port} — {d.description}</span>
                <button
                  onClick={() => handleConnect(d.port)}
                  className="px-3 py-1 bg-green-600 hover:bg-green-500 rounded text-sm transition"
                >
                  Connect
                </button>
              </div>
            ))}
          </div>
        )}

        {connectedDevices.length === 0 ? (
          <div className="text-center py-16 text-gray-600">
            <p className="text-xl">No devices connected</p>
            <p className="mt-2">Click "Scan Devices" to find your CyberPi</p>
          </div>
        ) : (
          <div className="space-y-4">
            {connectedDevices.map((d) => (
              <DeviceCard
                key={d.device_id}
                deviceId={d.device_id}
                port={d.port}
                sensors={sensorData[d.device_id] || d.sensor_cache}
                onDisconnect={() => handleDisconnect(d.device_id)}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
```

- [ ] Replace `web/src/app/layout.tsx` with:

```tsx
import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "MakeBlock Explorer",
  description: "CyberPi Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-gray-950 text-white">
        <nav className="border-b border-gray-800 px-8 py-3">
          <div className="max-w-4xl mx-auto flex gap-6 text-sm">
            <Link href="/" className="text-gray-300 hover:text-white transition">Dashboard</Link>
            <Link href="/controls" className="text-gray-300 hover:text-white transition">Controls</Link>
            <Link href="/notify" className="text-gray-300 hover:text-white transition">Notify</Link>
            <Link href="/settings" className="text-gray-300 hover:text-white transition">Settings</Link>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
```

- [ ] Commit:
```bash
git add web/src/
git commit -m "feat: add dashboard page with live sensor DeviceCards"
```

### Step 5.5: Create notification page

- [ ] Create `web/src/app/notify/page.tsx`:

```tsx
"use client";

import { useState, useEffect } from "react";
import { getStatus, pushNotify, DeviceStatus } from "@/lib/api";

export default function NotifyPage() {
  const [devices, setDevices] = useState<DeviceStatus[]>([]);
  const [selectedDevice, setSelectedDevice] = useState("");
  const [text, setText] = useState("");
  const [color, setColor] = useState("#00ff00");
  const [size, setSize] = useState(24);
  const [flashLeds, setFlashLeds] = useState(true);
  const [sending, setSending] = useState(false);
  const [history, setHistory] = useState<{ text: string; color: string; time: string }[]>([]);

  useEffect(() => {
    getStatus().then((d) => {
      setDevices(d);
      if (d.length > 0 && !selectedDevice) setSelectedDevice(d[0].device_id);
    });
  }, []);

  const hexToRgb = (hex: string): [number, number, number] => {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return [r, g, b];
  };

  const handleSend = async () => {
    if (!text || !selectedDevice) return;
    setSending(true);
    try {
      await pushNotify(selectedDevice, text, hexToRgb(color), size, flashLeds);
      setHistory((prev) => [
        { text, color, time: new Date().toLocaleTimeString() },
        ...prev.slice(0, 4),
      ]);
      setText("");
    } finally {
      setSending(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-lg mx-auto space-y-6">
        <h1 className="text-2xl font-bold">Push Notification</h1>
        <p className="text-gray-500">Send a message to the CyberPi display</p>

        <div className="space-y-4 bg-gray-900 border border-gray-700 rounded-xl p-6">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Device</label>
            <select
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(e.target.value)}
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white"
            >
              {devices.map((d) => (
                <option key={d.device_id} value={d.device_id}>{d.port} ({d.device_id})</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Message (max 30 chars)</label>
            <input
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, 30))}
              placeholder="Hi Chat!"
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white"
            />
            <div className="text-xs text-gray-600 mt-1">{text.length}/30</div>
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm text-gray-400 mb-1">Color</label>
              <input
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="w-full h-10 bg-gray-800 border border-gray-600 rounded-lg cursor-pointer"
              />
            </div>
            <div className="flex-1">
              <label className="block text-sm text-gray-400 mb-1">Size</label>
              <select
                value={size}
                onChange={(e) => setSize(Number(e.target.value))}
                className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white"
              >
                {[16, 20, 24, 28, 32].map((s) => (
                  <option key={s} value={s}>{s}pt</option>
                ))}
              </select>
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={flashLeds}
              onChange={(e) => setFlashLeds(e.target.checked)}
              className="rounded"
            />
            Flash LEDs with notification color
          </label>

          <button
            onClick={handleSend}
            disabled={!text || !selectedDevice || sending}
            className="w-full py-3 bg-green-600 hover:bg-green-500 rounded-lg font-semibold transition disabled:opacity-50"
          >
            {sending ? "Sending..." : "Send to CyberPi"}
          </button>
        </div>

        {history.length > 0 && (
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-4">
            <h2 className="text-sm font-semibold text-gray-400 mb-3">Recent</h2>
            {history.map((h, i) => (
              <div key={i} className="flex items-center gap-3 py-1 text-sm">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: h.color }} />
                <span className="text-gray-300">{h.text}</span>
                <span className="text-gray-600 ml-auto">{h.time}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
```

- [ ] Commit:
```bash
git add web/src/app/notify/
git commit -m "feat: add push notification page with color picker and history"
```

### Step 5.6: Create controls page

- [ ] Create `web/src/app/controls/page.tsx`:

```tsx
"use client";

import { useState, useEffect } from "react";
import { getStatus, setLed, executeCommand, DeviceStatus } from "@/lib/api";

export default function ControlsPage() {
  const [devices, setDevices] = useState<DeviceStatus[]>([]);
  const [selectedDevice, setSelectedDevice] = useState("");
  const [ledColor, setLedColor] = useState("#ff0000");
  const [displayText, setDisplayText] = useState("");
  const [displayColor, setDisplayColor] = useState("#ffffff");

  useEffect(() => {
    getStatus().then((d) => {
      setDevices(d);
      if (d.length > 0 && !selectedDevice) setSelectedDevice(d[0].device_id);
    });
  }, []);

  const hexToRgb = (hex: string): [number, number, number] => {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return [r, g, b];
  };

  const handleLed = async () => {
    const [r, g, b] = hexToRgb(ledColor);
    await setLed(selectedDevice, r, g, b);
  };

  const handleLedsOff = async () => {
    await setLed(selectedDevice, 0, 0, 0);
  };

  const handleDisplay = async () => {
    if (!displayText) return;
    const [r, g, b] = hexToRgb(displayColor);
    await executeCommand(selectedDevice, "cyberpi.display.clear()");
    await executeCommand(selectedDevice, `cyberpi.display.set_brush(${r},${g},${b})`);
    await executeCommand(selectedDevice, `cyberpi.display.show_label("${displayText}",24,10,50)`);
  };

  const handleClearDisplay = async () => {
    await executeCommand(selectedDevice, "cyberpi.display.clear()");
  };

  return (
    <main className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-lg mx-auto space-y-6">
        <h1 className="text-2xl font-bold">Device Controls</h1>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Device</label>
          <select
            value={selectedDevice}
            onChange={(e) => setSelectedDevice(e.target.value)}
            className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white"
          >
            {devices.map((d) => (
              <option key={d.device_id} value={d.device_id}>{d.port}</option>
            ))}
          </select>
        </div>

        <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 space-y-4">
          <h2 className="text-lg font-semibold">💡 LEDs</h2>
          <div className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="block text-sm text-gray-400 mb-1">Color</label>
              <input
                type="color"
                value={ledColor}
                onChange={(e) => setLedColor(e.target.value)}
                className="w-full h-10 bg-gray-800 border border-gray-600 rounded-lg cursor-pointer"
              />
            </div>
            <button onClick={handleLed} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg transition">
              Set
            </button>
            <button onClick={handleLedsOff} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition">
              Off
            </button>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 space-y-4">
          <h2 className="text-lg font-semibold">📺 Display</h2>
          <div className="flex gap-3">
            <input
              type="text"
              value={displayText}
              onChange={(e) => setDisplayText(e.target.value.slice(0, 30))}
              placeholder="Enter text..."
              className="flex-1 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white"
            />
            <input
              type="color"
              value={displayColor}
              onChange={(e) => setDisplayColor(e.target.value)}
              className="w-10 h-10 bg-gray-800 border border-gray-600 rounded-lg cursor-pointer"
            />
          </div>
          <div className="flex gap-3">
            <button onClick={handleDisplay} className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg transition">
              Show Text
            </button>
            <button onClick={handleClearDisplay} className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition">
              Clear
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
```

- [ ] Create placeholder `web/src/app/settings/page.tsx`:

```tsx
"use client";

export default function SettingsPage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-lg mx-auto">
        <h1 className="text-2xl font-bold mb-4">Settings</h1>
        <p className="text-gray-500">Device management and configuration — coming in a future update.</p>
      </div>
    </main>
  );
}
```

- [ ] Run: `cd C:/Dev/projects/stem/cyberpi/web && npm run build`
  Expected: Next.js builds successfully with no errors

- [ ] Commit:
```bash
git add web/src/
git commit -m "feat: add controls page, settings placeholder, and complete frontend"
```

---

## Task 6: Integration Verification

### Step 6.1: Run full test suite

- [ ] Run: `cd C:/Dev/projects/stem/cyberpi && pytest tests/ -v --tb=short`
  Expected: ALL tests pass — zero failures

### Step 6.2: Manual smoke test with real hardware

- [ ] Start the FastAPI server:
```bash
cd C:/Dev/projects/stem/cyberpi
python -m makeblock_explorer.api.server
```

- [ ] In another terminal, start the Next.js dev server:
```bash
cd C:/Dev/projects/stem/cyberpi/web
npm run dev
```

- [ ] Open browser to `http://localhost:3000`
- [ ] Click "Scan Devices" — should find CyberPi on COM port
- [ ] Click "Connect" — should connect (takes ~5 seconds for handshake)
- [ ] Verify live sensor data appears on DeviceCard
- [ ] Navigate to Controls — test LED color picker
- [ ] Navigate to Notify — send "Hi Chat!" in green
- [ ] Verify text appears on CyberPi display and LEDs flash

- [ ] Final commit:
```bash
git add -A
git commit -m "feat: complete CyberPi Dashboard v0.2.0 — F3 protocol + web dashboard"
```
