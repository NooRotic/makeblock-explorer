"""Tests for DeviceManager and DeviceRegistry."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from makeblock_explorer.device.manager import DeviceManager
from makeblock_explorer.device.registry import DeviceRegistry
from makeblock_explorer.protocol.f3 import HEADER, FOOTER, build_f3_packet, Mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_serial() -> MagicMock:
    """Return a MagicMock that behaves like an open serial.Serial instance."""
    mock = MagicMock()
    mock.is_open = True
    mock.in_waiting = 0
    mock.read.return_value = b""
    return mock


def _build_response_frame(index: int, value: object) -> bytes:
    """Build a minimal valid F3 response frame containing {"ret": value}."""
    payload = json.dumps({"ret": value}).encode("utf-8")
    plen = len(payload)
    data = bytes([plen & 0xFF, (plen >> 8) & 0xFF]) + payload

    type_b = 0x28  # SCRIPT
    mode_b = 0x01  # WITH_RESPONSE
    idx_lo = index & 0xFF
    idx_hi = (index >> 8) & 0xFF

    datalen = 4 + len(data)  # type + mode + idx_lo + idx_hi + data
    datalen_lo = datalen & 0xFF
    datalen_hi = (datalen >> 8) & 0xFF
    header_chk = (0xF3 + datalen_lo + datalen_hi) & 0xFF
    body_chk = (type_b + mode_b + idx_lo + idx_hi + sum(data)) & 0xFF

    return (
        bytes([HEADER, header_chk, datalen_lo, datalen_hi, type_b, mode_b, idx_lo, idx_hi])
        + data
        + bytes([body_chk, FOOTER])
    )


# ---------------------------------------------------------------------------
# DeviceManager — initial state
# ---------------------------------------------------------------------------


class TestDeviceManagerInitialState:
    def test_not_connected(self) -> None:
        dm = DeviceManager()
        assert dm.is_connected is False

    def test_device_id_none(self) -> None:
        dm = DeviceManager()
        assert dm.device_id is None

    def test_port_none(self) -> None:
        dm = DeviceManager()
        assert dm.port is None

    def test_sensor_cache_empty(self) -> None:
        dm = DeviceManager()
        assert dm.sensor_cache == {}

    def test_device_type_default(self) -> None:
        dm = DeviceManager()
        assert dm.device_type == "unknown"


# ---------------------------------------------------------------------------
# DeviceManager — _make_device_id
# ---------------------------------------------------------------------------


class TestMakeDeviceId:
    def test_com5(self) -> None:
        dm = DeviceManager()
        assert dm._make_device_id("COM5") == "device-COM5"

    def test_tty(self) -> None:
        dm = DeviceManager()
        assert dm._make_device_id("/dev/ttyUSB0") == "device-/dev/ttyUSB0"


# ---------------------------------------------------------------------------
# DeviceManager — _next_index
# ---------------------------------------------------------------------------


class TestNextIndex:
    def test_starts_at_zero(self) -> None:
        dm = DeviceManager()
        assert dm._next_index() == 0

    def test_increments(self) -> None:
        dm = DeviceManager()
        dm._next_index()
        assert dm._next_index() == 1

    def test_wraps_at_0xffff(self) -> None:
        dm = DeviceManager()
        dm._index = 0xFFFE
        assert dm._next_index() == 0xFFFE
        assert dm._next_index() == 0  # wrapped


# ---------------------------------------------------------------------------
# DeviceManager — connect()
# ---------------------------------------------------------------------------


class TestConnect:
    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_opens_serial_with_correct_params(self, mock_serial_cls: MagicMock) -> None:
        mock_serial = _make_mock_serial()
        mock_serial_cls.return_value = mock_serial

        dm = DeviceManager()

        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        mock_serial_cls.assert_called_once_with(
            port="COM5",
            baudrate=115200,
            bytesize=8,
            stopbits=1,
            parity="N",
            timeout=1.0,
        )

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_sets_port_and_device_id(self, mock_serial_cls: MagicMock) -> None:
        mock_serial_cls.return_value = _make_mock_serial()

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        assert dm.port == "COM5"
        assert dm.device_id == "device-COM5"

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_is_connected_after_connect(self, mock_serial_cls: MagicMock) -> None:
        mock_serial_cls.return_value = _make_mock_serial()

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        assert dm.is_connected is True


# ---------------------------------------------------------------------------
# DeviceManager — disconnect()
# ---------------------------------------------------------------------------


class TestDisconnect:
    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_closes_serial(self, mock_serial_cls: MagicMock) -> None:
        mock_serial = _make_mock_serial()
        mock_serial_cls.return_value = mock_serial

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        await dm.disconnect()

        mock_serial.close.assert_called_once()

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_clears_state(self, mock_serial_cls: MagicMock) -> None:
        mock_serial_cls.return_value = _make_mock_serial()

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        await dm.disconnect()

        assert dm.port is None
        assert dm.device_id is None
        assert dm.sensor_cache == {}

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_not_connected_after_disconnect(self, mock_serial_cls: MagicMock) -> None:
        mock_serial = _make_mock_serial()
        mock_serial_cls.return_value = mock_serial

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        # After disconnect the serial is gone, so is_connected must be False
        await dm.disconnect()
        assert dm.is_connected is False


# ---------------------------------------------------------------------------
# DeviceManager — execute()
# ---------------------------------------------------------------------------


class TestExecute:
    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_raises_when_not_connected(self, mock_serial_cls: MagicMock) -> None:
        dm = DeviceManager()
        with pytest.raises(ConnectionError):
            await dm.execute("cyberpi.get_bri()")

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_write_called_with_valid_f3_packet(self, mock_serial_cls: MagicMock) -> None:
        mock_serial = _make_mock_serial()
        mock_serial_cls.return_value = mock_serial

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        # Execute; no response bytes so returns None
        await dm.execute("cyberpi.get_bri()", expect_response=False)

        mock_serial.write.assert_called()
        written_packet: bytes = mock_serial.write.call_args[0][0]

        assert isinstance(written_packet, bytes)
        assert written_packet[0] == HEADER
        assert written_packet[-1] == FOOTER

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_packet_contains_script(self, mock_serial_cls: MagicMock) -> None:
        mock_serial = _make_mock_serial()
        mock_serial_cls.return_value = mock_serial

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        await dm.execute("cyberpi.get_bri()", expect_response=False)

        written_packet: bytes = mock_serial.write.call_args[0][0]
        assert b"cyberpi.get_bri()" in written_packet

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_returns_f3_response_when_bytes_available(self, mock_serial_cls: MagicMock) -> None:
        response_frame = _build_response_frame(index=1, value=42)

        mock_serial = _make_mock_serial()
        mock_serial.in_waiting = len(response_frame)
        mock_serial.read.return_value = response_frame
        mock_serial_cls.return_value = mock_serial

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")
        # Reset index counter so the execute() call gets index 0 (handshake used 0 and 1)
        dm._index = 1

        result = await dm.execute("cyberpi.get_bri()", expect_response=True)

        assert result is not None
        assert result.value == 42

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_returns_none_without_response(self, mock_serial_cls: MagicMock) -> None:
        mock_serial = _make_mock_serial()
        mock_serial_cls.return_value = mock_serial

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        result = await dm.execute("cyberpi.display_show('hi')", expect_response=False)
        assert result is None

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_with_response_mode_packet_uses_mode_01(self, mock_serial_cls: MagicMock) -> None:
        """Verify that expect_response=True builds a Mode.WITH_RESPONSE packet."""
        mock_serial = _make_mock_serial()
        mock_serial_cls.return_value = mock_serial

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        await dm.execute("cyberpi.get_bri()", expect_response=True)

        written_packet: bytes = mock_serial.write.call_args[0][0]
        # mode byte is at index 5 in F3 packet
        assert written_packet[5] == int(Mode.WITH_RESPONSE)

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_without_response_mode_packet_uses_mode_00(self, mock_serial_cls: MagicMock) -> None:
        """Verify that expect_response=False builds a Mode.WITHOUT_RESPONSE packet."""
        mock_serial = _make_mock_serial()
        mock_serial_cls.return_value = mock_serial

        dm = DeviceManager()
        with patch.object(dm, "_reset_device"), patch.object(dm, "_handshake"), patch.object(dm, "_identify_device"), patch.object(dm, "start_sensor_polling"):
            await dm.connect("COM5")

        await dm.execute("cyberpi.display_show('hi')", expect_response=False)

        written_packet: bytes = mock_serial.write.call_args[0][0]
        assert written_packet[5] == int(Mode.WITHOUT_RESPONSE)


# ---------------------------------------------------------------------------
# DeviceManager — subscribe / unsubscribe
# ---------------------------------------------------------------------------


class TestSubscriptions:
    def test_subscribe_returns_uuid_string(self) -> None:
        dm = DeviceManager()
        cb = MagicMock()
        sub_id = dm.subscribe(cb)
        assert isinstance(sub_id, str)
        assert len(sub_id) == 36  # UUID4 format

    def test_unsubscribe_removes_callback(self) -> None:
        dm = DeviceManager()
        cb = MagicMock()
        sub_id = dm.subscribe(cb)
        dm.unsubscribe(sub_id)
        assert sub_id not in dm._subscribers

    def test_unsubscribe_nonexistent_id_is_noop(self) -> None:
        dm = DeviceManager()
        dm.unsubscribe("nonexistent-id")  # should not raise


# ---------------------------------------------------------------------------
# DeviceRegistry
# ---------------------------------------------------------------------------


class TestDeviceRegistry:
    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_connect_creates_and_stores_manager(self, mock_serial_cls: MagicMock) -> None:
        mock_serial_cls.return_value = _make_mock_serial()

        registry = DeviceRegistry()
        with patch.object(DeviceManager, "_reset_device"), patch.object(DeviceManager, "_handshake"), patch.object(DeviceManager, "_identify_device"), patch.object(DeviceManager, "start_sensor_polling"):
            manager = await registry.connect("COM5")

        assert manager is not None
        assert manager.device_id == "device-COM5"
        assert registry.get("device-COM5") is manager

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_disconnect_removes_manager(self, mock_serial_cls: MagicMock) -> None:
        mock_serial_cls.return_value = _make_mock_serial()

        registry = DeviceRegistry()
        with patch.object(DeviceManager, "_reset_device"), patch.object(DeviceManager, "_handshake"), patch.object(DeviceManager, "_identify_device"), patch.object(DeviceManager, "start_sensor_polling"):
            manager = await registry.connect("COM5")

        await registry.disconnect("device-COM5")
        assert registry.get("device-COM5") is None

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_disconnect_calls_manager_disconnect(self, mock_serial_cls: MagicMock) -> None:
        mock_serial = _make_mock_serial()
        mock_serial_cls.return_value = mock_serial

        registry = DeviceRegistry()
        with patch.object(DeviceManager, "_reset_device"), patch.object(DeviceManager, "_handshake"), patch.object(DeviceManager, "_identify_device"), patch.object(DeviceManager, "start_sensor_polling"):
            await registry.connect("COM5")

        await registry.disconnect("device-COM5")
        mock_serial.close.assert_called_once()

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_get_returns_manager(self, mock_serial_cls: MagicMock) -> None:
        mock_serial_cls.return_value = _make_mock_serial()

        registry = DeviceRegistry()
        with patch.object(DeviceManager, "_reset_device"), patch.object(DeviceManager, "_handshake"), patch.object(DeviceManager, "_identify_device"), patch.object(DeviceManager, "start_sensor_polling"):
            manager = await registry.connect("COM5")

        assert registry.get("device-COM5") is manager

    def test_get_returns_none_for_unknown_id(self) -> None:
        registry = DeviceRegistry()
        assert registry.get("device-COM99") is None

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_list_connected(self, mock_serial_cls: MagicMock) -> None:
        mock_serial_cls.return_value = _make_mock_serial()

        registry = DeviceRegistry()
        with patch.object(DeviceManager, "_reset_device"), patch.object(DeviceManager, "_handshake"), patch.object(DeviceManager, "_identify_device"), patch.object(DeviceManager, "start_sensor_polling"):
            m1 = await registry.connect("COM5")

        connected = registry.list_connected()
        assert m1 in connected

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_disconnect_all(self, mock_serial_cls: MagicMock) -> None:
        mock_serial_cls.return_value = _make_mock_serial()

        registry = DeviceRegistry()
        with patch.object(DeviceManager, "_reset_device"), patch.object(DeviceManager, "_handshake"), patch.object(DeviceManager, "_identify_device"), patch.object(DeviceManager, "start_sensor_polling"):
            await registry.connect("COM5")

        await registry.disconnect_all()
        assert registry.list_connected() == []

    @patch("makeblock_explorer.device.manager.serial.Serial")
    async def test_disconnect_unknown_id_is_noop(self, mock_serial_cls: MagicMock) -> None:
        registry = DeviceRegistry()
        await registry.disconnect("device-UNKNOWN")  # should not raise

    @patch("serial.tools.list_ports.comports")
    async def test_scan_delegates_to_scan_serial_ports(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = []
        registry = DeviceRegistry()
        result = await registry.scan()
        assert result == []
