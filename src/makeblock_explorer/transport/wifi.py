"""WiFi transport for MakeBlock devices (future implementation)."""

from __future__ import annotations


class WiFiTransport:
    """WiFi transport for MakeBlock devices.

    Placeholder for future implementation. Will support:
    - UDP broadcast for device discovery
    - TCP socket for command/response
    - ESP-NOW integration
    """

    def __init__(self) -> None:
        self._connected: bool = False

    def connect(self, target: str) -> None:
        """Open WiFi connection to target IP address.

        Args:
            target: IP address or hostname of the device.

        Raises:
            NotImplementedError: WiFi transport is not yet implemented.
        """
        raise NotImplementedError("WiFi transport not yet implemented")

    def disconnect(self) -> None:
        """Close the WiFi connection.

        Raises:
            NotImplementedError: WiFi transport is not yet implemented.
        """
        raise NotImplementedError("WiFi transport not yet implemented")

    def send(self, data: bytes) -> None:
        """Send raw bytes over WiFi.

        Args:
            data: Raw bytes to send.

        Raises:
            NotImplementedError: WiFi transport is not yet implemented.
        """
        raise NotImplementedError("WiFi transport not yet implemented")

    def receive(self, timeout: float = 1.0) -> bytes:
        """Receive bytes over WiFi.

        Args:
            timeout: Maximum seconds to wait for data.

        Returns:
            Bytes received from the device.

        Raises:
            NotImplementedError: WiFi transport is not yet implemented.
        """
        raise NotImplementedError("WiFi transport not yet implemented")

    @property
    def is_connected(self) -> bool:
        """Whether the WiFi transport has an active connection."""
        return self._connected
