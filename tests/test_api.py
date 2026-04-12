"""Tests for the FastAPI web API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from makeblock_explorer.api.server import create_app
from makeblock_explorer.device.manager import DeviceManager
from makeblock_explorer.device.registry import DeviceRegistry
from makeblock_explorer.transport.base import DeviceInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_manager(
    device_id: str = "device-COM5",
    port: str = "COM5",
    device_type: str = "unknown",
    is_connected: bool = True,
    sensor_cache: dict | None = None,
) -> MagicMock:
    manager = MagicMock(spec=DeviceManager)
    manager.device_id = device_id
    manager.port = port
    manager.device_type = device_type
    manager.is_connected = is_connected
    manager.sensor_cache = sensor_cache or {}
    manager.execute = AsyncMock(return_value=None)
    manager.subscribe = MagicMock(return_value="sub-id-1")
    manager.unsubscribe = MagicMock()
    return manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_registry():
    registry = MagicMock(spec=DeviceRegistry)
    registry.scan = AsyncMock(
        return_value=[
            DeviceInfo(
                port="COM5",
                description="USB-SERIAL CH340",
                vid=0x1A86,
                pid=0x7523,
                serial_number=None,
            )
        ]
    )
    registry.list_connected = MagicMock(return_value=[])
    registry.disconnect_all = AsyncMock()
    return registry


@pytest.fixture
def app(mock_registry):
    return create_app(registry=mock_registry)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Device routes
# ---------------------------------------------------------------------------


class TestScanDevices:
    async def test_returns_discovered_devices(self, client, mock_registry):
        response = await client.get("/api/devices")
        assert response.status_code == 200
        body = response.json()
        assert "devices" in body
        assert len(body["devices"]) == 1
        device = body["devices"][0]
        assert device["port"] == "COM5"
        assert device["description"] == "USB-SERIAL CH340"
        assert device["vid"] == 0x1A86
        assert device["pid"] == 0x7523

    async def test_calls_registry_scan(self, client, mock_registry):
        await client.get("/api/devices")
        mock_registry.scan.assert_awaited_once()


class TestConnect:
    async def test_connect_success(self, client, mock_registry):
        manager = _make_mock_manager()
        mock_registry.connect = AsyncMock(return_value=manager)

        response = await client.post("/api/connect", json={"port": "COM5"})
        assert response.status_code == 200
        body = response.json()
        assert body["device_id"] == "device-COM5"
        assert body["port"] == "COM5"

    async def test_connect_failure_returns_500(self, client, mock_registry):
        mock_registry.connect = AsyncMock(side_effect=RuntimeError("Port busy"))

        response = await client.post("/api/connect", json={"port": "COM5"})
        assert response.status_code == 500
        assert "Port busy" in response.json()["detail"]


class TestDisconnect:
    async def test_disconnect_known_device(self, client, mock_registry):
        manager = _make_mock_manager()
        mock_registry.get = MagicMock(return_value=manager)
        mock_registry.disconnect = AsyncMock()

        response = await client.post(
            "/api/disconnect", json={"device_id": "device-COM5"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_registry.disconnect.assert_awaited_once_with("device-COM5")

    async def test_disconnect_unknown_device_returns_404(self, client, mock_registry):
        mock_registry.get = MagicMock(return_value=None)

        response = await client.post(
            "/api/disconnect", json={"device_id": "device-UNKNOWN"}
        )
        assert response.status_code == 404


class TestDeviceStatus:
    async def test_empty_when_no_devices(self, client, mock_registry):
        mock_registry.list_connected = MagicMock(return_value=[])

        response = await client.get("/api/status")
        assert response.status_code == 200
        assert response.json() == {"devices": []}

    async def test_returns_connected_device_info(self, client, mock_registry):
        manager = _make_mock_manager(
            sensor_cache={"battery": 85, "brightness": 120}
        )
        mock_registry.list_connected = MagicMock(return_value=[manager])

        response = await client.get("/api/status")
        assert response.status_code == 200
        devices = response.json()["devices"]
        assert len(devices) == 1
        d = devices[0]
        assert d["device_id"] == "device-COM5"
        assert d["port"] == "COM5"
        assert d["is_connected"] is True
        assert d["sensor_cache"]["battery"] == 85


# ---------------------------------------------------------------------------
# Command routes
# ---------------------------------------------------------------------------


class TestExecuteCommand:
    async def test_execute_returns_value(self, client, mock_registry):
        manager = _make_mock_manager()
        response_obj = MagicMock()
        response_obj.value = 42.0
        manager.execute = AsyncMock(return_value=response_obj)
        mock_registry.get = MagicMock(return_value=manager)

        response = await client.post(
            "/api/command",
            json={"device_id": "device-COM5", "script": "cyberpi.get_bri()"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["value"] == 42.0
        assert body["error"] is None

    async def test_execute_none_response(self, client, mock_registry):
        manager = _make_mock_manager()
        manager.execute = AsyncMock(return_value=None)
        mock_registry.get = MagicMock(return_value=manager)

        response = await client.post(
            "/api/command",
            json={"device_id": "device-COM5", "script": "cyberpi.get_bri()"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["value"] is None
        assert body["error"] is None

    async def test_execute_exception_returns_error(self, client, mock_registry):
        manager = _make_mock_manager()
        manager.execute = AsyncMock(side_effect=ConnectionError("Not connected"))
        mock_registry.get = MagicMock(return_value=manager)

        response = await client.post(
            "/api/command",
            json={"device_id": "device-COM5", "script": "cyberpi.get_bri()"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["value"] is None
        assert "Not connected" in body["error"]

    async def test_device_not_found_returns_404(self, client, mock_registry):
        mock_registry.get = MagicMock(return_value=None)

        response = await client.post(
            "/api/command",
            json={"device_id": "device-MISSING", "script": "cyberpi.get_bri()"},
        )
        assert response.status_code == 404


class TestLed:
    async def test_set_led_no_id(self, client, mock_registry):
        manager = _make_mock_manager()
        mock_registry.get = MagicMock(return_value=manager)

        response = await client.post(
            "/api/led",
            json={"device_id": "device-COM5", "red": 255, "green": 0, "blue": 128},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        call_args = manager.execute.call_args
        assert "cyberpi.led.on(255,0,128)" in call_args[0][0]

    async def test_set_led_with_id(self, client, mock_registry):
        manager = _make_mock_manager()
        mock_registry.get = MagicMock(return_value=manager)

        response = await client.post(
            "/api/led",
            json={
                "device_id": "device-COM5",
                "red": 0,
                "green": 255,
                "blue": 0,
                "led_id": 3,
            },
        )
        assert response.status_code == 200
        call_args = manager.execute.call_args
        assert "cyberpi.led.on(0,255,0,3)" in call_args[0][0]

    async def test_led_device_not_found(self, client, mock_registry):
        mock_registry.get = MagicMock(return_value=None)

        response = await client.post(
            "/api/led",
            json={"device_id": "device-MISSING", "red": 0, "green": 0, "blue": 0},
        )
        assert response.status_code == 404

    async def test_led_invalid_value(self, client, mock_registry):
        response = await client.post(
            "/api/led",
            json={"device_id": "device-COM5", "red": 300, "green": 0, "blue": 0},
        )
        assert response.status_code == 422


class TestNotify:
    async def test_notify_returns_ok(self, client, mock_registry):
        manager = _make_mock_manager()
        mock_registry.get = MagicMock(return_value=manager)

        response = await client.post(
            "/api/notify",
            json={
                "device_id": "device-COM5",
                "text": "Hello",
                "flash_leds": False,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["device_id"] == "device-COM5"

    async def test_notify_calls_display_commands(self, client, mock_registry):
        manager = _make_mock_manager()
        mock_registry.get = MagicMock(return_value=manager)

        await client.post(
            "/api/notify",
            json={
                "device_id": "device-COM5",
                "text": "Hi",
                "flash_leds": False,
            },
        )
        calls = [c[0][0] for c in manager.execute.call_args_list]
        assert any("display.clear()" in c for c in calls)
        assert any("display.set_brush" in c for c in calls)
        assert any("display.show_label" in c for c in calls)

    async def test_notify_with_flash_leds(self, client, mock_registry):
        manager = _make_mock_manager()
        mock_registry.get = MagicMock(return_value=manager)

        response = await client.post(
            "/api/notify",
            json={
                "device_id": "device-COM5",
                "text": "Alert",
                "flash_leds": True,
            },
        )
        assert response.status_code == 200
        calls = [c[0][0] for c in manager.execute.call_args_list]
        led_on_calls = [c for c in calls if "led.on" in c]
        led_off_calls = [c for c in calls if "led.off" in c]
        assert len(led_on_calls) == 3
        assert len(led_off_calls) == 3

    async def test_notify_device_not_found(self, client, mock_registry):
        mock_registry.get = MagicMock(return_value=None)

        response = await client.post(
            "/api/notify",
            json={"device_id": "device-MISSING", "text": "Hi"},
        )
        assert response.status_code == 404

    async def test_notify_text_too_long(self, client, mock_registry):
        response = await client.post(
            "/api/notify",
            json={"device_id": "device-COM5", "text": "X" * 31},
        )
        assert response.status_code == 422


class TestSensorsCached:
    async def test_returns_sensor_cache(self, client, mock_registry):
        manager = _make_mock_manager(
            sensor_cache={"battery": 90, "brightness": 50, "pitch": 3.14}
        )
        mock_registry.get = MagicMock(return_value=manager)

        response = await client.get("/api/sensors/device-COM5")
        assert response.status_code == 200
        body = response.json()
        assert body["battery"] == 90
        assert body["brightness"] == 50

    async def test_empty_cache(self, client, mock_registry):
        manager = _make_mock_manager(sensor_cache={})
        mock_registry.get = MagicMock(return_value=manager)

        response = await client.get("/api/sensors/device-COM5")
        assert response.status_code == 200
        assert response.json() == {}

    async def test_device_not_found_returns_404(self, client, mock_registry):
        mock_registry.get = MagicMock(return_value=None)

        response = await client.get("/api/sensors/device-MISSING")
        assert response.status_code == 404
