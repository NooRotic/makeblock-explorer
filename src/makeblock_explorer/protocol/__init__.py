"""Protocol engines for MakeBlock devices.

Implements two MakeBlock binary protocols:
- FF55: Legacy protocol for older MakeBlock boards.
    [0xFF][0x55][Length][Index][Action][Device][Data...]
- F3: Framed protocol for CyberPi and HaloCode devices.
    [0xF3][HeaderChecksum][DataLen_Lo][DataLen_Hi][Type][Mode][Idx_Lo][Idx_Hi][Data...][BodyChecksum][0xF4]
"""

from .capture import CaptureEntry, CaptureTransport, format_hex_dump, load_capture
from .f3 import (
    FOOTER,
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
from .f3 import HEADER as F3_HEADER
from .ff55 import HEADER, Action, Packet, build_packet, find_packets, parse_packet
from .types import DataType, decode_value, encode_value

__all__ = [
    # FF55 protocol
    "Action",
    "CaptureEntry",
    "CaptureTransport",
    "DataType",
    "HEADER",
    "Packet",
    "build_packet",
    "decode_value",
    "encode_value",
    "find_packets",
    "format_hex_dump",
    "load_capture",
    "parse_packet",
    # F3 protocol
    "F3_HEADER",
    "FOOTER",
    "F3Packet",
    "F3Response",
    "Mode",
    "OFFLINE_MODE_PACKET",
    "ONLINE_MODE_PACKET",
    "PacketType",
    "build_f3_packet",
    "find_f3_frames",
    "parse_f3_response",
]
