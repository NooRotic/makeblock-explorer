"""Tests for the traffic capture module."""

from __future__ import annotations

import json
import time

from makeblock_explorer.protocol.capture import (
    CaptureEntry,
    CaptureTransport,
    format_hex_dump,
    load_capture,
)
from makeblock_explorer.protocol.ff55 import Action, build_packet


class FakeTransport:
    """Minimal Transport implementation for testing."""

    def __init__(self) -> None:
        self._connected = False
        self._rx_buffer = b""
        self._sent: list[bytes] = []

    def connect(self, target: str) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def send(self, data: bytes) -> None:
        self._sent.append(data)

    def receive(self, timeout: float = 1.0) -> bytes:
        data = self._rx_buffer
        self._rx_buffer = b""
        return data

    @property
    def is_connected(self) -> bool:
        return self._connected

    def stage_rx(self, data: bytes) -> None:
        """Stage data to be returned by the next receive() call."""
        self._rx_buffer = data


class TestCaptureTransportDelegation:
    """CaptureTransport correctly delegates to the inner transport."""

    def test_connect_delegates(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner)
        ct.connect("COM4")
        assert inner.is_connected

    def test_disconnect_delegates(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner)
        ct.connect("COM4")
        ct.disconnect()
        assert not inner.is_connected

    def test_send_delegates(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner)
        ct.send(b"\x01\x02\x03")
        assert inner._sent == [b"\x01\x02\x03"]

    def test_receive_delegates(self) -> None:
        inner = FakeTransport()
        inner.stage_rx(b"\xAA\xBB")
        ct = CaptureTransport(inner)
        result = ct.receive(timeout=0.5)
        assert result == b"\xAA\xBB"

    def test_is_connected_delegates(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner)
        assert not ct.is_connected
        ct.connect("COM4")
        assert ct.is_connected


class TestCaptureTransportRecording:
    """CaptureTransport records TX and RX entries."""

    def test_send_records_tx(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner)
        ct.send(b"\x01\x02")
        entries = ct.entries
        assert len(entries) == 1
        assert entries[0].direction == "tx"
        assert entries[0].raw == b"\x01\x02"
        assert entries[0].timestamp > 0

    def test_receive_records_rx(self) -> None:
        inner = FakeTransport()
        inner.stage_rx(b"\x03\x04")
        ct = CaptureTransport(inner)
        ct.receive()
        entries = ct.entries
        assert len(entries) == 1
        assert entries[0].direction == "rx"
        assert entries[0].raw == b"\x03\x04"

    def test_receive_empty_not_recorded(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner)
        ct.receive()  # returns empty bytes
        assert len(ct.entries) == 0

    def test_ff55_packet_decoded(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner)
        packet = build_packet(index=1, action=Action.GET, device=0x1E, data=b"\x00")
        ct.send(packet)
        entry = ct.entries[0]
        assert entry.decoded is not None
        assert entry.decoded["index"] == 1
        assert entry.decoded["action"] == "GET"
        assert entry.decoded["device"] == "0x1E"
        assert entry.decoded["data_hex"] == "00"
        assert entry.decoded["data_len"] == 1

    def test_non_ff55_decoded_is_none(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner)
        ct.send(b"\x00\x01\x02")
        entry = ct.entries[0]
        assert entry.decoded is None

    def test_clear_empties_entries(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner)
        ct.send(b"\x01")
        assert len(ct.entries) == 1
        ct.clear()
        assert len(ct.entries) == 0


class TestCaptureTransportJSONL:
    """CaptureTransport writes JSONL log files correctly."""

    def test_jsonl_written(self, tmp_path) -> None:
        log_file = tmp_path / "capture.jsonl"
        inner = FakeTransport()
        ct = CaptureTransport(inner, log_path=log_file)
        packet = build_packet(index=5, action=Action.RUN, device=0x0A)
        ct.send(packet)
        ct.close()

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["dir"] == "tx"
        assert data["raw"] == packet.hex()
        assert data["decoded"]["index"] == 5
        assert data["decoded"]["action"] == "RUN"
        assert "ts" in data

    def test_multiple_entries_written(self, tmp_path) -> None:
        log_file = tmp_path / "capture.jsonl"
        inner = FakeTransport()
        ct = CaptureTransport(inner, log_path=log_file)
        ct.send(b"\x01")
        ct.send(b"\x02")
        ct.close()

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_memory_only_mode(self) -> None:
        inner = FakeTransport()
        ct = CaptureTransport(inner, log_path=None)
        ct.send(b"\x01\x02")
        assert len(ct.entries) == 1
        ct.close()  # should not raise

    def test_close_closes_file(self, tmp_path) -> None:
        log_file = tmp_path / "capture.jsonl"
        inner = FakeTransport()
        ct = CaptureTransport(inner, log_path=log_file)
        ct.send(b"\x01")
        ct.close()
        assert ct._log_file is None


class TestLoadCapture:
    """load_capture() reads JSONL files back into CaptureEntry lists."""

    def test_roundtrip(self, tmp_path) -> None:
        log_file = tmp_path / "capture.jsonl"
        inner = FakeTransport()
        packet = build_packet(index=3, action=Action.GET, device=0x1E, data=b"\xAB")
        ct = CaptureTransport(inner, log_path=log_file)
        ct.send(packet)
        inner.stage_rx(b"\xDE\xAD")
        ct.receive()
        ct.close()

        loaded = load_capture(log_file)
        assert len(loaded) == 2

        # TX entry
        assert loaded[0].direction == "tx"
        assert loaded[0].raw == packet
        assert loaded[0].decoded is not None
        assert loaded[0].decoded["index"] == 3

        # RX entry (non-FF55)
        assert loaded[1].direction == "rx"
        assert loaded[1].raw == b"\xDE\xAD"
        assert loaded[1].decoded is None

    def test_empty_file(self, tmp_path) -> None:
        log_file = tmp_path / "empty.jsonl"
        log_file.write_text("", encoding="utf-8")
        loaded = load_capture(log_file)
        assert loaded == []

    def test_blank_lines_skipped(self, tmp_path) -> None:
        log_file = tmp_path / "capture.jsonl"
        entry = json.dumps({"ts": 1000.0, "dir": "tx", "raw": "ff55", "decoded": None})
        log_file.write_text(entry + "\n\n\n", encoding="utf-8")
        loaded = load_capture(log_file)
        assert len(loaded) == 1


class TestFormatHexDump:
    """format_hex_dump() produces readable annotated output."""

    def test_basic_format(self) -> None:
        entry = CaptureEntry(
            timestamp=1000.5,
            direction="tx",
            raw=b"\x01\x02\x03",
            decoded=None,
        )
        result = format_hex_dump([entry])
        assert "TX" in result
        assert "01 02 03" in result

    def test_ff55_annotation(self) -> None:
        packet = build_packet(index=1, action=Action.GET, device=0x1E, data=b"\x00")
        entry = CaptureEntry(
            timestamp=1000.0,
            direction="tx",
            raw=packet,
            decoded={
                "index": 1,
                "action": "GET",
                "device": "0x1E",
                "data_hex": "00",
                "data_len": 1,
            },
        )
        result = format_hex_dump([entry])
        assert "^^^^^ hdr" in result
        assert "^data..." in result

    def test_ff55_no_data_no_data_annotation(self) -> None:
        packet = build_packet(index=1, action=Action.GET, device=0x1E)
        entry = CaptureEntry(
            timestamp=1000.0,
            direction="tx",
            raw=packet,
            decoded={
                "index": 1,
                "action": "GET",
                "device": "0x1E",
                "data_hex": "",
                "data_len": 0,
            },
        )
        result = format_hex_dump([entry])
        assert "^^^^^ hdr" in result
        assert "^data..." not in result

    def test_multiple_entries(self) -> None:
        entries = [
            CaptureEntry(timestamp=1000.0, direction="tx", raw=b"\x01", decoded=None),
            CaptureEntry(timestamp=1000.1, direction="rx", raw=b"\x02", decoded=None),
        ]
        result = format_hex_dump(entries)
        lines = result.split("\n")
        assert len(lines) == 2
        assert "TX" in lines[0]
        assert "RX" in lines[1]

    def test_rx_direction(self) -> None:
        entry = CaptureEntry(
            timestamp=1000.0,
            direction="rx",
            raw=b"\xFF",
            decoded=None,
        )
        result = format_hex_dump([entry])
        assert "RX" in result

    def test_timestamp_format(self) -> None:
        # Use a known timestamp and check format
        entry = CaptureEntry(
            timestamp=1000.123,
            direction="tx",
            raw=b"\x01",
            decoded=None,
        )
        result = format_hex_dump([entry])
        # Should have HH:MM:SS.mmm format
        import re
        assert re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}", result)
