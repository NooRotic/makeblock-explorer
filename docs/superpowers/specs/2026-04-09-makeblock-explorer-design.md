# MakeBlock FF55 Device Explorer CLI

## Context

We own a full set of Makeblock STEM products, with CyberPi and HaloCode immediately accessible. The goal is to build a Python-based Device Explorer CLI that speaks the raw Makeblock FF55 binary protocol over serial/WiFi, giving us full control over connected devices from the desktop.

**Why this project:**
- Learn the actual wire protocol instead of relying on black-box libraries
- Build a foundation that works across ALL Makeblock devices (shared FF55 protocol)
- Enable traffic capture for reverse-engineering undocumented device commands
- Serve as the foundation for a future **Claude Code Companion** -- using CyberPi as a physical approval/notification device (joystick to approve edits, display for pending changes, WiFi notifications while away from desk)

**North star use case:** CyberPi in your pocket, getting Claude Code notifications and approving/rejecting edits via joystick while away from the computer.

## Known Devices

| Device | Chip | Connection | Key I/O |
|--------|------|------------|---------|
| CyberPi | ESP32-WROVER-B (240MHz, 8MB Flash, 8MB PSRAM) | USB-C, WiFi, BT | 128x128 display, 5 RGB LEDs, joystick, 2 buttons, accelerometer, gyro, light sensor, mic, speaker |
| HaloCode | ESP32 | USB, WiFi | 12-LED ring, motion sensor, mic, touchpad |

Both use the CH340 USB-UART bridge and the Makeblock FF55 protocol.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Interactive CLI (Rich + Click)                 │
│  - Numbered menus (user preference)             │
│  - scan / explore / control / capture / live    │
├─────────────────────────────────────────────────┤
│  Device Registry                                │
│  - YAML device profiles (type ID -> name/caps)  │
│  - Sensor definitions + response parsers        │
│  - Extensible per device family                 │
├──────────────────────┬──────────────────────────┤
│  FF55 Protocol       │  Traffic Capture         │
│  Engine              │                          │
│  - build_packet()    │  - Raw byte logging      │
│  - parse_packet()    │  - Annotated hex dump    │
│  - Action types:     │  - Replay from file      │
│    GET/RUN/RESET/    │  - JSON Lines format     │
│    START             │                          │
├──────────────────────┴──────────────────────────┤
│  Transport Layer (pluggable)                    │
│  - USB/Serial (pyserial + CH340 auto-detect)    │
│  - WiFi (raw sockets + ESP-NOW)                 │
│  - Bluetooth (stubbed for future)               │
└─────────────────────────────────────────────────┘
```

## FF55 Protocol Reference

### Packet Format
```
[0xFF][0x55][Length][Index][Action][Device][Data...]
```

| Field | Size | Description |
|-------|------|-------------|
| Header | 2 bytes | Always `0xFF 0x55` |
| Length | 1 byte | Length of remaining data (excluding header) |
| Index | 1 byte | Command index for request/response correlation |
| Action | 1 byte | `0x01`=GET, `0x02`=RUN, `0x04`=RESET, `0x05`=START |
| Device | 1 byte | Target device/module type ID |
| Data | variable | Payload (type-prefixed values) |

### Data Type Encoding
| Type ID | Type | Size |
|---------|------|------|
| 1 | byte | 1 |
| 2 | float | 4 |
| 3 | short | 2 |
| 4 | string | variable (null-terminated) |
| 5 | double | 8 |

### Serial Parameters
- Baud: 115200
- Data bits: 8
- Stop bits: 1
- Parity: None

## Project Structure

```
cyberpi/
├── src/
│   └── makeblock_explorer/
│       ├── __init__.py
│       ├── cli.py              # Click CLI + Rich menus
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── base.py         # Abstract transport interface
│       │   ├── serial.py       # USB/pyserial + CH340 detection
│       │   └── wifi.py         # Socket + ESP-NOW transport
│       ├── protocol/
│       │   ├── __init__.py
│       │   ├── ff55.py         # Packet encode/decode
│       │   ├── types.py        # Data type encoding/decoding
│       │   └── capture.py      # Traffic logging + replay
│       ├── registry/
│       │   ├── __init__.py
│       │   └── loader.py       # YAML device profile loader
│       └── devices/
│           ├── cyberpi.yaml    # CyberPi device profile
│           └── halocode.yaml   # HaloCode device profile
├── tests/
│   ├── test_ff55.py            # Protocol encode/decode tests
│   ├── test_capture.py         # Capture/replay tests
│   └── test_registry.py        # Device registry tests
├── captures/                   # Saved traffic captures
├── pyproject.toml
└── README.md
```

## Component Details

### Transport Layer (`transport/`)

Abstract interface:
```python
class Transport(Protocol):
    def connect(self, target: str) -> None: ...
    def disconnect(self) -> None: ...
    def send(self, data: bytes) -> None: ...
    def receive(self, timeout: float = 1.0) -> bytes: ...
    def scan() -> list[DeviceInfo]: ...  # class method
```

**SerialTransport:**
- Scans COM ports for CH340 VID/PID (vendor: 0x1A86, product: 0x7523)
- Opens at 115200/8-N-1
- Thread-safe send/receive with response buffering

**WiFiTransport:**
- UDP broadcast for device discovery
- TCP socket for command/response
- ESP-NOW integration for device-to-device (future)

### FF55 Protocol Engine (`protocol/ff55.py`)

```python
def build_packet(index: int, action: Action, device: int, data: bytes = b"") -> bytes:
    """Encode an FF55 command packet."""

def parse_packet(raw: bytes) -> Packet:
    """Decode an FF55 response packet."""

@dataclass
class Packet:
    index: int
    action: Action
    device: int
    data: bytes
    raw: bytes  # Original bytes for capture
```

### Traffic Capture (`protocol/capture.py`)

- Wraps any Transport, tees all bytes to a JSONL log file
- Each line: `{"ts": <epoch_ms>, "dir": "tx"|"rx", "raw": "<hex>", "decoded": {...}}`
- `replay(file)` feeds captured bytes back through `parse_packet()` for testing
- Annotated hex dump mode for terminal display:
  ```
  TX 14:32:01.003  FF 55 05 01 01 1E 00 00
                   ^^^^^ hdr  ^len ^idx ^act ^dev ^data
  RX 14:32:01.015  FF 55 04 01 02 1A 3F
                   ^^^^^ hdr  ^len ^idx ^type=float ^value
  ```

### Device Registry (`registry/`)

YAML device profiles:
```yaml
# devices/cyberpi.yaml
name: CyberPi
chip: ESP32-WROVER-B
transport: [serial, wifi]
sensors:
  accelerometer:
    device_id: 0x3D
    axes: [x, y, z]
    type: float
  gyroscope:
    device_id: 0x3E
    axes: [x, y, z]
    type: float
  light:
    device_id: 0x03
    type: short
  # ... more sensors
actuators:
  rgb_led:
    device_id: 0x08
    params: [index, r, g, b]
  display:
    device_id: 0x45
    # text, image, clear commands
  speaker:
    device_id: 0x22
    # tone, melody, volume
```

Note: Device IDs listed above are placeholders -- actual IDs will be discovered through traffic capture and documentation cross-referencing.

### CLI (`cli.py`)

Interactive numbered menu system:
```
=== MakeBlock Explorer ===
Connected: CyberPi on COM4, HaloCode on COM6

1. Scan for devices
2. Explore device (read sensors)
3. Control device (actuators)
4. Live sensor dashboard
5. Start traffic capture
6. Replay capture file
7. Raw packet mode
0. Exit

>
```

**Live sensor dashboard** uses Rich's Live display for real-time updates:
```
CyberPi Sensors (COM4) - 10Hz refresh
──────────────────────────────────────
Accel X:  0.12g  Y: -0.98g  Z:  0.03g
Gyro  X:  1.2°/s Y:  0.1°/s Z: -0.4°/s
Light:    342 lux
Mic:      ambient (12 dB)
Joystick: center
Button A: released  Button B: released
```

## Dependencies

| Package | Purpose |
|---------|---------|
| pyserial | Serial port communication |
| click | CLI framework |
| rich | Terminal UI (menus, live display, tables) |
| pyyaml | Device profile loading |
| pytest | Testing |

## Phased Delivery

### Phase 1: Protocol Foundation
- FF55 packet encode/decode with full test coverage
- Serial transport with CH340 auto-detection
- Traffic capture (log + annotated hex dump)
- Connect to CyberPi, send a GET, parse response
- **Verification:** Send a known command (e.g., read light sensor), see valid response bytes

### Phase 2: Device Exploration
- Device registry with CyberPi + HaloCode profiles
- CLI scan + explore commands
- Read all available sensors from both devices
- **Verification:** `scan` finds both devices, `explore` reads sensor values

### Phase 3: Interactive Control
- CLI control commands (RGB LEDs, display text, speaker tones)
- Live sensor dashboard with Rich
- Replay mode for captured traffic
- **Verification:** Change LED colors, display text, hear tones from CLI

### Phase 4: WiFi Transport
- WiFi device discovery and communication
- Untethered CyberPi operation
- **Verification:** Send commands over WiFi without USB cable

### Phase 5: Claude Code Companion (future)
- CyberPi MicroPython app: notification display + joystick approval UI
- Desktop bridge: hooks into Claude Code events, relays to CyberPi over WiFi
- Display pending edits, approve/reject with joystick
- Notification buzzer/LED for attention
- **Verification:** Approve a Claude Code edit from CyberPi while away from desk

## Verification Plan

1. **Unit tests:** Protocol encode/decode, data type serialization, capture format
2. **Integration test:** Connect to real CyberPi, send GET for light sensor, validate response structure
3. **Capture verification:** Record a session, replay it, confirm parsed output matches
4. **Cross-device:** Same commands work against both CyberPi and HaloCode
5. **Manual smoke test:** Full CLI workflow -- scan, explore, control LEDs, capture traffic

## Open Questions

1. **Actual device IDs:** The FF55 device type IDs for CyberPi's sensors/actuators need to be discovered via traffic capture from mBlock or cross-referenced with Makeblock-Libraries on GitHub
2. **HaloCode protocol differences:** Need to verify HaloCode uses identical FF55 framing (likely yes, but untested)
3. **WiFi discovery protocol:** How does mBlock discover CyberPi over WiFi? May need to capture that traffic too
4. **Claude Code hook mechanism:** How to intercept Claude Code approval requests programmatically (Phase 5 research)
