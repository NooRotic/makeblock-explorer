# CyberPi Dashboard — F3 Protocol Refactor + Web Dashboard

## Context

We have a working MakeBlock CyberPi Explorer CLI (Phase 1 complete, 115 tests) that was built around the FF55 binary protocol. Through live device testing on 2026-04-12, we discovered that **CyberPi and HaloCode use the F3/F4 framed protocol, not FF55**. We successfully:

- Performed the F3 handshake (probe + online mode packet)
- Read live sensor data: brightness, battery, pitch, roll, accelerometer
- Controlled LEDs: `cyberpi.led.on(r,g,b)`, `cyberpi.led.set(id,r,g,b)`
- Displayed text: `cyberpi.display.show_label(text, size, x, y)` with `set_brush(r,g,b)` for color
- Confirmed error reporting: device returns `{"err": "TypeError"}` on bad calls

This spec covers the refactor from FF55 to F3 and the addition of a web-based dashboard with a simple push notification feature.

**North star:** CyberPi as a Claude Code Companion — joystick approvals, display notifications, untethered over WiFi. This phase builds the device control foundation and proves the notification pipeline.

## Scope

### In Scope (This Phase)
- F3/F4 protocol engine (replacing FF55 as primary protocol for CyberPi/HaloCode)
- Multi-device DeviceManager with serial bridge
- FastAPI backend with REST + WebSocket API
- Next.js React dashboard (persistent browser tab)
  - Live sensor readings
  - LED and display controls
  - Push notification to CyberPi display
- Existing FF55 code preserved (not deleted — valid for mBot/MegaPi)

### Out of Scope (Phase C and Beyond)
- External webhook receiver (GitHub, Slack, CI, etc.)
- WiFi transport (ESP-NOW, TCP socket)
- Claude Code Companion integration (approval workflows)
- MicroPython app deployment to CyberPi
- Bluetooth transport

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Next.js Frontend (React, always-open dashboard)        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │Dashboard │ │Controls  │ │ Notify   │ │ Settings  │  │
│  │(sensors) │ │(LED/disp)│ │(push msg)│ │(devices)  │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬─────┘  │
│       │ WebSocket   │ REST       │ REST         │ REST   │
└───────┼─────────────┼────────────┼──────────────┼────────┘
        │             │            │              │
┌───────┴─────────────┴────────────┴──────────────┴────────┐
│  FastAPI Backend (Python, async)                         │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ API Layer                                           │ │
│  │  GET  /api/devices     - scan COM ports             │ │
│  │  POST /api/connect     - connect to device          │ │
│  │  POST /api/disconnect  - close connection           │ │
│  │  POST /api/command     - execute MicroPython script │ │
│  │  GET  /api/sensors     - latest cached readings     │ │
│  │  WS   /api/stream      - live sensor stream         │ │
│  │  POST /api/notify      - push text to display       │ │
│  │  POST /api/led         - set LED color(s)           │ │
│  └──────────────────────────┬──────────────────────────┘ │
│  ┌──────────────────────────┴──────────────────────────┐ │
│  │ DeviceRegistry (manages multiple DeviceManagers)    │ │
│  │  ┌────────────────┐  ┌────────────────┐             │ │
│  │  │ DeviceManager  │  │ DeviceManager  │  ...        │ │
│  │  │ (COM5/CyberPi) │  │ (COM6/HaloCd) │             │ │
│  │  │ - own thread   │  │ - own thread   │             │ │
│  │  │ - command queue │  │ - command queue │             │ │
│  │  │ - sensor cache  │  │ - sensor cache  │             │ │
│  │  └───────┬────────┘  └───────┬────────┘             │ │
│  └──────────┼───────────────────┼──────────────────────┘ │
│  ┌──────────┴───────────────────┴──────────────────────┐ │
│  │ F3 Protocol Engine                                  │ │
│  │  build_f3_packet() / parse_f3_response()            │ │
│  │  Handshake: probe + online mode                     │ │
│  │  Response format: {"ret": value} / {"err": msg}     │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
        │                         │
        ▼                         ▼
   ┌─────────┐              ┌─────────┐
   │ CyberPi │              │HaloCode │
   │  COM5   │              │  COM6   │
   └─────────┘              └─────────┘
```

## F3/F4 Protocol Reference

### Packet Format

```
[0xF3][HeaderChecksum][DataLen_Lo][DataLen_Hi][Type][Mode][Idx_Lo][Idx_Hi][Data...][BodyChecksum][0xF4]
```

| Field | Size | Description |
|-------|------|-------------|
| Header | 1 byte | Always `0xF3` |
| Header Checksum | 1 byte | `(0xF3 + DataLen_Lo + DataLen_Hi) & 0xFF` |
| DataLen_Lo | 1 byte | Payload length, low byte (includes Type+Mode+Idx+Data, so `len(data) + 4`) |
| DataLen_Hi | 1 byte | Payload length, high byte |
| Type | 1 byte | Packet type (see below) |
| Mode | 1 byte | `0x00`=fire-and-forget, `0x01`=expect response, `0x03`=immediate |
| Idx_Lo | 1 byte | Command index, low byte (for request/response correlation) |
| Idx_Hi | 1 byte | Command index, high byte |
| Data | variable | `[script_len_lo, script_len_hi, ...script_utf8_bytes]` |
| Body Checksum | 1 byte | `(Type + Mode + Idx_Lo + Idx_Hi + sum(Data)) & 0xFF` |
| Footer | 1 byte | Always `0xF4` |

### Packet Types

| Type | Value | Description |
|------|-------|-------------|
| TYPE_RUN_WITHOUT_RESPONSE | `0x00` | Fire and forget |
| TYPE_RUN_WITH_RESPONSE | `0x01` | Expect a response |
| TYPE_RESET | `0x02` | Reset device |
| TYPE_RUN_IMDT_WITH_RESPONSE | `0x03` | Immediate response |
| TYPE_ONLINE | `0x0D` | Online/offline mode toggle |
| TYPE_SCRIPT | `0x28` | Script execution (primary command type) |
| TYPE_SUBSCRIBE | `0x29` | Subscribe to data updates |

### Handshake Sequence

1. Open serial at 115200 baud (8N1) via CH340 USB-UART bridge
2. Reset device via DTR/RTS toggle (required on first connection)
3. Wait 4 seconds for boot (ESP-NOW init, WiFi warning)
4. Drain boot output
5. Send probe: F3 script packet with `cyberpi.get_bri()`, idx=1, mode=0x01
6. Wait for response (may get boot text mixed in — tolerate non-F3 data)
7. Send online mode: `[0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x01, 0x0E, 0xF4]`
8. Send sync read to confirm pipeline is ready
9. Device is now accepting commands

### Response Format

Responses are F3-framed packets containing UTF-8 JSON:
- Success: `{"ret": <value>}` — value is number, string, or null
- Error: `{"err": "<ErrorType>"}` with plaintext error message preceding the frame

### Known CyberPi MicroPython API

**Sensors (mode=0x01, expect response):**
| Function | Returns | Description |
|----------|---------|-------------|
| `cyberpi.get_bri()` | int (0-100) | Ambient brightness |
| `cyberpi.get_loudness("maximum")` | int | Microphone loudness |
| `cyberpi.get_battery()` | int (0-100) | Battery percentage |
| `cyberpi.get_firmware_version()` | string | Firmware version |
| `cyberpi.get_pitch()` | int (degrees) | Pitch angle |
| `cyberpi.get_roll()` | int (degrees) | Roll angle |
| `cyberpi.get_acc("x"/"y"/"z")` | float (g) | Accelerometer axis |
| `cyberpi.get_gyro("x"/"y"/"z")` | float (deg/s) | Gyroscope axis |

**Actuators (mode=0x00, fire-and-forget):**
| Function | Description |
|----------|-------------|
| `cyberpi.led.on(r, g, b)` | Set all 5 LEDs to RGB color |
| `cyberpi.led.set(id, r, g, b)` | Set single LED (1-5) |
| `cyberpi.led.on(0, 0, 0)` | Turn off all LEDs |
| `cyberpi.display.clear()` | Clear the 128×128 display |
| `cyberpi.display.set_brush(r, g, b)` | Set text color for subsequent labels |
| `cyberpi.display.show_label(text, size, x, y)` | Show text at pixel coordinates |
| `cyberpi.audio.play_tone(freq, duration)` | Play tone (untested) |

## Component Details

### F3 Protocol Engine (`protocol/f3.py`)

```python
@dataclass
class F3Packet:
    type: int          # Packet type (0x28 for script)
    mode: int          # 0x00=no response, 0x01=with response
    index: int         # Command index for correlation (0-65535)
    data: bytes        # Raw data payload
    script: str | None # Decoded script (if TYPE_SCRIPT)
    raw: bytes         # Original wire bytes

@dataclass
class F3Response:
    index: int         # Correlates to request index
    value: Any         # Parsed from {"ret": ...}
    error: str | None  # Parsed from {"err": ...}
    raw: bytes         # Original wire bytes

def build_f3_packet(script: str, index: int, mode: int = 0x01) -> bytes:
    """Encode a MicroPython script into an F3 wire packet."""

def parse_f3_response(data: bytes) -> list[F3Response]:
    """Parse F3 response frames from a byte stream. Returns all complete frames found."""

def find_f3_frames(data: bytes) -> list[tuple[F3Packet, int]]:
    """Find all F3 frames in raw bytes. Returns (packet, end_offset) pairs."""

ONLINE_MODE_PACKET = bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x01, 0x0E, 0xF4])
OFFLINE_MODE_PACKET = bytes([0xF3, 0xF6, 0x03, 0x00, 0x0D, 0x00, 0x00, 0x0D, 0xF4])
```

### DeviceManager (`device/manager.py`)

```python
class DeviceManager:
    """Manages a single serial connection to a MakeBlock device.

    Runs a background thread that owns the serial port exclusively.
    Commands are submitted via async methods that use thread-safe queues.
    """

    device_id: str           # Unique identifier (e.g., "cyberpi-COM5")
    device_type: str         # "cyberpi" or "halocode" (detected by probing: try `cyberpi.get_bri()` — success = CyberPi, error = try `halocode.get_brightness()` for HaloCode, fallback = "unknown")
    port: str                # COM port
    is_connected: bool       # Connection state
    sensor_cache: dict       # Latest sensor readings

    async def connect(self, port: str) -> None:
        """Open serial, run F3 handshake, start sensor polling."""

    async def disconnect(self) -> None:
        """Stop polling, close serial, terminate thread."""

    async def execute(self, script: str, expect_response: bool = True) -> F3Response | None:
        """Send a MicroPython script to the device and optionally wait for response."""

    async def start_sensor_polling(self, hz: float = 5.0) -> None:
        """Begin continuous sensor reads, broadcasting to subscribers.

        Default poll set (CyberPi): brightness, pitch, roll, accel_x/y/z, battery.
        Each poll cycle reads all sensors sequentially (~7 commands per cycle).
        At 5Hz this is ~35 F3 packets/sec — well within serial bandwidth.
        """

    def subscribe(self, callback: Callable[[dict], None]) -> str:
        """Subscribe to sensor updates. Returns subscription ID."""

    def unsubscribe(self, sub_id: str) -> None:
        """Remove a sensor subscription."""
```

### DeviceRegistry (`device/registry.py`)

```python
class DeviceRegistry:
    """Manages multiple connected DeviceManagers.

    Singleton that tracks all connected devices, handles scan/connect/disconnect,
    and routes commands to the correct DeviceManager by device_id.
    """

    async def scan(self) -> list[DeviceInfo]:
        """Scan COM ports for CH340 devices."""

    async def connect(self, port: str) -> DeviceManager:
        """Create and connect a DeviceManager for the given port."""

    async def disconnect(self, device_id: str) -> None:
        """Disconnect and remove a DeviceManager."""

    def get(self, device_id: str) -> DeviceManager | None:
        """Get a connected DeviceManager by ID."""

    def list_connected(self) -> list[DeviceManager]:
        """List all connected devices."""
```

### FastAPI Application (`api/server.py`)

```python
app = FastAPI(title="MakeBlock Explorer API")

# CORS middleware for Next.js dev server (localhost:3000)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])

# Device management
@app.get("/api/devices")        # Scan for available devices
@app.post("/api/connect")       # Connect to a device by port
@app.post("/api/disconnect")    # Disconnect a device by device_id
@app.get("/api/status")         # Connection status of all devices

# Commands
@app.post("/api/command")       # Execute arbitrary MicroPython script
@app.get("/api/sensors/{device_id}")  # Latest cached sensor readings
@app.post("/api/led")           # Set LED colors
@app.post("/api/notify")        # Push notification to display

# WebSocket
@app.websocket("/api/stream")   # Live sensor stream (all devices, multiplexed)
```

**WebSocket message format:**
```json
// Server → Client (sensor update)
{"type": "sensor", "device_id": "cyberpi-COM5", "data": {"brightness": 42, "pitch": 3, "roll": -1, "accel_x": 0.2}}

// Server → Client (notification acknowledgment)
{"type": "notify_ack", "device_id": "cyberpi-COM5", "status": "ok"}

// Client → Server (subscribe to specific device)
{"type": "subscribe", "device_id": "cyberpi-COM5"}

// Client → Server (subscribe to all)
{"type": "subscribe", "device_id": "all"}
```

### Next.js Frontend (`web/`)

**Tech stack:**
- Next.js 14+ (App Router)
- React 18+
- Tailwind CSS for styling
- Recharts or similar for sensor charts
- Native WebSocket (no socket.io — keep it simple)

**Pages:**

| Route | Purpose |
|-------|---------|
| `/` | Dashboard — device cards with live sensor gauges, connection status |
| `/controls` | LED color picker, display text controls, speaker tone |
| `/notify` | Push notification form: text input + color picker + size → send to device |
| `/settings` | Device scan, connect/disconnect, polling rate config |

**Dashboard device card layout:**
```
┌─────────────────────────────────────┐
│ 🟢 CyberPi (COM5)        [Disconnect]│
│                                      │
│  Brightness ████████░░ 42            │
│  Battery    ██░░░░░░░░ 10%           │
│  Pitch      3°   Roll  -1°          │
│  Accel      X:0.2  Y:-0.9  Z:0.0   │
│                                      │
│  [💡 LEDs]  [📺 Display]  [📨 Notify]│
└─────────────────────────────────────┘
```

### Push Notification Feature

The simple notification feature for this phase:

**Frontend (`/notify`):**
- Text input field (max 20 chars — display is 128px wide)
- Color picker (defaults to white)
- Font size selector (16, 20, 24, 28, 32)
- Device selector dropdown (if multiple connected)
- "Send to CyberPi" button
- Shows last 5 sent notifications as a history list

**Backend (`POST /api/notify`):**
```json
// Request
{
  "device_id": "cyberpi-COM5",
  "text": "Hi Chat!",
  "color": [0, 255, 0],
  "size": 24,
  "flash_leds": true
}

// Response
{"status": "ok", "device_id": "cyberpi-COM5"}
```

**Device execution sequence:**
1. `cyberpi.display.clear()`
2. `cyberpi.display.set_brush(r, g, b)`
3. `cyberpi.display.show_label(text, size, x, y)` — x/y auto-centered based on text length and size
4. If `flash_leds`: `cyberpi.led.on(r, g, b)` → 500ms → `cyberpi.led.on(0, 0, 0)` × 3 flashes

## Project Structure

```
cyberpi/
├── src/
│   └── makeblock_explorer/
│       ├── __init__.py
│       ├── cli.py                    # UPDATED: scan/connect uses F3 handshake, raw mode sends F3 packets. Menu structure preserved.
│       ├── protocol/
│       │   ├── __init__.py
│       │   ├── f3.py                 # NEW: F3/F4 protocol engine
│       │   ├── ff55.py               # KEPT: FF55 for mBot/MegaPi
│       │   ├── types.py              # Shared data type encoding
│       │   └── capture.py            # Traffic capture (updated for F3)
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── base.py               # Abstract transport + scan
│       │   └── serial.py             # Serial transport (updated with F3 handshake)
│       ├── device/
│       │   ├── __init__.py
│       │   ├── manager.py            # NEW: DeviceManager (serial bridge thread)
│       │   └── registry.py           # REWRITTEN: multi-device DeviceRegistry
│       ├── api/
│       │   ├── __init__.py
│       │   ├── server.py             # NEW: FastAPI app
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── devices.py        # Device scan/connect/disconnect
│       │   │   ├── commands.py        # Script execution, LED, notify
│       │   │   └── stream.py         # WebSocket sensor stream
│       │   └── models.py             # Pydantic request/response models
│       └── devices/
│           ├── cyberpi.yaml          # Updated: known MicroPython commands
│           └── halocode.yaml         # Updated: known MicroPython commands
├── web/                              # NEW: Next.js frontend
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx            # Root layout with nav
│   │   │   ├── page.tsx              # Dashboard (live sensors)
│   │   │   ├── controls/page.tsx     # LED/display/speaker controls
│   │   │   ├── notify/page.tsx       # Push notification form
│   │   │   └── settings/page.tsx     # Device management
│   │   ├── components/
│   │   │   ├── DeviceCard.tsx        # Device status + sensor gauges
│   │   │   ├── SensorGauge.tsx       # Individual sensor display
│   │   │   ├── LedColorPicker.tsx    # RGB color picker for LEDs
│   │   │   ├── DisplayControl.tsx    # Text + color → display
│   │   │   ├── NotifyForm.tsx        # Notification push form
│   │   │   └── ConnectionStatus.tsx  # Header connection indicator
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts       # WebSocket connection + reconnect
│   │   │   └── useDevice.ts          # Device API helpers
│   │   └── lib/
│   │       └── api.ts                # REST API client
│   └── public/
├── tests/
│   ├── test_f3.py                    # NEW: F3 protocol tests
│   ├── test_ff55.py                  # KEPT: existing FF55 tests
│   ├── test_manager.py               # NEW: DeviceManager tests
│   ├── test_api.py                   # NEW: FastAPI endpoint tests
│   ├── test_transport.py             # KEPT: transport tests
│   ├── test_capture.py               # KEPT: capture tests (updated)
│   └── test_registry.py              # UPDATED: new registry tests
├── pyproject.toml                    # Updated: add fastapi, uvicorn, websockets
├── captures/
└── docs/
```

## Dependencies

### Python (added to pyproject.toml)
| Package | Purpose |
|---------|---------|
| fastapi | Async web framework |
| uvicorn | ASGI server |
| websockets | WebSocket support for FastAPI |
| pydantic | Request/response validation (comes with FastAPI) |

### Frontend (web/package.json)
| Package | Purpose |
|---------|---------|
| next | React framework |
| react / react-dom | UI library |
| tailwindcss | Utility CSS |
| recharts | Sensor data charts |

## Testing Strategy

1. **F3 protocol unit tests** — packet building, response parsing, checksum validation, frame finding in byte streams (mirrors existing FF55 test patterns)
2. **DeviceManager unit tests** — mock serial port, verify handshake sequence, command queue behavior, sensor polling loop
3. **FastAPI endpoint tests** — httpx TestClient, mock DeviceRegistry, verify all REST routes
4. **WebSocket tests** — connect, subscribe, verify sensor broadcast format
5. **Frontend** — manual testing for this phase (automated frontend tests in a later phase)
6. **Existing tests preserved** — all 115 FF55/transport/capture/registry tests stay green

## Verification Plan

1. `pytest` — all existing + new tests pass
2. Start FastAPI server, scan for CyberPi on real hardware
3. Connect via dashboard, see live sensor values updating
4. Use LED color picker — see CyberPi LEDs change
5. Use display controls — see text appear on CyberPi screen
6. Push notification from `/notify` page — see text + LED flash on CyberPi
7. Connect second device (HaloCode) — verify multi-device dashboard
