"""WebSocket sensor streaming route."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from makeblock_explorer.api.routes.devices import get_registry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/api/stream")
async def stream_sensors(websocket: WebSocket) -> None:
    """Stream sensor data to WebSocket clients.

    Client sends:
        {"type": "subscribe", "device_id": "device-COM5"}   # specific device
        {"type": "subscribe", "device_id": "all"}           # all devices

    Server sends:
        {"type": "sensor", "device_id": "...", "data": {...}}
    """
    await websocket.accept()

    queue: asyncio.Queue[dict] = asyncio.Queue()
    subscriptions: dict[str, str] = {}  # device_id -> sub_id
    subscribed_all = False

    def _make_callback(device_id: str):
        def callback(data: dict) -> None:
            queue.put_nowait({"type": "sensor", "device_id": device_id, "data": data})

        return callback

    async def receive_loop() -> None:
        nonlocal subscribed_all
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("Invalid JSON from WebSocket client: %s", raw)
                    continue

                if msg.get("type") != "subscribe":
                    continue

                device_id = msg.get("device_id", "")
                registry = get_registry()

                if device_id == "all":
                    subscribed_all = True
                    for manager in registry.list_connected():
                        mid = manager.device_id
                        if mid and mid not in subscriptions:
                            sub_id = manager.subscribe(_make_callback(mid))
                            subscriptions[mid] = sub_id
                else:
                    manager = registry.get(device_id)
                    if manager is not None and device_id not in subscriptions:
                        sub_id = manager.subscribe(_make_callback(device_id))
                        subscriptions[device_id] = sub_id
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.debug("WebSocket receive_loop error", exc_info=True)

    async def send_loop() -> None:
        try:
            while True:
                payload = await queue.get()
                await websocket.send_text(json.dumps(payload))
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.debug("WebSocket send_loop error", exc_info=True)

    receive_task = asyncio.create_task(receive_loop())
    send_task = asyncio.create_task(send_loop())

    try:
        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        # Clean up subscriptions
        try:
            registry = get_registry()
            for device_id, sub_id in subscriptions.items():
                manager = registry.get(device_id)
                if manager is not None:
                    manager.unsubscribe(sub_id)
        except Exception:
            logger.debug("Cleanup error", exc_info=True)

        for task in [receive_task, send_task]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
