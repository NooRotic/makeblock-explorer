"""FF55 protocol data type encoding and decoding.

Handles the type-prefixed value format used in FF55 packet payloads.
Each value is encoded as: [type_id][value_bytes]
"""

import struct
from enum import IntEnum


class DataType(IntEnum):
    """FF55 payload data type identifiers."""

    BYTE = 1
    FLOAT = 2
    SHORT = 3
    STRING = 4
    DOUBLE = 5


# Struct format strings for fixed-size types (little-endian)
_TYPE_FORMATS: dict[DataType, str] = {
    DataType.BYTE: "<B",
    DataType.FLOAT: "<f",
    DataType.SHORT: "<h",
    DataType.DOUBLE: "<d",
}

# Size in bytes for fixed-size types
_TYPE_SIZES: dict[DataType, int] = {
    DataType.BYTE: 1,
    DataType.FLOAT: 4,
    DataType.SHORT: 2,
    DataType.DOUBLE: 8,
}


def encode_value(data_type: DataType, value) -> bytes:
    """Encode a typed value into FF55 payload bytes (type prefix + value).

    Args:
        data_type: The FF55 data type to encode as.
        value: The value to encode. Must be compatible with the data type:
            - BYTE: int (0-255)
            - FLOAT: float (32-bit)
            - SHORT: int (signed 16-bit)
            - STRING: str or bytes
            - DOUBLE: float (64-bit)

    Returns:
        Bytes with type prefix followed by the encoded value.

    Raises:
        ValueError: If the data type is unknown.
    """
    type_byte = bytes([int(data_type)])

    if data_type == DataType.STRING:
        if isinstance(value, str):
            value = value.encode("utf-8")
        # String format: 2-byte LE length prefix + string bytes
        length = len(value)
        return type_byte + struct.pack("<H", length) + value

    if data_type in _TYPE_FORMATS:
        return type_byte + struct.pack(_TYPE_FORMATS[data_type], value)

    raise ValueError(f"Unknown data type: {data_type}")


def decode_value(data: bytes, offset: int = 0) -> tuple[any, int]:
    """Decode a typed value from bytes at offset.

    Reads the type prefix byte, then decodes the value according to its type.

    Args:
        data: The byte buffer to decode from.
        offset: Starting position in the buffer.

    Returns:
        A tuple of (decoded_value, total_bytes_consumed) where bytes_consumed
        includes the type prefix byte.

    Raises:
        ValueError: If the type ID is unknown or data is truncated.
    """
    if offset >= len(data):
        raise ValueError(f"Offset {offset} is beyond data length {len(data)}")

    type_id = data[offset]
    try:
        data_type = DataType(type_id)
    except ValueError:
        raise ValueError(f"Unknown type ID: {type_id}")

    offset += 1  # Skip type byte

    if data_type == DataType.STRING:
        if offset + 2 > len(data):
            raise ValueError("Truncated string length")
        (length,) = struct.unpack_from("<H", data, offset)
        offset += 2
        if offset + length > len(data):
            raise ValueError(
                f"Truncated string data: need {length} bytes, "
                f"have {len(data) - offset}"
            )
        value = data[offset : offset + length]
        return value.decode("utf-8"), 1 + 2 + length

    if data_type in _TYPE_FORMATS:
        fmt = _TYPE_FORMATS[data_type]
        size = _TYPE_SIZES[data_type]
        if offset + size > len(data):
            raise ValueError(
                f"Truncated {data_type.name} data: need {size} bytes, "
                f"have {len(data) - offset}"
            )
        (value,) = struct.unpack_from(fmt, data, offset)
        return value, 1 + size

    raise ValueError(f"Unknown data type: {data_type}")
