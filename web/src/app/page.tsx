"use client";

import { useCallback, useEffect, useState } from "react";
import {
  connectDevice,
  disconnectDevice,
  DeviceInfo,
  DeviceStatus,
  getStatus,
  scanDevices,
} from "@/lib/api";
import { DeviceCard } from "@/components/DeviceCard";
import { useWebSocket } from "@/hooks/useWebSocket";

export default function DashboardPage() {
  const { isConnected, sensorData } = useWebSocket();
  const [availableDevices, setAvailableDevices] = useState<DeviceInfo[]>([]);
  const [connectedDevices, setConnectedDevices] = useState<DeviceStatus[]>([]);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const devices = await getStatus();
      setConnectedDevices(devices);
    } catch {
      // silently fail status refresh
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 5000);
    return () => clearInterval(interval);
  }, [refreshStatus]);

  async function handleScan() {
    setScanning(true);
    setError(null);
    try {
      const devices = await scanDevices();
      setAvailableDevices(devices);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  async function handleConnect(port: string) {
    try {
      await connectDevice(port);
      await refreshStatus();
      setAvailableDevices([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connect failed");
    }
  }

  async function handleDisconnect(deviceId: string) {
    try {
      await disconnectDevice(deviceId);
      await refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Disconnect failed");
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">MakeBlock Explorer</h1>
          <p className="text-sm text-gray-500 mt-0.5">CyberPi Device Dashboard</p>
        </div>
        <div className="flex items-center gap-4">
          {/* WebSocket status */}
          <div className="flex items-center gap-1.5 text-xs">
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? "bg-green-500" : "bg-red-500"
              }`}
            />
            <span className="text-gray-400">
              {isConnected ? "Live" : "Offline"}
            </span>
          </div>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="px-4 py-2 text-sm rounded-md bg-blue-700 hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {scanning ? "Scanning\u2026" : "Scan Devices"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 text-sm px-4 py-2 rounded-md">
          {error}
        </div>
      )}

      {/* Available devices */}
      {availableDevices.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Available Devices
          </h2>
          <div className="space-y-2">
            {availableDevices.map((d) => (
              <div
                key={d.port}
                className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-lg px-4 py-3"
              >
                <div>
                  <p className="text-sm text-gray-200">{d.description}</p>
                  <p className="text-xs text-gray-500">{d.port}</p>
                </div>
                <button
                  onClick={() => handleConnect(d.port)}
                  className="text-sm px-3 py-1.5 rounded bg-green-800 hover:bg-green-700 text-green-200 transition-colors"
                >
                  Connect
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Connected devices */}
      <section>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Connected Devices{" "}
          <span className="text-gray-600">({connectedDevices.length})</span>
        </h2>
        {connectedDevices.length === 0 ? (
          <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-8 text-center">
            <p className="text-gray-500 text-sm">No devices connected.</p>
            <p className="text-gray-600 text-xs mt-1">
              Click &quot;Scan Devices&quot; to discover CyberPi devices.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {connectedDevices.map((device) => (
              <DeviceCard
                key={device.device_id}
                device={device}
                sensorData={sensorData[device.device_id]}
                onDisconnect={handleDisconnect}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
