"""Base transport abstractions for MakeBlock device communication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class DeviceInfo:
    """Discovered MakeBlock device."""

    port: str  # e.g., "COM4" or "/dev/ttyUSB0"
    description: str  # Human-readable device name
    vid: int | None  # USB Vendor ID
    pid: int | None  # USB Product ID
    serial_number: str | None


@runtime_checkable
class Transport(Protocol):
    """Abstract transport interface for MakeBlock device communication.

    Uses structural subtyping (Protocol) so implementations don't need to
    explicitly inherit -- they just need to implement the required methods.
    """

    def connect(self, target: str) -> None:
        """Open connection to target (e.g., COM port or IP address)."""
        ...

    def disconnect(self) -> None:
        """Close the connection."""
        ...

    def send(self, data: bytes) -> None:
        """Send raw bytes to the device."""
        ...

    def receive(self, timeout: float = 1.0) -> bytes:
        """Receive bytes from the device. Returns empty bytes on timeout."""
        ...

    @property
    def is_connected(self) -> bool:
        """Whether the transport has an active connection."""
        ...


# CH340 USB-UART bridge identifiers (used by MakeBlock devices)
CH340_VID = 0x1A86
CH340_PID = 0x7523


def scan_serial_ports() -> list[DeviceInfo]:
    """Scan for MakeBlock devices on serial ports.

    Looks for CH340 USB-UART bridges (VID: 0x1A86, PID: 0x7523) which are
    used by MakeBlock CyberPi and other MakeBlock devices. Also matches
    devices with 'CH340' or 'Makeblock' in their description as a fallback.

    Returns:
        List of DeviceInfo for each discovered MakeBlock-compatible device.
    """
    import serial.tools.list_ports

    devices: list[DeviceInfo] = []

    for port_info in serial.tools.list_ports.comports():
        vid = port_info.vid
        pid = port_info.pid
        desc = port_info.description or ""

        # Match by VID/PID (primary) or description keywords (fallback)
        vid_pid_match = vid == CH340_VID and pid == CH340_PID
        desc_match = "ch340" in desc.lower() or "makeblock" in desc.lower()

        if vid_pid_match or desc_match:
            devices.append(
                DeviceInfo(
                    port=port_info.device,
                    description=desc,
                    vid=vid,
                    pid=pid,
                    serial_number=port_info.serial_number,
                )
            )

    return devices
