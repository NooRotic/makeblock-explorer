"""Tests for the device registry loader."""

from pathlib import Path

import pytest

from makeblock_explorer.registry import DeviceProfile, DeviceRegistry


DEVICES_DIR = Path(__file__).resolve().parent.parent / "src" / "makeblock_explorer" / "devices"


class TestLoadCyberPi:
    """Tests for loading the CyberPi device profile."""

    def test_load_cyberpi_name(self) -> None:
        registry = DeviceRegistry()
        profile = registry.load_file(DEVICES_DIR / "cyberpi.yaml")
        assert profile.name == "CyberPi"

    def test_load_cyberpi_chip(self) -> None:
        registry = DeviceRegistry()
        profile = registry.load_file(DEVICES_DIR / "cyberpi.yaml")
        assert profile.chip == "ESP32-WROVER-B"

    def test_load_cyberpi_sensor_count(self) -> None:
        registry = DeviceRegistry()
        profile = registry.load_file(DEVICES_DIR / "cyberpi.yaml")
        assert len(profile.sensors) == 7

    def test_load_cyberpi_actuator_count(self) -> None:
        registry = DeviceRegistry()
        profile = registry.load_file(DEVICES_DIR / "cyberpi.yaml")
        assert len(profile.actuators) == 3


class TestLoadHaloCode:
    """Tests for loading the HaloCode device profile."""

    def test_load_halocode_name(self) -> None:
        registry = DeviceRegistry()
        profile = registry.load_file(DEVICES_DIR / "halocode.yaml")
        assert profile.name == "HaloCode"

    def test_load_halocode_chip(self) -> None:
        registry = DeviceRegistry()
        profile = registry.load_file(DEVICES_DIR / "halocode.yaml")
        assert profile.chip == "ESP32"

    def test_load_halocode_sensor_count(self) -> None:
        registry = DeviceRegistry()
        profile = registry.load_file(DEVICES_DIR / "halocode.yaml")
        assert len(profile.sensors) == 4

    def test_load_halocode_actuator_count(self) -> None:
        registry = DeviceRegistry()
        profile = registry.load_file(DEVICES_DIR / "halocode.yaml")
        assert len(profile.actuators) == 1


class TestDeviceRegistry:
    """Tests for the DeviceRegistry class."""

    def test_find_by_device_id_returns_both_devices(self) -> None:
        registry = DeviceRegistry.default()
        results = registry.find_by_device_id(0x08)
        device_names = {r[0] for r in results}
        assert "CyberPi" in device_names
        assert "HaloCode" in device_names
        # Both should be actuators
        assert all(r[1] == "actuator" for r in results)

    def test_get_case_insensitive(self) -> None:
        registry = DeviceRegistry.default()
        assert registry.get("cyberpi") is not None
        assert registry.get("CyberPi") is not None
        assert registry.get("CYBERPI") is not None
        assert registry.get("cyberpi").name == "CyberPi"

    def test_get_nonexistent_returns_none(self) -> None:
        registry = DeviceRegistry.default()
        assert registry.get("nonexistent") is None

    def test_list_devices(self) -> None:
        registry = DeviceRegistry.default()
        devices = registry.list_devices()
        assert "CyberPi" in devices
        assert "HaloCode" in devices
        assert len(devices) == 2

    def test_invalid_yaml_raises_value_error(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{{{invalid yaml content")
        registry = DeviceRegistry()
        with pytest.raises(ValueError, match="Invalid YAML"):
            registry.load_file(bad_file)

    def test_missing_file_raises_file_not_found(self) -> None:
        registry = DeviceRegistry()
        with pytest.raises(FileNotFoundError):
            registry.load_file(Path("/nonexistent/device.yaml"))

    def test_default_loads_all_profiles(self) -> None:
        registry = DeviceRegistry.default()
        assert len(registry.list_devices()) >= 2
