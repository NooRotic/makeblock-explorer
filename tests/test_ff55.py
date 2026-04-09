"""Tests for the FF55 protocol engine."""

import math
import struct

import pytest

from makeblock_explorer.protocol import (
    HEADER,
    Action,
    DataType,
    Packet,
    build_packet,
    decode_value,
    encode_value,
    find_packets,
    parse_packet,
)


# ─── Action enum ───────────────────────────────────────────────────────────


class TestAction:
    def test_action_values(self):
        assert Action.GET == 0x01
        assert Action.RUN == 0x02
        assert Action.RESET == 0x04
        assert Action.START == 0x05

    def test_action_from_int(self):
        assert Action(1) is Action.GET
        assert Action(2) is Action.RUN
        assert Action(4) is Action.RESET
        assert Action(5) is Action.START


# ─── Data type encoding/decoding ──────────────────────────────────────────


class TestDataTypes:
    def test_encode_byte(self):
        result = encode_value(DataType.BYTE, 42)
        assert result == bytes([1, 42])

    def test_encode_float(self):
        result = encode_value(DataType.FLOAT, 3.14)
        expected = bytes([2]) + struct.pack("<f", 3.14)
        assert result == expected

    def test_encode_short(self):
        result = encode_value(DataType.SHORT, -100)
        expected = bytes([3]) + struct.pack("<h", -100)
        assert result == expected

    def test_encode_string(self):
        result = encode_value(DataType.STRING, "hello")
        # type(1) + length(2 LE) + string bytes
        expected = bytes([4]) + struct.pack("<H", 5) + b"hello"
        assert result == expected

    def test_encode_string_bytes(self):
        result = encode_value(DataType.STRING, b"raw")
        expected = bytes([4]) + struct.pack("<H", 3) + b"raw"
        assert result == expected

    def test_encode_double(self):
        result = encode_value(DataType.DOUBLE, 2.718281828)
        expected = bytes([5]) + struct.pack("<d", 2.718281828)
        assert result == expected

    def test_encode_empty_string(self):
        result = encode_value(DataType.STRING, "")
        expected = bytes([4, 0, 0])
        assert result == expected

    def test_decode_byte(self):
        data = encode_value(DataType.BYTE, 255)
        value, consumed = decode_value(data)
        assert value == 255
        assert consumed == 2

    def test_decode_float(self):
        data = encode_value(DataType.FLOAT, 1.5)
        value, consumed = decode_value(data)
        assert math.isclose(value, 1.5, rel_tol=1e-6)
        assert consumed == 5

    def test_decode_short(self):
        data = encode_value(DataType.SHORT, -32768)
        value, consumed = decode_value(data)
        assert value == -32768
        assert consumed == 3

    def test_decode_string(self):
        data = encode_value(DataType.STRING, "test")
        value, consumed = decode_value(data)
        assert value == "test"
        assert consumed == 1 + 2 + 4  # type + length + chars

    def test_decode_double(self):
        data = encode_value(DataType.DOUBLE, 1.23456789012345)
        value, consumed = decode_value(data)
        assert math.isclose(value, 1.23456789012345, rel_tol=1e-14)
        assert consumed == 9

    def test_roundtrip_all_types(self):
        cases = [
            (DataType.BYTE, 0),
            (DataType.BYTE, 255),
            (DataType.FLOAT, 0.0),
            (DataType.FLOAT, -1.5),
            (DataType.SHORT, 0),
            (DataType.SHORT, 32767),
            (DataType.SHORT, -32768),
            (DataType.STRING, ""),
            (DataType.STRING, "hello world"),
            (DataType.DOUBLE, 0.0),
            (DataType.DOUBLE, -9999.9999),
        ]
        for dtype, val in cases:
            encoded = encode_value(dtype, val)
            decoded, consumed = decode_value(encoded)
            assert consumed == len(encoded), f"Consumed mismatch for {dtype.name}"
            if isinstance(val, float):
                assert math.isclose(decoded, val, rel_tol=1e-6), (
                    f"Value mismatch for {dtype.name}: {decoded} != {val}"
                )
            else:
                assert decoded == val, (
                    f"Value mismatch for {dtype.name}: {decoded} != {val}"
                )

    def test_decode_with_offset(self):
        prefix = b"\x00\x00\x00"
        data = prefix + encode_value(DataType.BYTE, 99)
        value, consumed = decode_value(data, offset=3)
        assert value == 99
        assert consumed == 2

    def test_decode_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown type ID"):
            decode_value(bytes([99, 0, 0]))

    def test_decode_truncated_string_length(self):
        with pytest.raises(ValueError, match="Truncated string length"):
            decode_value(bytes([4]))  # STRING type but no length bytes

    def test_decode_truncated_string_data(self):
        # STRING type + length says 10 but only 2 bytes of data
        data = bytes([4]) + struct.pack("<H", 10) + b"ab"
        with pytest.raises(ValueError, match="Truncated string data"):
            decode_value(data)

    def test_decode_truncated_fixed_type(self):
        with pytest.raises(ValueError, match="Truncated FLOAT"):
            decode_value(bytes([2, 0]))  # FLOAT type but only 1 data byte

    def test_decode_offset_beyond_data(self):
        with pytest.raises(ValueError, match="Offset .* beyond data length"):
            decode_value(b"\x01\x42", offset=5)


# ─── Packet building ──────────────────────────────────────────────────────


class TestBuildPacket:
    def test_basic_packet(self):
        raw = build_packet(1, Action.GET, 10)
        assert raw[:2] == HEADER
        assert raw[2] == 3  # length: index + action + device
        assert raw[3] == 1  # index
        assert raw[4] == 0x01  # GET
        assert raw[5] == 10  # device

    def test_packet_with_data(self):
        data = bytes([0xAA, 0xBB, 0xCC])
        raw = build_packet(5, Action.RUN, 20, data)
        assert raw[2] == 6  # 3 + 3 data bytes
        assert raw[6:] == data

    def test_zero_index(self):
        raw = build_packet(0, Action.RESET, 0)
        assert raw[3] == 0
        assert raw[5] == 0

    def test_max_index_and_device(self):
        raw = build_packet(255, Action.START, 255)
        assert raw[3] == 255
        assert raw[5] == 255

    def test_all_actions(self):
        for action in Action:
            raw = build_packet(0, action, 0)
            assert raw[4] == int(action)

    def test_invalid_index(self):
        with pytest.raises(ValueError, match="Index must be 0-255"):
            build_packet(256, Action.GET, 0)
        with pytest.raises(ValueError, match="Index must be 0-255"):
            build_packet(-1, Action.GET, 0)

    def test_invalid_device(self):
        with pytest.raises(ValueError, match="Device must be 0-255"):
            build_packet(0, Action.GET, 256)

    def test_payload_too_large(self):
        with pytest.raises(ValueError, match="Payload too large"):
            build_packet(0, Action.GET, 0, bytes(253))


# ─── Packet parsing ───────────────────────────────────────────────────────


class TestParsePacket:
    def test_roundtrip(self):
        raw = build_packet(7, Action.RUN, 42, b"\x01\x02\x03")
        pkt = parse_packet(raw)
        assert pkt.index == 7
        assert pkt.action == Action.RUN
        assert pkt.device == 42
        assert pkt.data == b"\x01\x02\x03"
        assert pkt.raw == raw

    def test_roundtrip_empty_data(self):
        raw = build_packet(0, Action.GET, 1)
        pkt = parse_packet(raw)
        assert pkt.index == 0
        assert pkt.data == b""

    def test_wrong_header(self):
        with pytest.raises(ValueError, match="Invalid header"):
            parse_packet(b"\xAA\xBB\x03\x00\x01\x00")

    def test_truncated_packet(self):
        with pytest.raises(ValueError, match="Packet too short"):
            parse_packet(b"\xff\x55\x03\x00")

    def test_length_exceeds_data(self):
        # Header says length=10 but only 3 bytes of payload follow
        with pytest.raises(ValueError, match="Packet truncated"):
            parse_packet(b"\xff\x55\x0a\x00\x01\x00")

    def test_unknown_action(self):
        # Build a packet manually with invalid action byte 0x99
        raw = b"\xff\x55\x03\x00\x99\x00"
        with pytest.raises(ValueError, match="Unknown action"):
            parse_packet(raw)

    def test_extra_bytes_ignored(self):
        """Extra bytes after the packet should not cause errors."""
        raw = build_packet(1, Action.GET, 5) + b"\xDE\xAD"
        pkt = parse_packet(raw)
        assert pkt.index == 1
        assert pkt.raw == raw[:-2]  # raw doesn't include extra bytes

    def test_parse_preserves_raw(self):
        raw = build_packet(10, Action.START, 100, b"\xFF")
        pkt = parse_packet(raw)
        assert pkt.raw == raw


# ─── Stream parsing ───────────────────────────────────────────────────────


class TestFindPackets:
    def test_single_packet(self):
        raw = build_packet(1, Action.GET, 5)
        results = find_packets(raw)
        assert len(results) == 1
        pkt, end = results[0]
        assert pkt.index == 1
        assert end == len(raw)

    def test_multiple_packets(self):
        p1 = build_packet(1, Action.GET, 5)
        p2 = build_packet(2, Action.RUN, 10, b"\xAA")
        p3 = build_packet(3, Action.RESET, 15)
        buf = p1 + p2 + p3
        results = find_packets(buf)
        assert len(results) == 3
        assert results[0][0].index == 1
        assert results[1][0].index == 2
        assert results[2][0].index == 3

    def test_garbage_between_packets(self):
        p1 = build_packet(1, Action.GET, 5)
        p2 = build_packet(2, Action.RUN, 10)
        buf = p1 + b"\xDE\xAD\xBE\xEF" + p2
        results = find_packets(buf)
        assert len(results) == 2
        assert results[0][0].index == 1
        assert results[1][0].index == 2

    def test_partial_packet_at_end(self):
        p1 = build_packet(1, Action.GET, 5)
        # Partial: header + length that says 10 more bytes, but only 2 follow
        partial = b"\xff\x55\x0a\x00\x01"
        buf = p1 + partial
        results = find_packets(buf)
        assert len(results) == 1
        assert results[0][0].index == 1

    def test_empty_buffer(self):
        assert find_packets(b"") == []

    def test_only_garbage(self):
        assert find_packets(b"\xDE\xAD\xBE\xEF") == []

    def test_false_header(self):
        """0xFF 0x55 appearing naturally but not a valid packet."""
        # FF55 followed by length=0 (too small)
        buf = b"\xff\x55\x00\x00\x00" + build_packet(1, Action.GET, 5)
        results = find_packets(buf)
        assert len(results) == 1
        assert results[0][0].index == 1

    def test_end_offsets_are_correct(self):
        p1 = build_packet(1, Action.GET, 5)
        p2 = build_packet(2, Action.RUN, 10)
        buf = p1 + p2
        results = find_packets(buf)
        assert results[0][1] == len(p1)
        assert results[1][1] == len(p1) + len(p2)
