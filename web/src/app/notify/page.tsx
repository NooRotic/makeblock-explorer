"use client";

import { useEffect, useState } from "react";
import { getStatus, DeviceStatus, pushNotify } from "@/lib/api";

function hexToRgb(hex: string): [number, number, number] {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)]
    : [0, 0, 0];
}

interface NotificationRecord {
  id: number;
  deviceId: string;
  text: string;
  color: string;
  size: number;
  flashLeds: boolean;
  timestamp: string;
}

const FONT_SIZES = [16, 20, 24, 28, 32];

export default function NotifyPage() {
  const [devices, setDevices] = useState<DeviceStatus[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [text, setText] = useState("");
  const [color, setColor] = useState("#ffffff");
  const [fontSize, setFontSize] = useState(20);
  const [flashLeds, setFlashLeds] = useState(false);
  const [history, setHistory] = useState<NotificationRecord[]>([]);
  const [sending, setSending] = useState(false);
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

  async function handleSend() {
    if (!selectedId || !text.trim()) return;
    setSending(true);
    setError(null);
    try {
      await pushNotify(selectedId, text, hexToRgb(color), fontSize, flashLeds);
      const record: NotificationRecord = {
        id: Date.now(),
        deviceId: selectedId,
        text,
        color,
        size: fontSize,
        flashLeds,
        timestamp: new Date().toLocaleTimeString(),
      };
      setHistory((prev) => [record, ...prev].slice(0, 5));
      setFeedback("Notification sent!");
      setTimeout(() => setFeedback(null), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send notification");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-100">Push Notification</h1>

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

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-4">
        {/* Device selector */}
        <div className="space-y-1">
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

        {/* Text input */}
        <div className="space-y-1">
          <div className="flex justify-between items-center">
            <label className="text-sm font-semibold text-gray-300">
              Message
            </label>
            <span
              className={`text-xs ${
                text.length > 30 ? "text-red-400" : "text-gray-500"
              }`}
            >
              {text.length}/30
            </span>
          </div>
          <input
            type="text"
            maxLength={30}
            placeholder="Enter notification text..."
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder-gray-600"
          />
        </div>

        {/* Colour + font size row */}
        <div className="flex items-center gap-6 flex-wrap">
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-400">Colour</label>
            <input
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              className="w-10 h-8 rounded cursor-pointer border border-gray-700 bg-gray-800"
            />
            <span className="text-xs text-gray-500 font-mono">{color}</span>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-400">Font size</label>
            <select
              value={fontSize}
              onChange={(e) => setFontSize(Number(e.target.value))}
              className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded-md px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {FONT_SIZES.map((s) => (
                <option key={s} value={s}>
                  {s}pt
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Flash LEDs */}
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={flashLeds}
            onChange={(e) => setFlashLeds(e.target.checked)}
            className="w-4 h-4 rounded accent-blue-500"
          />
          <span className="text-sm text-gray-300">Flash LEDs</span>
        </label>

        <button
          onClick={handleSend}
          disabled={!selectedId || !text.trim() || sending}
          className="w-full py-2.5 text-sm font-semibold rounded-md bg-blue-700 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {sending ? "Sending\u2026" : "Send to CyberPi"}
        </button>
      </div>

      {/* History */}
      {history.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Recent Notifications
          </h2>
          <div className="space-y-2">
            {history.map((rec) => (
              <div
                key={rec.id}
                className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-lg px-4 py-3"
              >
                <div className="flex items-center gap-3">
                  <span
                    className="w-3 h-3 rounded-full border border-gray-600 shrink-0"
                    style={{ backgroundColor: rec.color }}
                  />
                  <div>
                    <p className="text-sm text-gray-200">{rec.text}</p>
                    <p className="text-xs text-gray-500">
                      {rec.size}pt
                      {rec.flashLeds ? " · flash LEDs" : ""}
                    </p>
                  </div>
                </div>
                <span className="text-xs text-gray-600 shrink-0">
                  {rec.timestamp}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
