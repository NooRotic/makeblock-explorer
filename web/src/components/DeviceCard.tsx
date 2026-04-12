"use client";

import { DeviceStatus } from "@/lib/api";

interface SensorBarProps {
  label: string;
  value: number;
  max: number;
  color: string;
  unit?: string;
}

function SensorBar({ label, value, max, color, unit }: SensorBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>{label}</span>
        <span>
          {value.toFixed(1)}
          {unit}
        </span>
      </div>
      <div className="w-full bg-gray-700 rounded-full h-2">
        <div
          className="h-2 rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

interface SensorValueProps {
  label: string;
  value: number;
  unit: string;
}

function SensorValue({ label, value, unit }: SensorValueProps) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-gray-700 last:border-0">
      <span className="text-xs text-gray-400">{label}</span>
      <span className="text-sm font-mono text-gray-200">
        {value.toFixed(2)}
        <span className="text-gray-500 ml-1">{unit}</span>
      </span>
    </div>
  );
}

interface DeviceCardProps {
  device: DeviceStatus;
  sensorData?: Record<string, number>;
  onDisconnect: (deviceId: string) => void;
}

export function DeviceCard({ device, sensorData, onDisconnect }: DeviceCardProps) {
  const sensors = sensorData ?? device.sensor_cache ?? {};

  const brightness = sensors["brightness"] ?? 0;
  const battery = sensors["battery"] ?? 0;
  const pitch = sensors["pitch"] ?? 0;
  const roll = sensors["roll"] ?? 0;
  const accelX = sensors["accel_x"] ?? 0;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-green-500 shadow-[0_0_6px_#22c55e]" />
          <div>
            <p className="text-sm font-semibold text-gray-100">
              {device.device_type}
            </p>
            <p className="text-xs text-gray-500">{device.port}</p>
          </div>
        </div>
        <button
          onClick={() => onDisconnect(device.device_id)}
          className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-400 hover:bg-red-900 hover:text-red-300 transition-colors"
        >
          Disconnect
        </button>
      </div>

      {/* Sensor bars */}
      <div className="space-y-1">
        <SensorBar
          label="Brightness"
          value={brightness}
          max={100}
          color="#eab308"
        />
        <SensorBar
          label="Battery"
          value={battery}
          max={100}
          color="#22c55e"
          unit="%"
        />
      </div>

      {/* Sensor values */}
      <div className="bg-gray-800 rounded-md px-3 py-2">
        <SensorValue label="Pitch" value={pitch} unit="°" />
        <SensorValue label="Roll" value={roll} unit="°" />
        <SensorValue label="Accel X" value={accelX} unit="g" />
      </div>
    </div>
  );
}
