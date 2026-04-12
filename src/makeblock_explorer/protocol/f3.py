"""F3/F4 framed protocol engine for MakeBlock CyberPi and HaloCode devices.

Implements the MakeBlock F3 binary framing protocol:
    [0xF3][HeaderChecksum][DataLen_Lo][DataLen_Hi][Type][Mode][Idx_Lo][Idx_Hi][Data...][BodyChecksum][0xF4]

Checksum formulas:
    Header checksum: (0xF3 + datalen_lo + datalen_hi) & 0xFF
    Body checksum:   (type + mode + idx_lo + idx_hi + sum(data)) & 0xFF

Data field format for script packets:
    [script_len_lo, script_len_hi] + script_utf8_bytes

This is a pure-logic layer with no I/O or hardware dependencies.
"""

import json
from dataclasses import dataclass, field
from enum import IntEnum

HEADER: int = 0xF3
FOOTER: int = 0xF4

# Fixed framing sizes
_FRAME_OVERHEAD = 6  # 0xF3 + hchk + datalen(2) + bchk + 0xF4
_BODY_MIN_SIZE = 3   # type + mode + idx_lo (minimum; mode-switch packets)
_BODY_HEADER_SIZE = 4  # type + mode + idx_lo + idx_hi (script packets)
MIN_FRAME_SIZE = 10  # Minimum total frame size (header + overhead + minimum body)

# Pre-built mode switch packets (full wire bytes including checksums)
ONLINE_MODE_PACKET = bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x01, 0x0E, 0xF4])
OFFLINE_MODE_PACKET = bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x00, 0x0D, 0xF4])


class PacketType(IntEnum):
    """F3 packet type identifiers."""

    RUN_WITHOUT_RESPONSE = 0x00  # Run script, no response expected
    RUN_WITH_RESPONSE = 0x01     # Run script, response expected
    RESET = 0x02                 # Reset device
    RUN_IMMEDIATE = 0x03         # Run immediately
    ONLINE = 0x0D                # Online/offline mode switch
    SCRIPT = 0x28                # MicroPython script execution request
    SUBSCRIBE = 0x29             # Subscribe to events


class Mode(IntEnum):
    """F3 execution mode."""

    WITHOUT_RESPONSE = 0x00  # Execute without response
    WITH_RESPONSE = 0x01     # Execute with response
    IMMEDIATE = 0x03         # Execute immediately


@dataclass
class F3Packet:
    """A parsed F3 framed packet.

    Attributes:
        type: PacketType byte value from the frame.
        mode: Mode byte value from the frame.
        index: Command index (little-endian 2-byte) for request/response correlation.
        data: Raw data field bytes (after type/mode/idx bytes, before body checksum).
        script: Decoded MicroPython script string if this is a script packet, else None.
        raw: Original complete packet bytes for capture/debugging.
    """

    type: int
    mode: int
    index: int
    data: bytes
    script: str | None
    raw: bytes


@dataclass
class F3Response:
    """A parsed F3 response from the device.

    Attributes:
        index: Command index correlated with the originating request.
        value: Decoded return value from {"ret": value} JSON, or None.
        error: Error message from {"err": msg} JSON, or None.
        raw: Original complete response frame bytes.
    """

    index: int
    value: object
    error: str | None
    raw: bytes


def _compute_header_checksum(datalen_lo: int, datalen_hi: int) -> int:
    """Compute the F3 header checksum."""
    return (0xF3 + datalen_lo + datalen_hi) & 0xFF


def _compute_body_checksum(
    type_b: int, mode_b: int, idx_lo: int, idx_hi: int, data: bytes
) -> int:
    """Compute the F3 body checksum."""
    return (type_b + mode_b + idx_lo + idx_hi + sum(data)) & 0xFF


def build_f3_packet(
    script: str,
    index: int,
    mode: int = Mode.WITH_RESPONSE,
) -> bytes:
    """Encode a MicroPython script into a complete F3 wire packet.

    Frame layout:
        [0xF3][hchk][datalen_lo][datalen_hi][type][mode][idx_lo][idx_hi]
        [script_len_lo][script_len_hi][script_utf8...][bchk][0xF4]

    Args:
        script: MicroPython source code string to execute. Must be non-empty.
        index: Command index (0-65535) for request/response correlation.
        mode: Execution mode (default Mode.WITH_RESPONSE).

    Returns:
        Complete F3 framed packet as bytes.

    Raises:
        ValueError: If script is empty.
    """
    if not script:
        raise ValueError("Script must be non-empty")

    script_bytes = script.encode("utf-8")
    slen = len(script_bytes)

    # Data field: 2-byte LE script length prefix + script bytes
    data = bytes([slen & 0xFF, (slen >> 8) & 0xFF]) + script_bytes

    type_b = int(PacketType.SCRIPT)
    mode_b = int(mode)
    idx_lo = index & 0xFF
    idx_hi = (index >> 8) & 0xFF

    # datalen = body header (4) + data field length
    datalen = _BODY_HEADER_SIZE + len(data)
    datalen_lo = datalen & 0xFF
    datalen_hi = (datalen >> 8) & 0xFF

    header_chk = _compute_header_checksum(datalen_lo, datalen_hi)
    body_chk = _compute_body_checksum(type_b, mode_b, idx_lo, idx_hi, data)

    return (
        bytes([HEADER, header_chk, datalen_lo, datalen_hi, type_b, mode_b, idx_lo, idx_hi])
        + data
        + bytes([body_chk, FOOTER])
    )


def _try_parse_frame(buffer: bytes, pos: int) -> tuple[F3Packet, int] | None:
    """Attempt to parse a single F3 frame starting at pos in buffer.

    Returns:
        (F3Packet, end_offset) if a valid frame is found, else None.
    """
    if buffer[pos] != HEADER:
        return None

    # Need at least 4 bytes for header byte + hchk + datalen(2)
    if pos + 4 > len(buffer):
        return None

    datalen_lo = buffer[pos + 2]
    datalen_hi = buffer[pos + 3]
    datalen = datalen_lo | (datalen_hi << 8)

    # Total frame length: 1(F3) + 1(hchk) + 2(datalen) + datalen + 1(bchk) + 1(F4)
    end = pos + _FRAME_OVERHEAD + datalen
    if end > len(buffer):
        return None  # Partial frame

    # Validate footer
    if buffer[end - 1] != FOOTER:
        return None

    # Validate header checksum
    expected_hchk = _compute_header_checksum(datalen_lo, datalen_hi)
    if buffer[pos + 1] != expected_hchk:
        return None

    # Validate datalen >= 3 (minimum: type + mode + idx_lo)
    if datalen < _BODY_MIN_SIZE:
        return None

    type_b = buffer[pos + 4]
    mode_b = buffer[pos + 5]
    idx_lo = buffer[pos + 6]

    if datalen >= _BODY_HEADER_SIZE:
        # Full body header: type + mode + idx_lo + idx_hi + data
        idx_hi = buffer[pos + 7]
        index = idx_lo | (idx_hi << 8)
        data = bytes(buffer[pos + 8 : end - 2])
    else:
        # Short body (datalen == 3): type + mode + idx_lo only (mode-switch packets)
        idx_hi = 0x00
        index = idx_lo
        data = b""

    # Validate body checksum
    body_chk = buffer[end - 2]
    expected_bchk = _compute_body_checksum(type_b, mode_b, idx_lo, idx_hi, data)
    if body_chk != expected_bchk:
        return None

    raw = bytes(buffer[pos:end])

    # Try to decode script from data field (script_len_lo + script_len_hi + script_bytes)
    script: str | None = None
    if len(data) >= 2:
        script_len = data[0] | (data[1] << 8)
        if len(data) >= 2 + script_len:
            try:
                script = data[2 : 2 + script_len].decode("utf-8")
            except UnicodeDecodeError:
                script = None

    packet = F3Packet(
        type=type_b,
        mode=mode_b,
        index=index,
        data=data,
        script=script,
        raw=raw,
    )
    return packet, end


def find_f3_frames(buffer: bytes) -> list[tuple[F3Packet, int]]:
    """Scan raw bytes for valid F3 frames with header and body checksum validation.

    Useful for parsing a stream buffer that may contain partial, multiple, or
    garbage-prefixed frames.

    Args:
        buffer: Raw byte buffer to scan.

    Returns:
        List of (F3Packet, end_offset) tuples. end_offset is the index of the
        first byte after the packet in the buffer.
    """
    results: list[tuple[F3Packet, int]] = []
    pos = 0

    while pos < len(buffer):
        if buffer[pos] != HEADER:
            pos += 1
            continue

        result = _try_parse_frame(buffer, pos)
        if result is not None:
            packet, end = result
            results.append((packet, end))
            pos = end
        else:
            # Not a valid frame at this position; skip the 0xF3 byte and keep scanning
            pos += 1

    return results


def _extract_json_payload(data: bytes) -> str | None:
    """Extract the JSON string from a response frame's data field.

    The data field starts with [script_len_lo, script_len_hi] followed by the payload.
    """
    if len(data) < 2:
        return None
    payload_len = data[0] | (data[1] << 8)
    if len(data) < 2 + payload_len:
        return None
    try:
        return data[2 : 2 + payload_len].decode("utf-8")
    except UnicodeDecodeError:
        return None


def parse_f3_response(data: bytes) -> list[F3Response]:
    """Parse F3 response frames from a byte stream and extract return values.

    Each response frame contains a JSON payload in its data field, in one of two forms:
        {"ret": value}  — successful return value (int, float, str, null)
        {"err": "msg"}  — error message

    Args:
        data: Raw byte buffer from the device (may contain multiple frames or garbage).

    Returns:
        List of F3Response objects for each successfully parsed response frame.
    """
    responses: list[F3Response] = []

    for packet, end in find_f3_frames(data):
        json_str = _extract_json_payload(packet.data)
        if json_str is None:
            continue

        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError:
            continue

        if not isinstance(obj, dict):
            continue

        if "ret" in obj:
            responses.append(
                F3Response(
                    index=packet.index,
                    value=obj["ret"],
                    error=None,
                    raw=packet.raw,
                )
            )
        elif "err" in obj:
            responses.append(
                F3Response(
                    index=packet.index,
                    value=None,
                    error=str(obj["err"]),
                    raw=packet.raw,
                )
            )

    return responses
