"""FF55 protocol packet building and parsing.

Implements the MakeBlock FF55 binary protocol:
    [0xFF][0x55][Length][Index][Action][Device][Data...]

This is a pure-logic layer with no I/O or hardware dependencies.
"""

from dataclasses import dataclass
from enum import IntEnum

HEADER = b"\xff\x55"
HEADER_SIZE = 2
LENGTH_SIZE = 1
MIN_PAYLOAD = 3  # index + action + device (minimum, no data)
MIN_PACKET_SIZE = HEADER_SIZE + LENGTH_SIZE + MIN_PAYLOAD


class Action(IntEnum):
    """FF55 command action types."""

    GET = 0x01
    RUN = 0x02
    RESET = 0x04
    START = 0x05


@dataclass
class Packet:
    """A parsed FF55 protocol packet.

    Attributes:
        index: Command index for request/response correlation.
        action: The action type (GET, RUN, RESET, START).
        device: Target device/module type ID.
        data: Variable-length payload bytes.
        raw: Original complete packet bytes for capture/debugging.
    """

    index: int
    action: Action
    device: int
    data: bytes
    raw: bytes


def build_packet(
    index: int, action: Action, device: int, data: bytes = b""
) -> bytes:
    """Build a complete FF55 packet from components.

    Args:
        index: Command index (0-255) for request/response correlation.
        action: The action type to perform.
        device: Target device/module type ID (0-255).
        data: Optional payload data bytes.

    Returns:
        Complete FF55 packet as bytes.

    Raises:
        ValueError: If index or device is out of range, or payload too large.
    """
    if not 0 <= index <= 255:
        raise ValueError(f"Index must be 0-255, got {index}")
    if not 0 <= device <= 255:
        raise ValueError(f"Device must be 0-255, got {device}")

    # Length = index(1) + action(1) + device(1) + data(N)
    length = 3 + len(data)
    if length > 255:
        raise ValueError(
            f"Payload too large: length field would be {length} (max 255)"
        )

    return HEADER + bytes([length, index, int(action), device]) + data


def parse_packet(raw: bytes) -> Packet:
    """Parse raw bytes into a Packet.

    Args:
        raw: Complete packet bytes starting with the FF55 header.

    Returns:
        Parsed Packet instance.

    Raises:
        ValueError: If the packet is invalid (wrong header, truncated, bad length).
    """
    if len(raw) < MIN_PACKET_SIZE:
        raise ValueError(
            f"Packet too short: {len(raw)} bytes (minimum {MIN_PACKET_SIZE})"
        )

    if raw[:2] != HEADER:
        raise ValueError(
            f"Invalid header: expected FF55, got {raw[0]:02X}{raw[1]:02X}"
        )

    length = raw[2]
    if length < MIN_PAYLOAD:
        raise ValueError(
            f"Length field too small: {length} (minimum {MIN_PAYLOAD})"
        )

    expected_total = HEADER_SIZE + LENGTH_SIZE + length
    if len(raw) < expected_total:
        raise ValueError(
            f"Packet truncated: expected {expected_total} bytes, got {len(raw)}"
        )

    index = raw[3]
    action_byte = raw[4]
    try:
        action = Action(action_byte)
    except ValueError:
        raise ValueError(f"Unknown action: 0x{action_byte:02X}")

    device = raw[5]
    data = raw[6:expected_total]

    return Packet(
        index=index,
        action=action,
        device=device,
        data=data,
        raw=raw[:expected_total],
    )


def find_packets(buffer: bytes) -> list[tuple[Packet, int]]:
    """Find all valid FF55 packets in a byte buffer.

    Scans the buffer for FF55 headers and attempts to parse complete packets.
    Useful for parsing a stream buffer that may contain partial or multiple
    packets, with possible garbage bytes between them.

    Args:
        buffer: Raw byte buffer to scan.

    Returns:
        List of (Packet, end_offset) tuples. end_offset is the index of the
        first byte after the packet in the buffer.
    """
    results: list[tuple[Packet, int]] = []
    pos = 0

    while pos <= len(buffer) - MIN_PACKET_SIZE:
        # Scan for header
        if buffer[pos] != 0xFF or buffer[pos + 1] != 0x55:
            pos += 1
            continue

        # Check if we have enough bytes for the length field
        if pos + HEADER_SIZE + LENGTH_SIZE > len(buffer):
            break

        length = buffer[pos + 2]
        if length < MIN_PAYLOAD:
            pos += 1
            continue

        end = pos + HEADER_SIZE + LENGTH_SIZE + length
        if end > len(buffer):
            # Partial packet at end of buffer
            break

        try:
            packet = parse_packet(buffer[pos:end])
            results.append((packet, end))
            pos = end
        except ValueError:
            # Invalid packet at this position, skip the header bytes
            pos += 1

    return results
