"use client";

import { useEffect, useState } from "react";
import { getStatus, DeviceStatus, setLed, executeCommand } from "@/lib/api";

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      }
    : { r: 0, g: 0, b: 0 };
}

export default function ControlsPage() {
  const [devices, setDevices] = useState<DeviceStatus[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [ledColor, setLedColor] = useState("#ff0000");
  const [displayText, setDisplayText] = useState("");
  const [displayColor, setDisplayColor] = useState("#ffffff");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getStatus()
      .then((devs) => {
        setDevices(devs);
        if (devs.length > 0) setSelectedId(devs[0].device_id);
      })
      .catch(() => {});
  }, []);

  function showFeedback(msg: string) {
    setFeedback(msg);
    setTimeout(() => setFeedback(null), 2500);
  }

  function showError(msg: string) {
    setError(msg);
    setTimeout(() => setError(null), 4000);
  }

  async function handleSetLed() {
    if (!selectedId) return;
    const { r, g, b } = hexToRgb(ledColor);
    try {
      await setLed(selectedId, r, g, b);
      showFeedback("LED colour set");
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to set LED");
    }
  }

  async function handleLedOff() {
    if (!selectedId) return;
    try {
      await setLed(selectedId, 0, 0, 0);
      showFeedback("LED turned off");
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to turn off LED");
    }
  }

  async function handleShowText() {
    if (!selectedId || !displayText.trim()) return;
    const { r, g, b } = hexToRgb(displayColor);
    const script = `cyberpi.display.show_label("${displayText}", color=(${r},${g},${b}))`;
    try {
      await executeCommand(selectedId, script);
      showFeedback("Text sent to display");
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to show text");
    }
  }

  async function handleClear() {
    if (!selectedId) return;
    try {
      await executeCommand(selectedId, "cyberpi.display.clear()");
      showFeedback("Display cleared");
    } catch (e) {
      showError(e instanceof Error ? e.message : "Failed to clear display");
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-100">Device Controls</h1>

      {feedback && (
        <div className="bg-green-900/40 border border-green-700 text-green-300 text-sm px-4 py-2 rounded-md">
          {feedback}
        </div>
      )}
      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 text-sm px-4 py-2 rounded-md">
          {error}
        </div>
      )}

      {/* Device selector */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
        <label className="text-sm font-semibold text-gray-300">Device</label>
        {devices.length === 0 ? (
          <p className="text-sm text-gray-500">No connected devices found.</p>
        ) : (
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {devices.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                {d.device_type} &mdash; {d.port}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* LED section */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
        <h2 className="text-base font-semibold text-gray-200">LED Control</h2>
        <div className="flex items-center gap-3">
          <label className="text-sm text-gray-400">Colour</label>
          <input
            type="color"
            value={ledColor}
            onChange={(e) => setLedColor(e.target.value)}
            className="w-10 h-8 rounded cursor-pointer border border-gray-700 bg-gray-800"
          />
          <span className="text-xs text-gray-500 font-mono">{ledColor}</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleSetLed}
            disabled={!selectedId}
            className="px-4 py-2 text-sm rounded-md bg-blue-700 hover:bg-blue-600 disabled:opacity-40 transition-colors"
          >
            Set
          </button>
          <button
            onClick={handleLedOff}
            disabled={!selectedId}
            className="px-4 py-2 text-sm rounded-md bg-gray-700 hover:bg-gray-600 disabled:opacity-40 transition-colors"
          >
            Off
          </button>
        </div>
      </div>

      {/* Display section */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
        <h2 className="text-base font-semibold text-gray-200">Display</h2>
        <div className="space-y-2">
          <input
            type="text"
            placeholder="Text to display"
            value={displayText}
            onChange={(e) => setDisplayText(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder-gray-600"
          />
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-400">Colour</label>
            <input
              type="color"
              value={displayColor}
              onChange={(e) => setDisplayColor(e.target.value)}
              className="w-10 h-8 rounded cursor-pointer border border-gray-700 bg-gray-800"
            />
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleShowText}
            disabled={!selectedId || !displayText.trim()}
            className="px-4 py-2 text-sm rounded-md bg-blue-700 hover:bg-blue-600 disabled:opacity-40 transition-colors"
          >
            Show Text
          </button>
          <button
            onClick={handleClear}
            disabled={!selectedId}
            className="px-4 py-2 text-sm rounded-md bg-gray-700 hover:bg-gray-600 disabled:opacity-40 transition-colors"
          >
            Clear
          </button>
        </div>
      </div>
    </div>
  );
}
