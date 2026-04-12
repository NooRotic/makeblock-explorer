# CyberPi Custom Firmware Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Goal:** Transform the CyberPi into a wireless Claude Code remote that also serves as a dual-mode (serial + WiFi) device dashboard.

## Problem

CyberOS (stock firmware v44.01.011) manages WiFi via a co-processor that is inaccessible from MicroPython. Raw TCP sockets, HTTP, and MQTT calls from user code all fail silently. The device cannot do outbound networking despite having a valid DHCP lease. This blocks wireless communication entirely.

The CyberPi hardware (ESP32-WROVER-B, 8MB flash, 8MB PSRAM, WiFi/BT) is fully capable. The limitation is purely firmware.

## Solution

Flash custom Arduino firmware using the official Makeblock Arduino SDK, adding WiFi and MQTT support. The firmware runs as four FreeRTOS tasks communicating via queues, preserving full backwards compatibility with the existing F3 serial protocol.

## Primary Use Case

The user carries the CyberPi away from the terminal. When Claude Code needs approval (run tests? commit? proceed?), the prompt appears on the CyberPi display. The user responds via joystick/buttons. The response flows back over MQTT to Claude Code, which continues working. No terminal interaction required.

Secondary uses: live sensor dashboard over WiFi, remote slash commands (`/usage`, `/status`), status feed of Claude Code activity.

## Hardware Reference

```
ESP32-WROVER-B (Dual-Core 240MHz, 8MB Flash, 8MB PSRAM)
├── I2C (GPIO18=SCL, GPIO19=SDA, 400kHz)
│   ├── 0x58: AW9523B #2 (buttons, joystick, LCD control pins)
│   ├── 0x5B: AW9523B #1 (5 RGB LED PWM)
│   ├── 0x69: MPU6887 (6-axis IMU)
│   └── 0x10: ES8218E (microphone ADC)
├── SPI Host 1 (GPIO2=MOSI, GPIO4=CLK, GPIO26=MISO)
│   ├── CS=GPIO12: ST7735 LCD (128x128, 20MHz)
│   └── CS=GPIO27: GT30L24A3W font flash (4MHz)
├── I2S_NUM_0 (TX, DAC) → GPIO25 speaker
├── I2S_NUM_1 (RX) → GPIO13=BCK, GPIO14=WS, GPIO35=DATA_IN (mic)
├── GPIO0: MCLK for ES8218E
├── GPIO33: Light sensor (ADC)
└── WiFi/BT: Available in silicon, unused by stock SDK
```

### AW9523B GPIO Expander (0x58) Pin Map

| Pin | Function |
|-----|----------|
| P0_0 | Joystick LEFT |
| P0_1 | Joystick UP |
| P0_2 | Joystick RIGHT |
| P0_3 | Joystick CENTER (press) |
| P0_4 | Joystick DOWN |
| P0_5 | Button B |
| P0_6 | Button A |
| P1_0 | Button MENU |
| P1_3 | Speaker amplifier enable |
| P1_4 | LCD DC (Data/Command) |
| P1_5 | LCD RESET |
| P1_7 | LCD Backlight |

## MQTT Topic Schema

All topics are namespaced by `device_id`, derived from the last 3 bytes of the MAC address (e.g., `cyberpi-a2f6e4`).

| Topic | Direction | Payload | Purpose |
|-------|-----------|---------|---------|
| `claude/prompt/{device_id}` | PC → CyberPi | `{"id":"uuid","text":"Run tests?","options":["yes","no","skip"],"type":"confirm"}` | Prompt requiring user response |
| `claude/response/{device_id}` | CyberPi → PC | `{"id":"uuid","selected":"yes"}` | User's button response |
| `claude/status/{device_id}` | PC → CyberPi | `{"text":"Building...","type":"info"}` | Status update. Types: `info`, `success`, `error`, `warning` |
| `claude/command/{device_id}` | CyberPi → PC | `{"command":"/usage"}` | Slash command from device |
| `claude/command_result/{device_id}` | PC → CyberPi | `{"command":"/usage","result":"..."}` | Command output for display |
| `cyberpi/sensors/{device_id}` | CyberPi → PC | `{"battery":15,"pitch":7,"roll":-5,...}` | Periodic sensor data (1Hz) |
| `cyberpi/online/{device_id}` | CyberPi → PC | `{"status":"online","firmware":"1.0.0"}` | Retained LWT message for online/offline detection |

## Firmware Architecture

Four FreeRTOS tasks communicating through three queues:

### Tasks

| Task | Core | Stack | Rate | Responsibility |
|------|------|-------|------|----------------|
| `mqttTask` | 0 | 8KB | Event-driven | WiFi connect/reconnect, MQTT subscribe/publish, LWT heartbeat |
| `sensorTask` | 1 | 4KB | Mixed (see below) | IMU (100Hz), light (5Hz), mic loudness (5Hz), battery (1Hz) |
| `serialTask` | 1 | 4KB | Event-driven | F3 protocol handler, WiFi/MQTT serial provisioning |
| `uiTask` | 1 | 4KB | 50Hz | Display rendering, button/joystick input, LEDs, sound alerts |

### Queues

| Queue | From → To | Carries | Depth |
|-------|-----------|---------|-------|
| `inboundQueue` | mqttTask → uiTask | `PromptMessage`, `StatusMessage`, `CommandResult` | 8 |
| `outboundQueue` | uiTask, serialTask → mqttTask | `UserResponse`, `SlashCommand`, `SensorBundle` | 8 |
| `sensorQueue` | sensorTask → uiTask, mqttTask | `SensorReading` | 4 |

### Message Structs

```cpp
enum class MessageType : uint8_t {
    PROMPT, STATUS, COMMAND_RESULT,     // inbound (PC → CyberPi)
    RESPONSE, SLASH_COMMAND, SENSORS    // outbound (CyberPi → PC)
};

struct PromptMessage {
    char id[37];           // UUID
    char text[128];        // Prompt text
    char options[4][16];   // Up to 4 options, 15 chars each
    uint8_t optionCount;
};

struct StatusMessage {
    char text[128];
    uint8_t type;          // 0=info, 1=success, 2=error, 3=warning
};

struct CommandResult {
    char command[16];
    char result[256];
};

struct UserResponse {
    char promptId[37];
    char selected[16];
};

struct SlashCommand {
    char command[16];
};

struct SensorReading {
    float pitch, roll, yaw;
    float accelX, accelY, accelZ;
    uint16_t brightness;
    uint16_t loudness;
    uint8_t battery;
};
```

## UI Design

Three screens, cycled with the Menu button.

### Screen 1: Prompt Screen (default)

```
┌──────────────────────┐
│ ● Claude Code   WIFI │  status bar
├──────────────────────┤
│                      │
│  Run tests before    │  prompt text (word-wrapped, max 4 lines)
│  committing?         │
│                      │
├──────────────────────┤
│ ▲ yes                │  options list (joystick UP/DOWN)
│   no            [A]→ │  button A confirms
│   skip               │
└──────────────────────┘
```

When no prompt is pending: "Waiting for prompts..." with a pulsing dot animation.

### Screen 2: Status Feed

```
┌──────────────────────┐
│ ● Status        WIFI │
├──────────────────────┤
│ ✓ Tests passed       │  last 6 messages, newest at bottom
│ ⚠ Lint warning       │  color-coded by type
│ → Building...        │
│ ✓ Committed abc123   │
└──────────────────────┘
```

### Screen 3: Commands & Sensors

```
┌──────────────────────┐
│ ● Commands      WIFI │
├──────────────────────┤
│ ▲ /usage             │  joystick to select, button A to send
│   /status            │
│   /help              │
├──────────────────────┤
│ Bat:15% Bri:42       │  sensor summary
│ P:7° R:-5° Loud:14   │
└──────────────────────┘
```

### LED & Sound Alerts

| Event Type | LED Pattern | Sound |
|------------|------------|-------|
| Prompt arrives | Pulsing blue (until answered) | Two-tone chime |
| Success | Green flash (3x) | Rising tone |
| Error | Red flash (3x) | Descending tone |
| Warning | Yellow flash (2x) | Single beep |
| Info | Dim white pulse (1x) | None |

### Button Map

| Input | Action |
|-------|--------|
| Joystick UP/DOWN | Navigate options / scroll |
| Button A | Confirm selection |
| Button B | Back / dismiss |
| Menu | Cycle screens |
| Joystick CENTER | Quick-respond "yes" to current prompt |

## Claude Code Integration

### Python MQTT Bridge

A Python service (`makeblock_explorer.bridge`) that translates between Claude Code hooks and MQTT:

```
Claude Code hooks → bridge.py → MQTT broker → CyberPi
                                MQTT broker ← CyberPi
                  ← bridge.py ←─────────────┘
```

The bridge:
- Subscribes to `claude/response/{device_id}` and `claude/command/{device_id}`
- Publishes to `claude/prompt/{device_id}`, `claude/status/{device_id}`, `claude/command_result/{device_id}`
- When a response arrives from CyberPi, injects it as input to the waiting Claude Code process
- When a slash command arrives, executes it and publishes the result back

### Claude Code Hooks

Three hooks configured in `.claude/settings.json`:

| Hook Event | Action |
|------------|--------|
| `Notification` | Publishes prompt message with options to MQTT |
| `UserPromptSubmit` | Publishes the user's message as a status update |
| `Stop` | Publishes success/error status based on session result |

### Slash Command Execution

When CyberPi sends a command (e.g., `/usage`) on `claude/command/{device_id}`:
1. Bridge receives it
2. Executes the appropriate CLI command
3. Truncates output to fit the CyberPi display (256 chars max)
4. Publishes result on `claude/command_result/{device_id}`

## WiFi Provisioning

Serial commands for first-time setup, stored in ESP32 NVS:

| Serial Command | Action |
|----------------|--------|
| `WIFI:<ssid>,<password>` | Store WiFi credentials, connect |
| `MQTT:<host>,<port>` | Store MQTT broker address, connect |
| `STATUS` | Print current WiFi/MQTT connection state |
| `RESET` | Clear stored credentials, reboot |

Credentials persist across reboots. On boot, firmware checks NVS for stored creds and auto-connects. If no creds found, device operates in serial-only mode.

## File Structure

### Firmware (new)

```
firmware/
├── platformio.ini
├── src/
│   ├── main.cpp                ← setup() + task creation
│   ├── config.h                ← Pins, queue sizes, topic strings
│   ├── messages.h              ← Shared message structs
│   ├── mqtt_task.cpp/.h        ← WiFi + MQTT (core 0)
│   ├── sensor_task.cpp/.h      ← IMU, light, mic, battery (core 1)
│   ├── serial_task.cpp/.h      ← F3 protocol + provisioning (core 1)
│   ├── ui_task.cpp/.h          ← Display, LEDs, buttons, sound (core 1)
│   ├── nvs_store.cpp/.h        ← Credential storage
│   └── ui/
│       ├── screen_prompt.cpp/.h
│       ├── screen_status.cpp/.h
│       └── screen_commands.cpp/.h
├── lib/
│   └── cyberpi/                ← Makeblock Arduino SDK (git submodule)
└── data/
```

### Python Bridge (added to existing project)

```
src/makeblock_explorer/
├── bridge/
│   ├── __init__.py
│   ├── service.py              ← Main bridge process
│   ├── mqtt_client.py          ← paho-mqtt wrapper with reconnect
│   └── hook_handlers.py        ← Hook event → MQTT message translation
```

### Dependencies

| Component | Library | Purpose |
|-----------|---------|---------|
| Firmware MQTT | `PubSubClient` | Arduino MQTT client |
| Firmware JSON | `ArduinoJson` | Parse/build MQTT payloads |
| Firmware WiFi | `WiFi.h` (ESP32 built-in) | WiFi connectivity |
| Python bridge | `paho-mqtt` 2.1.0 | MQTT client (already installed) |

## Safety & Recovery

### Pre-flash Backup

```bash
esptool.py --port COM6 --baud 921600 read_flash 0x0 0x800000 cyberpi_stock_backup.bin
```

### Recovery Paths

| Situation | Recovery |
|-----------|----------|
| Custom firmware boots but broken | `esptool.py write_flash 0x0 cyberpi_stock_backup.bin` |
| Firmware won't boot | Hold BOOT button during USB plug-in, forces download mode, reflash |
| Full recovery | mBlock 5 → Setting → Firmware Update (always works) |
| WiFi won't connect | Serial provisioning works independently (core 1, no WiFi dependency) |
| MQTT broker down | Auto-reconnect; serial path unaffected; sensors continue locally |

### Incremental Flash Strategy

Do not build everything at once. Flash in stages, verifying each:

1. **Stage 1:** LED blink + serial echo. Confirm build chain and upload work.
2. **Stage 2:** Display + buttons. Confirm hardware drivers from SDK.
3. **Stage 3:** WiFi + MQTT. Confirm networking.
4. **Stage 4:** F3 serial protocol. Confirm backwards compatibility.
5. **Stage 5:** Full UI screens + Claude Code integration.

### Safeguards

- **Watchdog timer:** If any task hangs for >10s, ESP32 reboots automatically.
- **Serial always available:** Serial task runs on core 1 with no WiFi dependency. Even if WiFi/MQTT breaks entirely, serial access and F3 protocol work.
- **No OTA in v1:** Reduces attack surface. Updates require USB.
- **No TLS in v1:** Local network only. Can be added later.
- **No flash encryption:** Keeps recovery simple.

## Out of Scope for v1

- OTA firmware updates
- TLS/SSL on MQTT
- Multi-device mesh (ESP-NOW)
- Bluetooth connectivity
- Custom mBlock blocks
- Flash encryption
