<p align="center">
  <img src="favicon.png" alt="NooRoticX" width="48"/>
</p>

<p align="center">
  <img src="png-clipart-computer-icons-logo-design-logo-cartoon-thumbnail.png" alt="mBot" width="80"/>
</p>

<h1 align="center">MakeBlock Explorer</h1>

<p align="center">
  <strong>Talk to MakeBlock hardware over USB serial. See what it says back.</strong>
</p>

<p align="center">
  Interactive CLI + REST API + real-time web dashboard.<br/>
  Speaks both FF55 (legacy) and F3 (CyberPi/HaloCode) binary protocols.
</p>

<p align="center">
  <img src="makeblock-construct-your-dreams.png" alt="MakeBlock Construct Your Dreams" width="240"/>
  &nbsp;&nbsp;&nbsp;
  <img src="makeblock_education.jpg" alt="MakeBlock Education" width="240"/>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a>
  &nbsp;&middot;&nbsp;
  <a href="#cli">CLI</a>
  &nbsp;&middot;&nbsp;
  <a href="#api">API</a>
  &nbsp;&middot;&nbsp;
  <a href="#web-dashboard">Dashboard</a>
  &nbsp;&middot;&nbsp;
  <a href="#protocols">Protocols</a>
</p>

---

## Why does this exist?

MakeBlock's CyberPi and HaloCode talk over proprietary binary protocols with almost no public documentation. If you're writing firmware, building classroom integrations, or just want to know what your CyberPi is actually sending over serial: there wasn't a good tool for that. So I built one.

Three ways to use it:

1. **`mbx` CLI**: scan, connect, explore device profiles, send raw packets
2. **REST + WebSocket API**: programmatic control from any language
3. **Web dashboard**: real-time sensor streaming, LED control, push notifications to the device display

## Quick Start

### Backend

```bash
git clone https://github.com/NooRotic/makeblock-explorer.git
cd makeblock-explorer
pip install -e .
```

Plug in a CyberPi or HaloCode via USB:

```bash
mbx
```

The interactive menu walks you through scanning, connecting, and exploring.

### Web Dashboard

```bash
mbx-server            # starts API on port 8333

# separate terminal
cd web
npm install
npm run dev            # dashboard on localhost:3000
```

## CLI

The `mbx` command gives you a numbered menu with rich terminal formatting:

```
MakeBlock Explorer

  1. Scan for devices
  2. Connect to device
  3. Explore device profile
  4. Send raw FF55 packet
  5. List known profiles
```

### Direct commands

```bash
mbx scan                          # find connected MakeBlock devices (CH340)
mbx explore /dev/ttyUSB0          # show device profile and capabilities
mbx raw /dev/ttyUSB0 0x01         # send raw FF55 GET packet
```

## API

`mbx-server` starts a FastAPI server on port 8333.

| Method | Path | What it does |
|--------|------|-------------|
| `GET` | `/api/devices` | Scan serial ports for MakeBlock devices |
| `POST` | `/api/connect` | Connect to a device by port |
| `POST` | `/api/disconnect` | Disconnect a device |
| `GET` | `/api/status` | All connected devices + cached sensor data |
| `POST` | `/api/command` | Run MicroPython on the device |
| `GET` | `/api/sensors/{id}` | Cached sensor readings |
| `POST` | `/api/led` | Set RGB LED color (individual or all 5) |
| `POST` | `/api/notify` | Push notification to device display |
| `WS` | `/api/stream` | Real-time sensor streaming |

### Examples

```bash
# scan for devices
curl http://localhost:8333/api/devices

# set all LEDs to green
curl -X POST http://localhost:8333/api/led \
  -H "Content-Type: application/json" \
  -d '{"r": 0, "g": 255, "b": 0}'

# run MicroPython on the device
curl -X POST http://localhost:8333/api/command \
  -H "Content-Type: application/json" \
  -d '{"script": "cyberpi.get_loudness()"}'
```

## Web Dashboard

Four pages, all real-time via WebSocket:

| Page | What you get |
|------|-------------|
| **Dashboard** | Scan and connect devices. Live sensor cards: battery, brightness, orientation (pitch/roll), accelerometer |
| **Controls** | LED color picker, display text sender, direct MicroPython execution |
| **Notify** | Push text to CyberPi display with color, size, and flash options |
| **Settings** | Configuration |

Built with Next.js, React 19, Tailwind CSS v4. Dark theme throughout.

## Protocols

MakeBlock Explorer implements two binary serial protocols from scratch.

### FF55 (Legacy)

```
[0xFF][0x55][Length][Index][Action][Device][Data...]
```

Used by older MakeBlock boards. Actions: `GET`, `RUN`, `RESET`, `START`. Typed payloads with `BYTE`, `FLOAT`, `SHORT`, `STRING`, `DOUBLE` encoding.

### F3 (Modern)

```
[0xF3][HdrChk][Len_Lo][Len_Hi][Type][Mode][Idx_Lo][Idx_Hi][Data...][BodyChk][0xF4]
```

Used by CyberPi and HaloCode (ESP32-based). Dual checksums on header and body. Sends MicroPython scripts to the device, gets JSON back:

```json
{"ret": 42}
{"err": "name 'foo' is not defined"}
```

## Supported Devices

| Device | MCU | Sensors | Actuators | Transport |
|--------|-----|---------|-----------|-----------|
| **CyberPi** | ESP32-WROVER-B | Accelerometer, gyro, light, mic, joystick, buttons A/B | 5x RGB LEDs, 128x128 IPS display, speaker | Serial, WiFi, BT |
| **HaloCode** | ESP32 | Accelerometer, gyro, mic, touchpad | 12-LED RGB ring | Serial, WiFi |

Device profiles are YAML files in `src/makeblock_explorer/devices/`. Adding a new device = adding a new YAML file.

## Architecture

```
src/makeblock_explorer/
  cli.py                     # Interactive CLI (click + rich)
  protocol/
    ff55.py                  # FF55 binary protocol engine
    f3.py                    # F3 framed protocol engine
    capture.py               # Traffic capture to JSONL
  device/
    manager.py               # Serial lifecycle + sensor polling
    registry.py              # Multi-device registry
  transport/
    base.py                  # Abstract transport + CH340 scanner
    serial.py                # pyserial (115200 baud, 8N1)
  api/
    server.py                # FastAPI app
    routes/                  # REST + WebSocket endpoints
  devices/
    cyberpi.yaml             # CyberPi sensor/actuator profile
    halocode.yaml            # HaloCode profile

web/                         # Next.js dashboard
  src/app/                   # Pages
  src/hooks/useWebSocket.ts  # Real-time sensor streaming
  src/components/            # DeviceCard, sensor visualizations
```

Auto-discovery scans for CH340 USB-serial bridges (VID `1A86`, PID `7523`). The `CaptureTransport` wraps any transport and tees all TX/RX to annotated JSONL logs for protocol analysis.

## Tech Stack

| Layer | What |
|-------|------|
| Backend | Python 3.11+, pyserial, click, rich |
| API | FastAPI + uvicorn, WebSocket streaming |
| Frontend | Next.js, React 19, Tailwind CSS v4, Recharts |
| Build | hatchling (Python), npm (frontend) |
| Testing | pytest + pytest-asyncio + httpx (115+ tests) |

## Development

```bash
pip install -e ".[dev]"    # install with test deps
pytest                     # run tests
cd web && npm run dev      # dashboard dev mode
```

## License

MIT

---

<p align="center">
  <img src="wutang_fullyellow.png" alt="Wu-Tang" width="28"/>
</p>

<p align="center"><strong>C.R.E.A.M.</strong><br/>Code Rules Everything Around Me.</p>
