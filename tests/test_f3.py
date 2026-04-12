"""Tests for the F3/F4 framed protocol engine."""

import pytest

from makeblock_explorer.protocol.f3 import (
    FOOTER,
    HEADER,
    MIN_FRAME_SIZE,
    OFFLINE_MODE_PACKET,
    ONLINE_MODE_PACKET,
    F3Packet,
    F3Response,
    Mode,
    PacketType,
    build_f3_packet,
    find_f3_frames,
    parse_f3_response,
)


# ─── Constants ─────────────────────────────────────────────────────────────


class TestConstants:
    def test_header_value(self):
        assert HEADER == 0xF3

    def test_footer_value(self):
        assert FOOTER == 0xF4

    def test_min_frame_size(self):
        assert MIN_FRAME_SIZE == 10

    def test_online_mode_packet(self):
        expected = bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x01, 0x0E, 0xF4])
        assert ONLINE_MODE_PACKET == expected

    def test_offline_mode_packet(self):
        expected = bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x00, 0x0D, 0xF4])
        assert OFFLINE_MODE_PACKET == expected


# ─── Enums ─────────────────────────────────────────────────────────────────


class TestEnums:
    def test_packet_type_enum_exists(self):
        assert hasattr(PacketType, "__members__")

    def test_mode_enum_exists(self):
        assert hasattr(Mode, "__members__")

    def test_packet_type_script_value(self):
        """SCRIPT must be 0x28 — the wire byte sent to real hardware."""
        assert PacketType.SCRIPT == 0x28

    def test_packet_type_online_value(self):
        assert PacketType.ONLINE == 0x0D

    def test_packet_type_run_without_response_value(self):
        assert PacketType.RUN_WITHOUT_RESPONSE == 0x00

    def test_packet_type_run_with_response_value(self):
        assert PacketType.RUN_WITH_RESPONSE == 0x01

    def test_packet_type_reset_value(self):
        assert PacketType.RESET == 0x02

    def test_packet_type_run_immediate_value(self):
        assert PacketType.RUN_IMMEDIATE == 0x03

    def test_packet_type_subscribe_value(self):
        assert PacketType.SUBSCRIBE == 0x29

    def test_mode_with_response_value(self):
        assert Mode.WITH_RESPONSE == 0x01

    def test_mode_without_response_value(self):
        assert Mode.WITHOUT_RESPONSE == 0x00

    def test_mode_immediate_value(self):
        assert Mode.IMMEDIATE == 0x03

    def test_packet_type_has_expected_member_count(self):
        assert len(PacketType.__members__) == 7

    def test_mode_has_expected_member_count(self):
        assert len(Mode.__members__) == 3


# ─── Dataclasses ───────────────────────────────────────────────────────────


class TestDataclasses:
    def test_f3_packet_has_expected_fields(self):
        import dataclasses

        fields = {f.name for f in dataclasses.fields(F3Packet)}
        assert "type" in fields
        assert "mode" in fields
        assert "index" in fields
        assert "data" in fields
        assert "script" in fields
        assert "raw" in fields

    def test_f3_response_has_expected_fields(self):
        import dataclasses

        fields = {f.name for f in dataclasses.fields(F3Response)}
        assert "index" in fields
        assert "value" in fields
        assert "error" in fields
        assert "raw" in fields


# ─── build_f3_packet ────────────────────────────────────────────────────────


class TestBuildF3Packet:
    def test_starts_with_header(self):
        pkt = build_f3_packet("pass", 1)
        assert pkt[0] == 0xF3

    def test_ends_with_footer(self):
        pkt = build_f3_packet("pass", 1)
        assert pkt[-1] == 0xF4

    def test_structure(self):
        """Verify the 8-byte framing structure."""
        script = "pass"
        pkt = build_f3_packet(script, 1)
        # [0]=0xF3, [1]=header_checksum, [2]=datalen_lo, [3]=datalen_hi,
        # [4]=type, [5]=mode, [6]=idx_lo, [7]=idx_hi, [8..n-2]=data, [-2]=body_checksum, [-1]=0xF4
        assert pkt[0] == 0xF3
        assert pkt[-1] == 0xF4
        assert len(pkt) >= 9  # at minimum header+checksum+datalen(2)+type+mode+idx(2)+body_chk+footer

    def test_type_byte_is_0x28(self):
        """Type byte at offset [4] must be 0x28 (PacketType.SCRIPT) for hardware compliance."""
        pkt = build_f3_packet("pass", 1)
        assert pkt[4] == 0x28

    def test_datalen_encodes_script_length_field(self):
        """datalen = 4 (type+mode+idx_lo+idx_hi) + 2 (script_len_lo+hi) + len(script_utf8)."""
        script = "pass"  # 4 bytes
        pkt = build_f3_packet(script, 1)
        script_bytes = script.encode("utf-8")
        expected_datalen = 4 + 2 + len(script_bytes)  # type+mode+idx(2) + script_len(2) + data
        datalen_lo = pkt[2]
        datalen_hi = pkt[3]
        actual_datalen = datalen_lo | (datalen_hi << 8)
        assert actual_datalen == expected_datalen

    def test_header_checksum(self):
        script = "pass"
        pkt = build_f3_packet(script, 1)
        datalen_lo = pkt[2]
        datalen_hi = pkt[3]
        expected_hchk = (0xF3 + datalen_lo + datalen_hi) & 0xFF
        assert pkt[1] == expected_hchk

    def test_body_checksum(self):
        script = "pass"
        pkt = build_f3_packet(script, 1)
        # data field = [script_len_lo, script_len_hi] + script_bytes
        script_bytes = script.encode("utf-8")
        slen = len(script_bytes)
        data_field = bytes([slen & 0xFF, (slen >> 8) & 0xFF]) + script_bytes
        # body fields: type, mode, idx_lo, idx_hi at pkt[4:8]
        type_b = pkt[4]
        mode_b = pkt[5]
        idx_lo = pkt[6]
        idx_hi = pkt[7]
        expected_bchk = (type_b + mode_b + idx_lo + idx_hi + sum(data_field)) & 0xFF
        body_chk = pkt[-2]
        assert body_chk == expected_bchk

    def test_index_little_endian(self):
        # Use index 300 = 0x012C -> lo=0x2C, hi=0x01
        pkt = build_f3_packet("pass", 300)
        idx_lo = pkt[6]
        idx_hi = pkt[7]
        assert idx_lo == 0x2C
        assert idx_hi == 0x01

    def test_index_zero(self):
        pkt = build_f3_packet("pass", 0)
        assert pkt[6] == 0x00
        assert pkt[7] == 0x00

    def test_index_max_single_byte(self):
        pkt = build_f3_packet("pass", 255)
        assert pkt[6] == 0xFF
        assert pkt[7] == 0x00

    def test_utf8_encoding(self):
        """Script bytes should be UTF-8 encoded in the data field."""
        script = "print('héllo')"
        pkt = build_f3_packet(script, 1)
        script_bytes = script.encode("utf-8")
        # Script bytes should appear in the packet body
        assert script_bytes in pkt

    def test_default_mode(self):
        """Default mode should produce a valid packet."""
        pkt = build_f3_packet("pass", 1)
        assert pkt is not None
        assert len(pkt) > 0

    def test_different_modes_produce_different_packets(self):
        """If mode parameter is supported, different modes differ."""
        modes = list(Mode)
        if len(modes) >= 2:
            pkt1 = build_f3_packet("pass", 1, modes[0])
            pkt2 = build_f3_packet("pass", 1, modes[1])
            assert pkt1 != pkt2

    def test_empty_script_raises(self):
        with pytest.raises(ValueError, match="[Ss]cript"):
            build_f3_packet("", 1)

    def test_packet_total_length(self):
        """Total packet size = 1(F3) + 1(hchk) + 2(datalen) + datalen + 1(bchk) + 1(F4)."""
        script = "pass"
        pkt = build_f3_packet(script, 1)
        script_bytes = script.encode("utf-8")
        datalen = 4 + 2 + len(script_bytes)
        expected_len = 1 + 1 + 2 + datalen + 1 + 1
        assert len(pkt) == expected_len

    def test_multiline_script(self):
        script = "x = 1\ny = 2\nprint(x + y)"
        pkt = build_f3_packet(script, 5)
        assert pkt[0] == 0xF3
        assert pkt[-1] == 0xF4
        script_bytes = script.encode("utf-8")
        assert script_bytes in pkt


# ─── find_f3_frames ─────────────────────────────────────────────────────────


class TestFindF3Frames:
    def test_single_valid_frame(self):
        pkt = build_f3_packet("pass", 1)
        results = find_f3_frames(pkt)
        assert len(results) == 1

    def test_single_frame_returns_packet_and_offset(self):
        pkt = build_f3_packet("pass", 1)
        results = find_f3_frames(pkt)
        frame, end = results[0]
        assert isinstance(frame, F3Packet)
        assert end == len(pkt)

    def test_garbage_prefix(self):
        pkt = build_f3_packet("pass", 1)
        buf = bytes([0xDE, 0xAD, 0xBE, 0xEF]) + pkt
        results = find_f3_frames(buf)
        assert len(results) == 1
        _, end = results[0]
        assert end == len(buf)

    def test_multiple_consecutive_frames(self):
        p1 = build_f3_packet("x=1", 1)
        p2 = build_f3_packet("y=2", 2)
        p3 = build_f3_packet("z=3", 3)
        buf = p1 + p2 + p3
        results = find_f3_frames(buf)
        assert len(results) == 3
        assert results[0][0].index == 1
        assert results[1][0].index == 2
        assert results[2][0].index == 3

    def test_partial_frame_at_end_ignored(self):
        pkt = build_f3_packet("pass", 1)
        partial = pkt[:5]  # truncated
        buf = pkt + partial
        results = find_f3_frames(buf)
        assert len(results) == 1

    def test_bad_header_checksum_rejected(self):
        pkt = bytearray(build_f3_packet("pass", 1))
        pkt[1] ^= 0xFF  # corrupt header checksum
        results = find_f3_frames(bytes(pkt))
        assert len(results) == 0

    def test_bad_body_checksum_rejected(self):
        pkt = bytearray(build_f3_packet("pass", 1))
        pkt[-2] ^= 0xFF  # corrupt body checksum
        results = find_f3_frames(bytes(pkt))
        assert len(results) == 0

    def test_empty_buffer(self):
        assert find_f3_frames(b"") == []

    def test_only_garbage(self):
        assert find_f3_frames(b"\xDE\xAD\xBE\xEF\x00\x01\x02") == []

    def test_online_mode_packet(self):
        """ONLINE_MODE_PACKET should be found as a valid frame."""
        results = find_f3_frames(ONLINE_MODE_PACKET)
        assert len(results) == 1

    def test_offline_mode_packet(self):
        """OFFLINE_MODE_PACKET should be found as a valid frame."""
        results = find_f3_frames(OFFLINE_MODE_PACKET)
        assert len(results) == 1

    def test_end_offsets_correct(self):
        p1 = build_f3_packet("x=1", 1)
        p2 = build_f3_packet("y=2", 2)
        buf = p1 + p2
        results = find_f3_frames(buf)
        assert results[0][1] == len(p1)
        assert results[1][1] == len(p1) + len(p2)

    def test_script_field_populated(self):
        script = "print(42)"
        pkt = build_f3_packet(script, 1)
        results = find_f3_frames(pkt)
        assert len(results) == 1
        frame, _ = results[0]
        assert frame.script == script

    def test_raw_field_matches_original(self):
        pkt = build_f3_packet("pass", 1)
        results = find_f3_frames(pkt)
        frame, _ = results[0]
        assert frame.raw == pkt


# ─── parse_f3_response ──────────────────────────────────────────────────────


class TestParseF3Response:
    def _make_response(self, json_str: str, index: int = 1) -> bytes:
        """Build a minimal F3 response frame containing JSON data."""
        # Response frame: same structure as request but data contains JSON bytes
        payload = json_str.encode("utf-8")
        slen = len(payload)
        data_field = bytes([slen & 0xFF, (slen >> 8) & 0xFF]) + payload
        datalen = 4 + len(data_field)
        datalen_lo = datalen & 0xFF
        datalen_hi = (datalen >> 8) & 0xFF
        header_chk = (0xF3 + datalen_lo + datalen_hi) & 0xFF
        type_b = int(PacketType.SCRIPT)  # 0x28 — spec-compliant response type
        mode_b = 0x00
        idx_lo = index & 0xFF
        idx_hi = (index >> 8) & 0xFF
        body_chk = (type_b + mode_b + idx_lo + idx_hi + sum(data_field)) & 0xFF
        return (
            bytes([0xF3, header_chk, datalen_lo, datalen_hi, type_b, mode_b, idx_lo, idx_hi])
            + data_field
            + bytes([body_chk, 0xF4])
        )

    def test_integer_ret(self):
        raw = self._make_response('{"ret": 42}', index=1)
        responses = parse_f3_response(raw)
        assert len(responses) == 1
        resp = responses[0]
        assert resp.value == 42
        assert resp.error is None

    def test_float_ret(self):
        raw = self._make_response('{"ret": 0.2}', index=2)
        responses = parse_f3_response(raw)
        assert len(responses) == 1
        assert abs(responses[0].value - 0.2) < 1e-9

    def test_string_ret(self):
        raw = self._make_response('{"ret": "44.01.011"}', index=3)
        responses = parse_f3_response(raw)
        assert len(responses) == 1
        assert responses[0].value == "44.01.011"

    def test_null_ret(self):
        raw = self._make_response('{"ret": null}', index=4)
        responses = parse_f3_response(raw)
        assert len(responses) == 1
        assert responses[0].value is None
        assert responses[0].error is None

    def test_error_response(self):
        raw = self._make_response('{"err": "TypeError"}', index=5)
        responses = parse_f3_response(raw)
        assert len(responses) == 1
        resp = responses[0]
        assert resp.error == "TypeError"
        assert resp.value is None

    def test_multiple_responses(self):
        r1 = self._make_response('{"ret": 1}', index=1)
        r2 = self._make_response('{"ret": 2}', index=2)
        responses = parse_f3_response(r1 + r2)
        assert len(responses) == 2
        assert responses[0].value == 1
        assert responses[1].value == 2

    def test_garbage_tolerance(self):
        """Garbage before a valid response should be skipped."""
        raw = self._make_response('{"ret": 99}', index=1)
        buf = bytes([0xAA, 0xBB, 0xCC]) + raw
        responses = parse_f3_response(buf)
        assert len(responses) == 1
        assert responses[0].value == 99

    def test_empty_data(self):
        responses = parse_f3_response(b"")
        assert responses == []

    def test_response_has_index(self):
        raw = self._make_response('{"ret": 7}', index=42)
        responses = parse_f3_response(raw)
        assert responses[0].index == 42

    def test_response_raw_field(self):
        raw = self._make_response('{"ret": 0}', index=1)
        responses = parse_f3_response(raw)
        assert responses[0].raw == raw
