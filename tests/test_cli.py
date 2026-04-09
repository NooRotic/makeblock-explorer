"""Tests for the MakeBlock Explorer CLI."""

from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from makeblock_explorer.cli import main, do_scan, do_list_profiles, console
from makeblock_explorer.transport.base import DeviceInfo
from makeblock_explorer.registry import DeviceRegistry


def _make_device(port="COM4", desc="USB-SERIAL CH340", vid=0x1A86, pid=0x7523):
    """Helper to create a DeviceInfo for testing."""
    return DeviceInfo(
        port=port,
        description=desc,
        vid=vid,
        pid=pid,
        serial_number="1234",
    )


class TestScanCommand:
    """Tests for the 'mbx scan' CLI command."""

    @patch("makeblock_explorer.cli.scan_serial_ports")
    def test_scan_with_devices(self, mock_scan):
        """mbx scan shows a table when devices are found."""
        mock_scan.return_value = [_make_device()]
        runner = CliRunner()
        result = runner.invoke(main, ["scan"])
        assert result.exit_code == 0
        assert "COM4" in result.output
        assert "CH340" in result.output

    @patch("makeblock_explorer.cli.scan_serial_ports")
    def test_scan_no_devices(self, mock_scan):
        """mbx scan shows a helpful message when no devices found."""
        mock_scan.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, ["scan"])
        assert result.exit_code == 0
        assert "No MakeBlock devices found" in result.output


class TestExploreCommand:
    """Tests for the 'mbx explore' CLI command."""

    def test_explore_shows_profiles(self):
        """mbx explore COM4 shows device profiles."""
        runner = CliRunner()
        result = runner.invoke(main, ["explore", "COM4"])
        assert result.exit_code == 0
        # Should show at least the port being explored
        assert "COM4" in result.output


class TestHelpCommand:
    """Tests for the 'mbx --help' command."""

    def test_help_text(self):
        """mbx --help shows usage information."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "FF55 Protocol Explorer" in result.output
        assert "scan" in result.output
        assert "explore" in result.output
        assert "raw" in result.output


class TestDoScan:
    """Tests for the do_scan function directly."""

    @patch("makeblock_explorer.cli.scan_serial_ports")
    def test_do_scan_with_devices(self, mock_scan, capsys):
        """do_scan prints a Rich table with device info."""
        mock_scan.return_value = [
            _make_device("COM4", "USB-SERIAL CH340"),
            _make_device("COM5", "Makeblock Device", vid=None, pid=None),
        ]
        do_scan()
        # Rich outputs to its own console, so we check it didn't raise

    @patch("makeblock_explorer.cli.scan_serial_ports")
    def test_do_scan_empty(self, mock_scan, capsys):
        """do_scan shows no-device message when list is empty."""
        mock_scan.return_value = []
        do_scan()
        # Verify it ran without error (Rich console output)


class TestDoListProfiles:
    """Tests for the do_list_profiles function."""

    def test_list_profiles_shows_devices(self):
        """do_list_profiles outputs a table with known device names."""
        registry = DeviceRegistry.default()
        devices = registry.list_devices()
        # Should have at least one built-in profile
        assert len(devices) > 0
        # Should not raise
        do_list_profiles(registry)

    def test_list_profiles_empty_registry(self):
        """do_list_profiles handles empty registry gracefully."""
        registry = DeviceRegistry()
        do_list_profiles(registry)
        # Should not raise


class TestRawCommand:
    """Tests for the 'mbx raw' CLI command."""

    def test_raw_help(self):
        """mbx raw --help shows usage for raw packet command."""
        runner = CliRunner()
        result = runner.invoke(main, ["raw", "--help"])
        assert result.exit_code == 0
        assert "DEVICE_ID" in result.output
