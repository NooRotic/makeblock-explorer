"""Command routes: script execution, LED, notify, sensors."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from makeblock_explorer.api.models import (
    CommandRequest,
    LedRequest,
    NotifyRequest,
)
from makeblock_explorer.api.routes.devices import get_registry

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_manager(device_id: str):
    """Look up a DeviceManager or raise 404."""
    registry = get_registry()
    manager = registry.get(device_id)
    if manager is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return manager


@router.post("/api/command")
async def execute_command(req: CommandRequest) -> dict:
    """Execute an arbitrary MicroPython script on the device."""
    manager = _get_manager(req.device_id)
    try:
        response = await manager.execute(req.script, expect_response=True, timeout=req.timeout)
    except Exception as exc:
        return {"value": None, "error": str(exc)}

    if response is None:
        return {"value": None, "error": None}
    return {"value": response.value, "error": None}


@router.get("/api/sensors/{device_id}")
async def get_sensors(device_id: str) -> dict:
    """Return the cached sensor readings for a device."""
    manager = _get_manager(device_id)
    return dict(manager.sensor_cache)


@router.post("/api/led")
async def set_led(req: LedRequest) -> dict:
    """Set LED colour on a device."""
    manager = _get_manager(req.device_id)
    r, g, b = req.red, req.green, req.blue

    if req.led_id is not None:
        script = f"cyberpi.led.on({r},{g},{b},{req.led_id})"
    else:
        script = f"cyberpi.led.on({r},{g},{b})"

    try:
        await manager.execute(script, expect_response=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "ok"}


@router.post("/api/notify")
async def push_notification(req: NotifyRequest) -> dict:
    """Display a notification on the device screen and optionally flash LEDs."""
    manager = _get_manager(req.device_id)

    r, g, b = req.color[0], req.color[1], req.color[2]

    # 1. Clear display (fire-and-forget)
    try:
        await manager.execute("cyberpi.display.clear()", expect_response=False)
    except Exception:
        logger.debug("display.clear() failed", exc_info=True)

    # 2. Set brush colour (fire-and-forget)
    try:
        await manager.execute(
            f"cyberpi.display.set_brush({r},{g},{b})", expect_response=False
        )
    except Exception:
        logger.debug("display.set_brush() failed", exc_info=True)

    # 3. Show label with auto-centring
    # CyberPi display is 128x64; estimate x so text is roughly centred.
    text = req.text
    size = req.size
    char_width_est = size * 0.6
    x = max(0, int((128 - len(text) * char_width_est) / 2))
    y = 20  # vertically centred-ish

    try:
        await manager.execute(
            f'cyberpi.display.show_label("{text}",{size},{x},{y})',
            expect_response=False,
        )
    except Exception:
        logger.debug("display.show_label() failed", exc_info=True)

    # 4. Flash LEDs (3 flashes: 500ms on, 300ms off)
    if req.flash_leds:
        for _ in range(3):
            try:
                await manager.execute(
                    f"cyberpi.led.on({r},{g},{b})", expect_response=False
                )
            except Exception:
                logger.debug("LED on failed", exc_info=True)
            await asyncio.sleep(0.5)
            try:
                await manager.execute("cyberpi.led.off()", expect_response=False)
            except Exception:
                logger.debug("LED off failed", exc_info=True)
            await asyncio.sleep(0.3)

    return {"status": "ok", "device_id": req.device_id}
