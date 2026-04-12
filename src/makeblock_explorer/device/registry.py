"""DeviceRegistry: manages the collection of connected MakeBlock devices."""

from __future__ import annotations

from makeblock_explorer.transport.base import DeviceInfo, scan_serial_ports

from .manager import DeviceManager


class DeviceRegistry:
    """Manages the lifecycle of multiple DeviceManager connections."""

    def __init__(self) -> None:
        self._devices: dict[str, DeviceManager] = {}

    async def scan(self) -> list[DeviceInfo]:
        """Scan serial ports for MakeBlock devices."""
        return scan_serial_ports()

    async def connect(self, port: str) -> DeviceManager:
        """Create a new DeviceManager, connect it, and store it by device_id."""
        manager = DeviceManager()
        await manager.connect(port)
        if manager.device_id is None:
            raise RuntimeError(f"DeviceManager did not set device_id after connecting to {port}")
        self._devices[manager.device_id] = manager
        return manager

    async def disconnect(self, device_id: str) -> None:
        """Disconnect and remove a device by its ID."""
        manager = self._devices.pop(device_id, None)
        if manager is not None:
            await manager.disconnect()

    async def disconnect_all(self) -> None:
        """Disconnect all managed devices (for server shutdown)."""
        device_ids = list(self._devices.keys())
        for device_id in device_ids:
            await self.disconnect(device_id)

    def get(self, device_id: str) -> DeviceManager | None:
        """Return the DeviceManager for the given ID, or None if not found."""
        return self._devices.get(device_id)

    def list_connected(self) -> list[DeviceManager]:
        """Return all currently managed DeviceManagers."""
        return list(self._devices.values())
