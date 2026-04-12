# Firmware Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up PlatformIO project, back up stock firmware, flash incremental builds to confirm the toolchain and all hardware drivers work (LEDs, display, buttons, joystick, IMU, light sensor, mic, speaker).

**Architecture:** Single Arduino sketch using the Makeblock CyberPi Arduino SDK (`cyberpi.h`). The SDK's `cyber.begin()` initializes all hardware and spawns 3 FreeRTOS tasks on core 1 (LCD render, sensor read, sound synth). Our code runs in `setup()` and `loop()` on core 0.

**Tech Stack:** PlatformIO, Arduino framework, ESP32-WROVER-B, Makeblock CyberPi SDK (git submodule)

**Spec:** `docs/superpowers/specs/2026-04-12-cyberpi-custom-firmware-design.md`

**Plan series:** This is Plan 1 of 4:
1. **Firmware Foundation** (this plan) — toolchain, backup, hardware drivers
2. Firmware Networking — WiFi, MQTT, NVS, serial F3
3. Firmware UI — three screens, alerts, interaction
4. Python Bridge + Claude Code hooks

---

## File Structure

```
firmware/
├── platformio.ini              ← Build config
├── src/
│   ├── main.cpp                ← setup() + loop(), incremental test stages
│   └── config.h                ← Pin definitions, constants
├── lib/
│   └── cyberpi/                ← Git submodule → Makeblock SDK
└── backups/
    └── .gitkeep                ← Stock firmware backup stored here (not committed)
```

---

### Task 1: Install PlatformIO and esptool

**Files:** None (tooling setup)

- [ ] **Step 1: Install PlatformIO CLI**

```bash
pip install platformio
```

- [ ] **Step 2: Verify installation**

Run: `pio --version`
Expected: `PlatformIO Core, version 6.x.x`

- [ ] **Step 3: Install esptool for firmware backup**

```bash
pip install esptool
```

- [ ] **Step 4: Verify esptool**

Run: `esptool.py version`
Expected: `esptool.py v4.x`

- [ ] **Step 5: Commit nothing** — tooling only, no project files yet.

---

### Task 2: Back Up Stock CyberOS Firmware

**Files:**
- Create: `firmware/backups/.gitkeep`
- Create: `firmware/backups/.gitignore`

This is the safety net. We dump the full 8MB flash before touching anything.

- [ ] **Step 1: Ensure CyberPi is connected on COM6 and no other process holds the port**

Kill any running FastAPI server or serial monitor first:
```bash
netstat -ano | grep ":8333" | grep LISTENING | awk '{print $5}' | xargs -I{} taskkill //PID {} //F 2>/dev/null; echo "Port clear"
```

- [ ] **Step 2: Read the full flash image**

```bash
mkdir -p firmware/backups
esptool.py --port COM6 --baud 921600 read_flash 0x0 0x800000 firmware/backups/cyberpi_stock_v44.01.011.bin
```

Expected: Progress bar, completes in ~70 seconds, creates an 8MB `.bin` file.

- [ ] **Step 3: Verify the backup file size**

```bash
ls -la firmware/backups/cyberpi_stock_v44.01.011.bin
```

Expected: Exactly 8388608 bytes (8MB).

- [ ] **Step 4: Create .gitignore so backup binaries are never committed**

Create `firmware/backups/.gitignore`:
```
*.bin
```

- [ ] **Step 5: Create .gitkeep so the directory is tracked**

```bash
touch firmware/backups/.gitkeep
```

- [ ] **Step 6: Commit**

```bash
git add firmware/backups/.gitkeep firmware/backups/.gitignore
git commit -m "chore: add firmware backups directory with gitignore"
```

---

### Task 3: Scaffold PlatformIO Project

**Files:**
- Create: `firmware/platformio.ini`
- Create: `firmware/src/config.h`
- Create: `firmware/src/main.cpp`

- [ ] **Step 1: Create platformio.ini**

Create `firmware/platformio.ini`:
```ini
[env:cyberpi]
platform = espressif32
board = esp32dev
framework = arduino
upload_port = COM6
monitor_port = COM6
monitor_speed = 115200
board_build.partitions = default.csv
build_flags =
    -DBOARD_HAS_PSRAM
    -mfix-esp32-psram-cache-issue
    -Ilib/cyberpi/src
    -Ilib/cyberpi/src/lcd
    -Ilib/cyberpi/src/gyro
    -Ilib/cyberpi/src/io
    -Ilib/cyberpi/src/i2c
    -Ilib/cyberpi/src/sound
    -Ilib/cyberpi/src/microphone
    -Llib/cyberpi/src/lcd
    -lGT30L24A3W
lib_extra_dirs = lib
```

- [ ] **Step 2: Create config.h with pin definitions**

Create `firmware/src/config.h`:
```cpp
#pragma once

// ─── Pin Definitions (from CyberPi Arduino SDK) ──────────────
// I2C Bus
#define PIN_I2C_SCL         18
#define PIN_I2C_SDA         19

// SPI Bus (LCD + Font IC)
#define PIN_SPI_MOSI        2
#define PIN_SPI_CLK         4
#define PIN_SPI_MISO        26
#define PIN_LCD_CS          12
#define PIN_FONT_CS         27

// Audio
#define PIN_SPEAKER_DAC     25
#define PIN_MIC_BCK         13
#define PIN_MIC_WS          14
#define PIN_MIC_DATA        35
#define PIN_MIC_MCLK        0

// Sensors
#define PIN_LIGHT_SENSOR    33

// ─── I2C Addresses ───────────────────────────────────────────
#define I2C_ADDR_LED_EXPANDER   0x5B   // AW9523B #1 (RGB LEDs)
#define I2C_ADDR_IO_EXPANDER    0x58   // AW9523B #2 (buttons, LCD ctrl)
#define I2C_ADDR_IMU            0x69   // MPU6887
#define I2C_ADDR_MIC_CODEC      0x10   // ES8218E

// ─── Display ─────────────────────────────────────────────────
#define SCREEN_WIDTH        128
#define SCREEN_HEIGHT       128

// ─── Firmware Version ────────────────────────────────────────
#define FIRMWARE_VERSION    "0.1.0"
```

- [ ] **Step 3: Create minimal main.cpp (Stage 1 — serial echo only)**

Create `firmware/src/main.cpp`:
```cpp
#include <Arduino.h>
#include "config.h"

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== CyberPi Custom Firmware ===");
    Serial.print("Version: ");
    Serial.println(FIRMWARE_VERSION);
    Serial.println("Stage 1: Serial echo test");
    Serial.println("Type anything and press Enter...");
}

void loop() {
    if (Serial.available()) {
        String input = Serial.readStringUntil('\n');
        input.trim();
        Serial.print("Echo: ");
        Serial.println(input);
    }
}
```

- [ ] **Step 4: Build to verify the toolchain compiles**

```bash
cd firmware && pio run
```

Expected: `SUCCESS` — compiles without errors. The CyberPi SDK is not linked yet (no `#include "cyberpi.h"` yet), so this is a pure Arduino build test.

- [ ] **Step 5: Commit**

```bash
git add firmware/platformio.ini firmware/src/config.h firmware/src/main.cpp
git commit -m "chore(firmware): scaffold PlatformIO project with config and serial echo"
```

---

### Task 4: Add CyberPi Arduino SDK as Git Submodule

**Files:**
- Create: `firmware/lib/cyberpi/` (submodule)
- Modify: `firmware/platformio.ini` (add platform.local.txt copy note)

- [ ] **Step 1: Add the submodule**

```bash
cd firmware
git submodule add https://github.com/Makeblock-official/CyberPi-Library-for-Arduino.git lib/cyberpi-sdk
```

- [ ] **Step 2: Create a symlink or copy the library into lib/cyberpi**

The SDK repo has the library at `lib/cyberpi/`. We need to reference it properly. Create a symlink from the expected path:

```bash
# The SDK repo structure is: CyberPi-Library-for-Arduino/lib/cyberpi/
# PlatformIO expects libraries in firmware/lib/
# Create symlink to the inner library directory
ln -s cyberpi-sdk/lib/cyberpi firmware/lib/cyberpi
```

If symlinks don't work on Windows, copy instead:
```bash
cp -r firmware/lib/cyberpi-sdk/lib/cyberpi firmware/lib/cyberpi
```

- [ ] **Step 3: Verify the SDK header is accessible**

```bash
ls firmware/lib/cyberpi/src/cyberpi.h
```

Expected: File exists.

- [ ] **Step 4: Test build with SDK included — update main.cpp**

Replace `firmware/src/main.cpp` with:
```cpp
#include <Arduino.h>
#include "config.h"
#include "cyberpi.h"

CyberPi cyber;

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== CyberPi Custom Firmware ===");
    Serial.print("Version: ");
    Serial.println(FIRMWARE_VERSION);
    Serial.println("Stage 1: SDK init test");

    cyber.begin();
    Serial.println("cyber.begin() OK — all hardware initialized");
}

void loop() {
    if (Serial.available()) {
        String input = Serial.readStringUntil('\n');
        input.trim();
        Serial.print("Echo: ");
        Serial.println(input);
    }
    delay(10);
}
```

- [ ] **Step 5: Build**

```bash
cd firmware && pio run
```

Expected: `SUCCESS` — compiles with the SDK linked. If linker errors about `GT30L24A3W`, verify the `-Llib/cyberpi/src/lcd -lGT30L24A3W` flags in `platformio.ini`.

- [ ] **Step 6: Commit**

```bash
git add firmware/lib/ firmware/src/main.cpp .gitmodules
git commit -m "feat(firmware): add CyberPi Arduino SDK as submodule and verify build"
```

---

### Task 5: Stage 1 Flash — Serial Echo + LED Blink

**Files:**
- Modify: `firmware/src/main.cpp`

This is the first real flash. We blink LEDs and echo serial to confirm the hardware works.

- [ ] **Step 1: Update main.cpp to blink LEDs and echo serial**

Replace `firmware/src/main.cpp`:
```cpp
#include <Arduino.h>
#include "config.h"
#include "cyberpi.h"

CyberPi cyber;

uint32_t lastBlink = 0;
uint8_t ledIndex = 0;
bool ledOn = false;

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== CyberPi Custom Firmware ===");
    Serial.print("Version: ");
    Serial.println(FIRMWARE_VERSION);
    Serial.println("Stage 1: LED blink + serial echo");

    cyber.begin();
    Serial.println("Hardware initialized OK");

    // Turn all LEDs off
    for (int i = 0; i < 5; i++) {
        cyber.set_rgb(i, 0, 0, 0);
    }
    Serial.println("LEDs cleared. Starting blink cycle...");
}

void loop() {
    // Echo serial input
    if (Serial.available()) {
        String input = Serial.readStringUntil('\n');
        input.trim();
        if (input.length() > 0) {
            Serial.print("Echo: ");
            Serial.println(input);
        }
    }

    // Cycle through LEDs: red, green, blue, yellow, purple
    uint32_t now = millis();
    if (now - lastBlink >= 500) {
        lastBlink = now;

        // Turn off previous LED
        cyber.set_rgb(ledIndex, 0, 0, 0);

        // Advance to next LED
        ledIndex = (ledIndex + 1) % 5;

        // Color cycle: R, G, B, Y, P
        uint8_t colors[][3] = {
            {255, 0, 0},     // Red
            {0, 255, 0},     // Green
            {0, 0, 255},     // Blue
            {255, 255, 0},   // Yellow
            {255, 0, 255},   // Purple
        };

        cyber.set_rgb(ledIndex, colors[ledIndex][0], colors[ledIndex][1], colors[ledIndex][2]);
    }

    delay(10);
}
```

- [ ] **Step 2: Build**

```bash
cd firmware && pio run
```

Expected: `SUCCESS`

- [ ] **Step 3: Flash to device**

```bash
cd firmware && pio run --target upload
```

Expected: Upload completes, device reboots. LEDs should cycle through colors. Serial monitor should show boot messages.

- [ ] **Step 4: Open serial monitor and verify**

```bash
cd firmware && pio device monitor
```

Expected output:
```
=== CyberPi Custom Firmware ===
Version: 0.1.0
Stage 1: LED blink + serial echo
Hardware initialized OK
LEDs cleared. Starting blink cycle...
```

Type `hello` and press Enter. Expected: `Echo: hello`

- [ ] **Step 5: Verify LEDs are cycling visually**

You should see the 5 RGB LEDs cycling one at a time: red → green → blue → yellow → purple, one every 500ms.

- [ ] **Step 6: Commit**

```bash
git add firmware/src/main.cpp
git commit -m "feat(firmware): stage 1 — LED blink and serial echo verified on hardware"
```

---

### Task 6: Stage 2 — Display Test

**Files:**
- Modify: `firmware/src/main.cpp`

Confirm the ST7735 LCD works by drawing colored rectangles and text.

- [ ] **Step 1: Update main.cpp to add display test**

Replace `firmware/src/main.cpp`:
```cpp
#include <Arduino.h>
#include "config.h"
#include "cyberpi.h"

CyberPi cyber;

// Helper: fill a rectangle in the framebuffer
void fillRect(uint8_t x, uint8_t y, uint8_t w, uint8_t h, uint16_t color) {
    for (uint8_t dy = 0; dy < h && (y + dy) < SCREEN_HEIGHT; dy++) {
        for (uint8_t dx = 0; dx < w && (x + dx) < SCREEN_WIDTH; dx++) {
            cyber.set_lcd_pixel(x + dx, y + dy, color);
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== CyberPi Custom Firmware ===");
    Serial.println("Stage 2: Display test");

    cyber.begin();
    Serial.println("Hardware initialized");

    // Clear screen to black
    cyber.clean_lcd();

    // Draw colored bands
    uint16_t red   = cyber.swap_color(cyber.color24_to_16(0xFF0000));
    uint16_t green = cyber.swap_color(cyber.color24_to_16(0x00FF00));
    uint16_t blue  = cyber.swap_color(cyber.color24_to_16(0x0000FF));
    uint16_t white = cyber.swap_color(cyber.color24_to_16(0xFFFFFF));

    fillRect(0,  0,  128, 32, red);
    fillRect(0,  32, 128, 32, green);
    fillRect(0,  64, 128, 32, blue);
    fillRect(0,  96, 128, 32, white);

    // Render text
    wchar_t title[] = L"CyberPi v0.1";
    Bitmap* titleBmp = cyber.create_text(title, white, 16);
    if (titleBmp) {
        cyber.set_bitmap(10, 10, titleBmp);
        free(titleBmp->buffer);
        free(titleBmp);
    }

    wchar_t status[] = L"Display OK!";
    Bitmap* statusBmp = cyber.create_text(status, cyber.swap_color(cyber.color24_to_16(0x000000)), 12);
    if (statusBmp) {
        cyber.set_bitmap(20, 108, statusBmp);
        free(statusBmp->buffer);
        free(statusBmp);
    }

    cyber.render_lcd();
    Serial.println("Display rendered — you should see colored bands + text");

    // Set all LEDs to green to indicate success
    for (int i = 0; i < 5; i++) {
        cyber.set_rgb(i, 0, 50, 0);
    }
}

void loop() {
    if (Serial.available()) {
        String input = Serial.readStringUntil('\n');
        input.trim();
        Serial.print("Echo: ");
        Serial.println(input);
    }
    delay(10);
}
```

- [ ] **Step 2: Build and flash**

```bash
cd firmware && pio run --target upload
```

Expected: Upload completes. Display shows 4 colored bands (red/green/blue/white) with "CyberPi v0.1" in white text and "Display OK!" in black text. LEDs turn green.

- [ ] **Step 3: Verify via serial monitor**

```bash
cd firmware && pio device monitor
```

Expected:
```
=== CyberPi Custom Firmware ===
Stage 2: Display test
Hardware initialized
Display rendered — you should see colored bands + text
```

- [ ] **Step 4: Commit**

```bash
git add firmware/src/main.cpp
git commit -m "feat(firmware): stage 2 — display test with colored bands and text"
```

---

### Task 7: Stage 2b — Button and Joystick Test

**Files:**
- Modify: `firmware/src/main.cpp`

Confirm all input hardware works by showing button/joystick state on display and serial.

- [ ] **Step 1: Update main.cpp to read and display inputs**

Replace `firmware/src/main.cpp`:
```cpp
#include <Arduino.h>
#include "config.h"
#include "cyberpi.h"

CyberPi cyber;

void fillRect(uint8_t x, uint8_t y, uint8_t w, uint8_t h, uint16_t color) {
    for (uint8_t dy = 0; dy < h && (y + dy) < SCREEN_HEIGHT; dy++) {
        for (uint8_t dx = 0; dx < w && (x + dx) < SCREEN_WIDTH; dx++) {
            cyber.set_lcd_pixel(x + dx, y + dy, color);
        }
    }
}

void drawText(const wchar_t* text, uint8_t x, uint8_t y, uint16_t color, uint8_t size) {
    // create_text takes non-const; cast is safe for read-only use
    Bitmap* bmp = cyber.create_text((wchar_t*)text, color, size);
    if (bmp) {
        cyber.set_bitmap(x, y, bmp);
        free(bmp->buffer);
        free(bmp);
    }
}

uint16_t toColor(uint32_t rgb) {
    return cyber.swap_color(cyber.color24_to_16(rgb));
}

uint32_t lastUpdate = 0;

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== CyberPi Custom Firmware ===");
    Serial.println("Stage 2b: Button & joystick test");

    cyber.begin();
    Serial.println("Press buttons and move joystick...");
}

void loop() {
    uint32_t now = millis();
    if (now - lastUpdate < 100) return;  // 10Hz update
    lastUpdate = now;

    bool btnA = cyber.get_button_a();
    bool btnB = cyber.get_button_b();
    bool btnMenu = cyber.get_button_menu();
    int joyX = cyber.get_joystick_x();
    int joyY = cyber.get_joystick_y();
    bool joyPress = cyber.get_joystick_pressed();

    // Print to serial
    Serial.printf("A:%d B:%d M:%d JX:%d JY:%d JP:%d\n",
                  btnA, btnB, btnMenu, joyX, joyY, joyPress);

    // Draw on display
    uint16_t bg    = toColor(0x1A1A2E);
    uint16_t white = toColor(0xFFFFFF);
    uint16_t green = toColor(0x00FF00);
    uint16_t gray  = toColor(0x444444);

    cyber.clean_lcd();
    fillRect(0, 0, 128, 128, bg);

    drawText(L"Input Test", 20, 4, white, 14);

    // Button indicators
    drawText(L"A", 10, 30, btnA ? green : gray, 16);
    drawText(L"B", 50, 30, btnB ? green : gray, 16);
    drawText(L"Menu", 85, 30, btnMenu ? green : gray, 12);

    // Joystick state
    wchar_t jxBuf[16];
    swprintf(jxBuf, 16, L"JX: %d", joyX);
    drawText(jxBuf, 10, 60, white, 12);

    wchar_t jyBuf[16];
    swprintf(jyBuf, 16, L"JY: %d", joyY);
    drawText(jyBuf, 10, 78, white, 12);

    drawText(L"Press:", 10, 96, white, 12);
    drawText(joyPress ? L"YES" : L"no", 70, 96, joyPress ? green : gray, 12);

    cyber.render_lcd();

    // LED feedback: light up LED corresponding to joystick direction
    for (int i = 0; i < 5; i++) cyber.set_rgb(i, 0, 0, 0);

    if (joyY == -1)     cyber.set_rgb(0, 0, 0, 255);  // UP = LED 0 blue
    if (joyX == 1)      cyber.set_rgb(1, 0, 0, 255);  // RIGHT = LED 1
    if (joyY == 1)       cyber.set_rgb(2, 0, 0, 255);  // DOWN = LED 2
    if (joyX == -1)     cyber.set_rgb(3, 0, 0, 255);  // LEFT = LED 3
    if (joyPress)        cyber.set_rgb(4, 255, 0, 0);  // CENTER = LED 4 red
    if (btnA)            for (int i = 0; i < 5; i++) cyber.set_rgb(i, 0, 255, 0);  // A = all green
    if (btnB)            for (int i = 0; i < 5; i++) cyber.set_rgb(i, 255, 0, 0);  // B = all red
}
```

- [ ] **Step 2: Build and flash**

```bash
cd firmware && pio run --target upload
```

Expected: Display shows button/joystick state in real-time. LEDs respond to joystick direction.

- [ ] **Step 3: Test all inputs**

Verify each input works:
- Press Button A → display shows green "A", all LEDs green
- Press Button B → display shows green "B", all LEDs red
- Press Menu → display shows green "Menu"
- Joystick UP → JY: -1, LED 0 blue
- Joystick DOWN → JY: 1, LED 2 blue
- Joystick LEFT → JX: -1, LED 3 blue
- Joystick RIGHT → JX: 1, LED 1 blue
- Joystick CENTER press → "Press: YES", LED 4 red

- [ ] **Step 4: Commit**

```bash
git add firmware/src/main.cpp
git commit -m "feat(firmware): stage 2b — button and joystick input test verified"
```

---

### Task 8: Stage 2c — Sensor and Sound Test

**Files:**
- Modify: `firmware/src/main.cpp`

Confirm IMU, light sensor, microphone, and speaker all work.

- [ ] **Step 1: Update main.cpp to display sensor readings and play tones**

Replace `firmware/src/main.cpp`:
```cpp
#include <Arduino.h>
#include "config.h"
#include "cyberpi.h"

CyberPi cyber;

void fillRect(uint8_t x, uint8_t y, uint8_t w, uint8_t h, uint16_t color) {
    for (uint8_t dy = 0; dy < h && (y + dy) < SCREEN_HEIGHT; dy++) {
        for (uint8_t dx = 0; dx < w && (x + dx) < SCREEN_WIDTH; dx++) {
            cyber.set_lcd_pixel(x + dx, y + dy, color);
        }
    }
}

void drawText(const wchar_t* text, uint8_t x, uint8_t y, uint16_t color, uint8_t size) {
    Bitmap* bmp = cyber.create_text((wchar_t*)text, color, size);
    if (bmp) {
        cyber.set_bitmap(x, y, bmp);
        free(bmp->buffer);
        free(bmp);
    }
}

uint16_t toColor(uint32_t rgb) {
    return cyber.swap_color(cyber.color24_to_16(rgb));
}

uint32_t lastUpdate = 0;
bool tonePlayed = false;

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== CyberPi Custom Firmware ===");
    Serial.println("Stage 2c: Sensor & sound test");

    cyber.begin();
    Serial.println("Hardware initialized. Reading sensors...");

    // Play startup chime: C5, E5, G5
    cyber.set_instrument(0);  // Sine wave
    cyber.set_pitch(0, 72, 50);  // C5
    delay(200);
    cyber.set_pitch(0, 76, 50);  // E5
    delay(200);
    cyber.set_pitch(0, 79, 50);  // G5
    Serial.println("Startup chime played");
}

void loop() {
    uint32_t now = millis();
    if (now - lastUpdate < 200) return;  // 5Hz update
    lastUpdate = now;

    // Read sensors
    float pitch = cyber.get_pitch();
    float roll  = cyber.get_roll();
    float accX  = cyber.get_acc_x();
    float accY  = cyber.get_acc_y();
    float accZ  = cyber.get_acc_z();
    uint16_t light = cyber.get_light();
    int loudness   = cyber.get_loudness();

    // Print to serial
    Serial.printf("P:%.1f R:%.1f AX:%.1f AY:%.1f AZ:%.1f L:%d Loud:%d\n",
                  pitch, roll, accX, accY, accZ, light, loudness);

    // Draw on display
    uint16_t bg    = toColor(0x0F0F23);
    uint16_t white = toColor(0xFFFFFF);
    uint16_t cyan  = toColor(0x00DDFF);
    uint16_t amber = toColor(0xFFAA00);

    cyber.clean_lcd();
    fillRect(0, 0, 128, 128, bg);

    drawText(L"Sensors", 30, 4, cyan, 14);

    wchar_t buf[32];

    swprintf(buf, 32, L"Pitch: %.1f", pitch);
    drawText(buf, 4, 24, white, 11);

    swprintf(buf, 32, L"Roll:  %.1f", roll);
    drawText(buf, 4, 38, white, 11);

    swprintf(buf, 32, L"AccX:  %.1f", accX);
    drawText(buf, 4, 52, white, 11);

    swprintf(buf, 32, L"AccY:  %.1f", accY);
    drawText(buf, 4, 66, white, 11);

    swprintf(buf, 32, L"AccZ:  %.1f", accZ);
    drawText(buf, 4, 80, white, 11);

    swprintf(buf, 32, L"Light: %d", light);
    drawText(buf, 4, 97, amber, 11);

    swprintf(buf, 32, L"Loud:  %d", loudness);
    drawText(buf, 4, 111, amber, 11);

    cyber.render_lcd();

    // Button A plays a tone
    if (cyber.get_button_a() && !tonePlayed) {
        cyber.set_instrument(0);
        cyber.set_pitch(0, 60, 80);  // Middle C
        tonePlayed = true;
    }
    if (!cyber.get_button_a()) {
        tonePlayed = false;
    }
}
```

- [ ] **Step 2: Build and flash**

```bash
cd firmware && pio run --target upload
```

Expected: Display shows live sensor readings. Startup chime plays through speaker. Button A plays a tone.

- [ ] **Step 3: Verify all sensors**

- Tilt the device → pitch/roll values change
- Cover the light sensor → light value drops
- Make noise → loudness value increases
- Press Button A → tone plays through speaker
- Serial monitor shows matching values

- [ ] **Step 4: Commit**

```bash
git add firmware/src/main.cpp
git commit -m "feat(firmware): stage 2c — sensors (IMU, light, mic) and speaker verified"
```

---

### Task 9: Restore Test — Verify Stock Firmware Recovery

**Files:** None (verification only)

Before proceeding to Plan 2 (networking), verify we can restore stock firmware. This proves our safety net works.

- [ ] **Step 1: Flash the stock backup**

```bash
esptool.py --port COM6 --baud 921600 write_flash 0x0 firmware/backups/cyberpi_stock_v44.01.011.bin
```

Expected: Flash completes, device reboots into CyberOS.

- [ ] **Step 2: Verify CyberOS works**

Open serial monitor or run the Python scan:
```bash
python -c "from makeblock_explorer.transport.base import scan_serial_ports; print(scan_serial_ports())"
```

Expected: CyberPi detected on COM6, CyberOS running normally.

- [ ] **Step 3: Re-flash custom firmware**

```bash
cd firmware && pio run --target upload
```

Expected: Custom firmware boots, sensor display shows, LEDs work.

- [ ] **Step 4: Commit a note**

```bash
git commit --allow-empty -m "test: verified stock firmware restore and re-flash cycle"
```

---

## Summary

After completing all 9 tasks:
- PlatformIO toolchain is set up and builds clean
- Stock firmware is backed up (8MB, safe recovery proven)
- CyberPi Arduino SDK is integrated as a submodule
- All hardware verified working: LEDs (5x RGB), display (128x128 ST7735), buttons (A, B, Menu), joystick (5-way), IMU (pitch/roll/accel), light sensor, microphone, speaker
- Stock restore cycle tested and confirmed

**Next:** Plan 2 — Firmware Networking (WiFi, MQTT, NVS provisioning, serial F3 protocol)
