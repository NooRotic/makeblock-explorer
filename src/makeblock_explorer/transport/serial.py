"""Serial/USB transport for MakeBlock devices."""

from __future__ import annotations

import serial

from .base import DeviceInfo, Transport, scan_serial_ports

# MakeBlock serial parameters
BAUD_RATE = 115200
BYTE_SIZE = serial.EIGHTBITS
STOP_BITS = serial.STOPBITS_ONE
PARITY = serial.PARITY_NONE


class SerialTransport:
    """Serial/USB transport for MakeBlock devices.

    Communicates over a serial port (typically a CH340 USB-UART bridge)
    using pyserial. Handles connection lifecycle and raw byte I/O.
    """

    def __init__(self) -> None:
        self._serial: serial.Serial | None = None

    def connect(self, target: str) -> None:
        """Open serial connection.

        Args:
            target: COM port name (e.g., 'COM4' on Windows, '/dev/ttyUSB0' on Linux).

        Raises:
            serial.SerialException: If the port cannot be opened.
        """
        if self._serial is not None and self._serial.is_open:
            self.disconnect()

        self._serial = serial.Serial(
            port=target,
            baudrate=BAUD_RATE,
            bytesize=BYTE_SIZE,
            stopbits=STOP_BITS,
            parity=PARITY,
            timeout=1.0,
        )

    def disconnect(self) -> None:
        """Close the serial port."""
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def send(self, data: bytes) -> None:
        """Send bytes over serial.

        Args:
            data: Raw bytes to send.

        Raises:
            ConnectionError: If the transport is not connected.
            serial.SerialException: If the write fails.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected. Call connect() first.")
        assert self._serial is not None
        self._serial.write(data)
        self._serial.flush()

    def receive(self, timeout: float = 1.0) -> bytes:
        """Read all available bytes with timeout.

        Args:
            timeout: Maximum seconds to wait for data. Defaults to 1.0.

        Returns:
            Bytes read from the device, or empty bytes on timeout.

        Raises:
            ConnectionError: If the transport is not connected.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected. Call connect() first.")
        assert self._serial is not None

        original_timeout = self._serial.timeout
        self._serial.timeout = timeout

        try:
            # Read first byte (blocks up to timeout)
            first = self._serial.read(1)
            if not first:
                return b""

            # Read remaining available bytes without blocking
            waiting = self._serial.in_waiting
            if waiting > 0:
                rest = self._serial.read(waiting)
                return first + rest
            return first
        finally:
            self._serial.timeout = original_timeout

    @property
    def is_connected(self) -> bool:
        """Whether the serial port is open and connected."""
        return self._serial is not None and self._serial.is_open
