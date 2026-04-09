"""Tests for the transport layer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from makeblock_explorer.transport.base import (
    CH340_PID,
    CH340_VID,
    DeviceInfo,
    Transport,
    scan_serial_ports,
)
from makeblock_explorer.transport.serial import SerialTransport
from makeblock_explorer.transport.wifi import WiFiTransport


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify that concrete transports satisfy the Transport protocol."""

    def test_serial_transport_implements_protocol(self) -> None:
        transport = SerialTransport()
        assert isinstance(transport, Transport)

    def test_wifi_transport_implements_protocol(self) -> None:
        transport = WiFiTransport()
        assert isinstance(transport, Transport)


# ---------------------------------------------------------------------------
# scan_serial_ports
# ---------------------------------------------------------------------------


class TestScanSerialPorts:
    """Tests for scan_serial_ports using mocked comports."""

    def _make_port(
        self,
        device: str = "COM4",
        description: str = "USB-SERIAL CH340",
        vid: int | None = CH340_VID,
        pid: int | None = CH340_PID,
        serial_number: str | None = "12345",
    ) -> MagicMock:
        port = MagicMock()
        port.device = device
        port.description = description
        port.vid = vid
        port.pid = pid
        port.serial_number = serial_number
        return port

    @patch("serial.tools.list_ports.comports")
    def test_finds_ch340_by_vid_pid(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [self._make_port()]
        devices = scan_serial_ports()
        assert len(devices) == 1
        assert devices[0].port == "COM4"
        assert devices[0].vid == CH340_VID
        assert devices[0].pid == CH340_PID

    @patch("serial.tools.list_ports.comports")
    def test_finds_device_by_description_ch340(self, mock_comports: MagicMock) -> None:
        port = self._make_port(vid=None, pid=None, description="Some CH340 Bridge")
        mock_comports.return_value = [port]
        devices = scan_serial_ports()
        assert len(devices) == 1

    @patch("serial.tools.list_ports.comports")
    def test_finds_device_by_description_makeblock(self, mock_comports: MagicMock) -> None:
        port = self._make_port(vid=None, pid=None, description="Makeblock CyberPi")
        mock_comports.return_value = [port]
        devices = scan_serial_ports()
        assert len(devices) == 1

    @patch("serial.tools.list_ports.comports")
    def test_ignores_unrelated_ports(self, mock_comports: MagicMock) -> None:
        port = self._make_port(vid=0x1234, pid=0x5678, description="Arduino Uno")
        mock_comports.return_value = [port]
        devices = scan_serial_ports()
        assert len(devices) == 0

    @patch("serial.tools.list_ports.comports")
    def test_returns_empty_when_no_ports(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = []
        devices = scan_serial_ports()
        assert devices == []

    @patch("serial.tools.list_ports.comports")
    def test_returns_device_info_dataclass(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [self._make_port(serial_number="ABC123")]
        devices = scan_serial_ports()
        assert isinstance(devices[0], DeviceInfo)
        assert devices[0].serial_number == "ABC123"


# ---------------------------------------------------------------------------
# SerialTransport (mocked serial.Serial)
# ---------------------------------------------------------------------------


class TestSerialTransport:
    """Tests for SerialTransport with mocked pyserial."""

    def test_starts_disconnected(self) -> None:
        transport = SerialTransport()
        assert not transport.is_connected

    @patch("makeblock_explorer.transport.serial.serial.Serial")
    def test_connect_opens_port(self, mock_serial_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_serial_cls.return_value = mock_instance

        transport = SerialTransport()
        transport.connect("COM4")

        assert transport.is_connected
        mock_serial_cls.assert_called_once()

    @patch("makeblock_explorer.transport.serial.serial.Serial")
    def test_disconnect_closes_port(self, mock_serial_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_serial_cls.return_value = mock_instance

        transport = SerialTransport()
        transport.connect("COM4")
        transport.disconnect()

        assert not transport.is_connected
        mock_instance.close.assert_called_once()

    @patch("makeblock_explorer.transport.serial.serial.Serial")
    def test_send_writes_and_flushes(self, mock_serial_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_serial_cls.return_value = mock_instance

        transport = SerialTransport()
        transport.connect("COM4")
        transport.send(b"\xff\x55\x00")

        mock_instance.write.assert_called_once_with(b"\xff\x55\x00")
        mock_instance.flush.assert_called_once()

    def test_send_raises_when_not_connected(self) -> None:
        transport = SerialTransport()
        with pytest.raises(ConnectionError, match="Not connected"):
            transport.send(b"\xff")

    def test_receive_raises_when_not_connected(self) -> None:
        transport = SerialTransport()
        with pytest.raises(ConnectionError, match="Not connected"):
            transport.receive()

    @patch("makeblock_explorer.transport.serial.serial.Serial")
    def test_receive_returns_bytes(self, mock_serial_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_instance.read.return_value = b"\xff"
        mock_instance.in_waiting = 3
        mock_instance.timeout = 1.0
        mock_serial_cls.return_value = mock_instance

        # Make the second read call return the remaining bytes
        mock_instance.read.side_effect = [b"\xff", b"\x55\x00\x01"]

        transport = SerialTransport()
        transport.connect("COM4")
        result = transport.receive(timeout=0.5)

        assert result == b"\xff\x55\x00\x01"

    @patch("makeblock_explorer.transport.serial.serial.Serial")
    def test_receive_returns_empty_on_timeout(self, mock_serial_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_instance.read.return_value = b""
        mock_instance.timeout = 1.0
        mock_serial_cls.return_value = mock_instance

        transport = SerialTransport()
        transport.connect("COM4")
        result = transport.receive(timeout=0.1)

        assert result == b""

    @patch("makeblock_explorer.transport.serial.serial.Serial")
    def test_connect_disconnects_existing(self, mock_serial_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_serial_cls.return_value = mock_instance

        transport = SerialTransport()
        transport.connect("COM4")
        transport.connect("COM5")

        # First connection should have been closed
        mock_instance.close.assert_called_once()


# ---------------------------------------------------------------------------
# WiFiTransport (stub verification)
# ---------------------------------------------------------------------------


class TestWiFiTransport:
    """Tests for WiFiTransport stub."""

    def test_starts_disconnected(self) -> None:
        transport = WiFiTransport()
        assert not transport.is_connected

    def test_connect_raises_not_implemented(self) -> None:
        transport = WiFiTransport()
        with pytest.raises(NotImplementedError, match="WiFi transport not yet implemented"):
            transport.connect("192.168.1.100")

    def test_disconnect_raises_not_implemented(self) -> None:
        transport = WiFiTransport()
        with pytest.raises(NotImplementedError):
            transport.disconnect()

    def test_send_raises_not_implemented(self) -> None:
        transport = WiFiTransport()
        with pytest.raises(NotImplementedError):
            transport.send(b"\xff")

    def test_receive_raises_not_implemented(self) -> None:
        transport = WiFiTransport()
        with pytest.raises(NotImplementedError):
            transport.receive()
