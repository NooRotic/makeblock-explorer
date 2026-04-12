"""DeviceManager: manages a single serial connection to a MakeBlock device."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable

import serial

from makeblock_explorer.protocol.f3 import (
    F3Response,
    Mode,
    ONLINE_MODE_PACKET,
    build_f3_packet,
    parse_f3_response,
)

logger = logging.getLogger(__name__)

BAUD_RATE = 115200
HANDSHAKE_PROBE = "cyberpi.get_bri()"
BOOT_WAIT_SECONDS = 4.0
HANDSHAKE_TIMEOUT = 2.0

DEFAULT_SENSOR_COMMANDS: dict[str, str] = {
    "brightness": "cyberpi.get_bri()",
    "battery": "cyberpi.get_battery()",
    "pitch": "cyberpi.get_pitch()",
    "roll": "cyberpi.get_roll()",
    "accel_x": 'cyberpi.get_acc("x")',
    "accel_y": 'cyberpi.get_acc("y")',
    "accel_z": 'cyberpi.get_acc("z")',
}


class DeviceManager:
    """Manages a single serial connection to a MakeBlock device."""

    def __init__(self) -> None:
        self.port: str | None = None
        self.device_id: str | None = None
        self.device_type: str = "unknown"
        self.sensor_cache: dict[str, Any] = {}

        self._serial: serial.Serial | None = None
        self._index: int = 0
        self._poll_task: asyncio.Task | None = None
        self._subscribers: dict[str, Callable[[dict], None]] = {}

    @property
    def is_connected(self) -> bool:
        """True when the serial port is open and active."""
        return self._serial is not None and self._serial.is_open

    def _make_device_id(self, port: str) -> str:
        return f"device-{port}"

    def _next_index(self) -> int:
        """Return incrementing counter, wrapping at 0xFFFF."""
        idx = self._index
        self._index = (self._index + 1) % 0xFFFF
        return idx

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, port: str) -> None:
        """Open serial port and perform device handshake."""
        self._serial = serial.Serial(
            port=port,
            baudrate=BAUD_RATE,
            bytesize=8,
            stopbits=1,
            parity="N",
            timeout=1.0,
        )
        self.port = port
        self.device_id = self._make_device_id(port)

        await asyncio.to_thread(self._reset_device)
        await asyncio.to_thread(self._handshake)

    def _reset_device(self) -> None:
        """Toggle DTR/RTS lines to reset the ESP32, then drain boot output."""
        if self._serial is None:
            return
        try:
            self._serial.dtr = False
            self._serial.rts = False
            time.sleep(0.1)
            self._serial.dtr = True
            self._serial.rts = True
            time.sleep(0.1)
            self._serial.dtr = False
            self._serial.rts = False
        except Exception:
            logger.debug("DTR/RTS toggle failed — continuing", exc_info=True)

        # Wait for the ESP32 boot sequence to complete
        time.sleep(BOOT_WAIT_SECONDS)

        # Drain any boot output
        try:
            self._serial.reset_input_buffer()
        except Exception:
            logger.debug("Failed to drain boot output", exc_info=True)

    def _handshake(self) -> None:
        """Perform F3 protocol handshake sequence."""
        if self._serial is None:
            return

        # 1. Send probe packet
        probe_packet = build_f3_packet(HANDSHAKE_PROBE, self._next_index(), Mode.WITH_RESPONSE)
        try:
            self._serial.write(probe_packet)
        except Exception:
            logger.debug("Probe write failed", exc_info=True)

        time.sleep(1.5)

        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass

        # 2. Switch to online mode
        try:
            self._serial.write(ONLINE_MODE_PACKET)
        except Exception:
            logger.debug("Online mode packet write failed", exc_info=True)

        time.sleep(0.5)

        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass

        # 3. Sync read — send brightness query to confirm link
        sync_packet = build_f3_packet(HANDSHAKE_PROBE, self._next_index(), Mode.WITH_RESPONSE)
        try:
            self._serial.write(sync_packet)
        except Exception:
            logger.debug("Sync packet write failed", exc_info=True)

        time.sleep(0.8)

        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass

    async def disconnect(self) -> None:
        """Cancel polling, close serial port and clear state."""
        if self._poll_task is not None and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                logger.debug("Error closing serial port", exc_info=True)

        self._serial = None
        self.port = None
        self.device_id = None
        self.sensor_cache = {}

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    async def execute(self, script: str, expect_response: bool = True) -> F3Response | None:
        """Send a MicroPython script command and optionally wait for a response."""
        if not self.is_connected:
            raise ConnectionError("Device is not connected")

        mode = Mode.WITH_RESPONSE if expect_response else Mode.WITHOUT_RESPONSE
        packet = build_f3_packet(script, self._next_index(), mode)

        return await asyncio.to_thread(self._send_and_receive, packet, expect_response)

    def _send_and_receive(self, packet: bytes, expect_response: bool) -> F3Response | None:
        """Blocking: write packet and read response bytes (2 s timeout)."""
        if self._serial is None:
            return None

        # Drain any stale bytes from previous responses before sending
        try:
            self._serial.reset_input_buffer()
        except Exception:
            pass

        self._serial.write(packet)

        if not expect_response:
            return None

        # Accumulate incoming bytes until we parse a response or time out
        deadline = time.monotonic() + HANDSHAKE_TIMEOUT
        buf = b""

        while time.monotonic() < deadline:
            try:
                chunk = self._serial.read(self._serial.in_waiting or 1)
            except Exception:
                break
            if chunk:
                buf += chunk
                responses = parse_f3_response(buf)
                if responses:
                    return responses[0]

        return None

    # ------------------------------------------------------------------
    # Sensor polling
    # ------------------------------------------------------------------

    async def start_sensor_polling(self, hz: float = 5.0) -> None:
        """Start background task that polls sensors at the given frequency."""
        if self._poll_task is not None and not self._poll_task.done():
            return  # already running
        self._poll_task = asyncio.create_task(self._poll_loop(hz))

    async def _poll_loop(self, hz: float) -> None:
        """Continuously read DEFAULT_SENSOR_COMMANDS and update sensor_cache."""
        interval = 1.0 / hz if hz > 0 else 1.0
        while True:
            for key, cmd in DEFAULT_SENSOR_COMMANDS.items():
                if not self.is_connected:
                    return
                try:
                    response = await self.execute(cmd, expect_response=True)
                    if response is not None and response.value is not None:
                        self.sensor_cache[key] = response.value
                except Exception:
                    logger.debug("Polling error for %s", key, exc_info=True)

            # Notify all subscribers
            snapshot = dict(self.sensor_cache)
            for callback in list(self._subscribers.values()):
                try:
                    callback(snapshot)
                except Exception:
                    logger.debug("Subscriber callback error", exc_info=True)

            await asyncio.sleep(interval)

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[dict], None]) -> str:
        """Register a callback for sensor updates. Returns subscription ID."""
        sub_id = str(uuid.uuid4())
        self._subscribers[sub_id] = callback
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        """Remove a subscription by ID."""
        self._subscribers.pop(sub_id, None)
