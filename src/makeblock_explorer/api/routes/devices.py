"""Device management routes: scan, connect, disconnect, status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from makeblock_explorer.device.registry import DeviceRegistry
from makeblock_explorer.api.models import (
    ConnectRequest,
    DisconnectRequest,
    DeviceInfoResponse,
    DeviceStatusResponse,
)

router = APIRouter()

_registry: DeviceRegistry | None = None


def init_router(registry: DeviceRegistry | None) -> None:
    """Inject the DeviceRegistry instance used by all device routes."""
    global _registry
    _registry = registry


def get_registry() -> DeviceRegistry:
    """Return the active registry, raising 503 if not initialised."""
    if _registry is None:
        raise HTTPException(status_code=503, detail="Registry not initialised")
    return _registry


@router.get("/api/devices")
async def scan_devices() -> dict:
    """Scan serial ports and return discovered MakeBlock devices."""
    registry = get_registry()
    discovered = await registry.scan()
    devices = [
        DeviceInfoResponse(
            port=d.port,
            description=d.description,
            vid=d.vid,
            pid=d.pid,
        )
        for d in discovered
    ]
    return {"devices": [d.model_dump() for d in devices]}


@router.post("/api/connect")
async def connect_device(req: ConnectRequest) -> dict:
    """Connect to a device on the given serial port."""
    registry = get_registry()
    try:
        manager = await registry.connect(req.port)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"device_id": manager.device_id, "port": manager.port}


@router.post("/api/disconnect")
async def disconnect_device(req: DisconnectRequest) -> dict:
    """Disconnect a device by its ID."""
    registry = get_registry()
    manager = registry.get(req.device_id)
    if manager is None:
        raise HTTPException(status_code=404, detail=f"Device '{req.device_id}' not found")
    await registry.disconnect(req.device_id)
    return {"status": "ok"}


@router.get("/api/status")
async def device_status() -> dict:
    """Return status of all connected devices."""
    registry = get_registry()
    managers = registry.list_connected()
    statuses = [
        DeviceStatusResponse(
            device_id=m.device_id or "",
            port=m.port or "",
            device_type=m.device_type,
            is_connected=m.is_connected,
            sensor_cache=m.sensor_cache,
        )
        for m in managers
    ]
    return {"devices": [s.model_dump() for s in statuses]}
