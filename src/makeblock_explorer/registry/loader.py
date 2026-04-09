"""Device profile loader and registry for MakeBlock hardware."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Reading:
    """A single sensor reading definition."""

    name: str
    type: str  # byte, float, short, string, double
    unit: str


@dataclass
class SensorDef:
    """Sensor definition from device profile."""

    name: str
    device_id: int
    description: str
    readings: list[Reading]


@dataclass
class Parameter:
    """An actuator parameter definition."""

    name: str
    type: str
    description: str


@dataclass
class ActuatorDef:
    """Actuator definition from device profile."""

    name: str
    device_id: int
    description: str
    parameters: list[Parameter]


@dataclass
class DeviceProfile:
    """Complete device profile loaded from YAML."""

    name: str
    chip: str
    description: str
    transport: list[str]
    sensors: dict[str, SensorDef]
    actuators: dict[str, ActuatorDef]


def _parse_readings(raw: list[dict]) -> list[Reading]:
    """Parse raw reading dicts into Reading dataclasses."""
    return [Reading(name=r["name"], type=r["type"], unit=r["unit"]) for r in raw]


def _parse_parameters(raw: list[dict]) -> list[Parameter]:
    """Parse raw parameter dicts into Parameter dataclasses."""
    return [
        Parameter(name=p["name"], type=p["type"], description=p["description"])
        for p in raw
    ]


def _parse_device_id(value: int | str) -> int:
    """Parse a device_id that may be int (from YAML hex) or string."""
    if isinstance(value, int):
        return value
    return int(str(value), 0)


class DeviceRegistry:
    """Registry of known MakeBlock device profiles."""

    def __init__(self) -> None:
        self._profiles: dict[str, DeviceProfile] = {}

    def load_directory(self, path: Path) -> None:
        """Load all YAML device profiles from a directory."""
        if not path.is_dir():
            raise FileNotFoundError(f"Directory not found: {path}")
        for yaml_file in sorted(path.glob("*.yaml")):
            self.load_file(yaml_file)

    def load_file(self, path: Path) -> DeviceProfile:
        """Load a single YAML device profile."""
        if not path.exists():
            raise FileNotFoundError(f"Device profile not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid YAML in {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Invalid device profile format in {path}")

        # Parse sensors
        sensors: dict[str, SensorDef] = {}
        for sensor_name, sensor_data in (data.get("sensors") or {}).items():
            sensors[sensor_name] = SensorDef(
                name=sensor_name,
                device_id=_parse_device_id(sensor_data["device_id"]),
                description=sensor_data["description"],
                readings=_parse_readings(sensor_data.get("readings", [])),
            )

        # Parse actuators
        actuators: dict[str, ActuatorDef] = {}
        for act_name, act_data in (data.get("actuators") or {}).items():
            actuators[act_name] = ActuatorDef(
                name=act_name,
                device_id=_parse_device_id(act_data["device_id"]),
                description=act_data["description"],
                parameters=_parse_parameters(act_data.get("parameters", [])),
            )

        profile = DeviceProfile(
            name=data["name"],
            chip=data["chip"],
            description=data["description"],
            transport=data.get("transport", []),
            sensors=sensors,
            actuators=actuators,
        )

        self._profiles[profile.name.lower()] = profile
        return profile

    def get(self, name: str) -> DeviceProfile | None:
        """Get a device profile by name (case-insensitive)."""
        return self._profiles.get(name.lower())

    def list_devices(self) -> list[str]:
        """List all registered device names."""
        return [p.name for p in self._profiles.values()]

    def find_by_device_id(self, device_id: int) -> list[tuple[str, str, str]]:
        """Find which device+sensor/actuator uses a given device_id.

        Returns list of (device_name, component_type, component_name).
        """
        results: list[tuple[str, str, str]] = []
        for profile in self._profiles.values():
            for sensor_name, sensor in profile.sensors.items():
                if sensor.device_id == device_id:
                    results.append((profile.name, "sensor", sensor_name))
            for act_name, actuator in profile.actuators.items():
                if actuator.device_id == device_id:
                    results.append((profile.name, "actuator", act_name))
        return results

    @classmethod
    def default(cls) -> DeviceRegistry:
        """Create a registry loaded with built-in device profiles."""
        registry = cls()
        devices_dir = Path(__file__).parent.parent / "devices"
        registry.load_directory(devices_dir)
        return registry
