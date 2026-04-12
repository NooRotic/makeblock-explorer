const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface DeviceInfo {
  port: string;
  description: string;
  vid: number | null;
  pid: number | null;
}

export interface DeviceStatus {
  device_id: string;
  port: string;
  device_type: string;
  is_connected: boolean;
  sensor_cache: Record<string, number>;
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function scanDevices(): Promise<DeviceInfo[]> {
  const data = await apiFetch<{ devices: DeviceInfo[] }>("/api/devices");
  return data.devices;
}

export async function connectDevice(port: string): Promise<void> {
  await apiFetch("/api/connect", {
    method: "POST",
    body: JSON.stringify({ port }),
  });
}

export async function disconnectDevice(deviceId: string): Promise<void> {
  await apiFetch("/api/disconnect", {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId }),
  });
}

export async function getStatus(): Promise<DeviceStatus[]> {
  const data = await apiFetch<{ devices: DeviceStatus[] }>("/api/status");
  return data.devices;
}

export async function getSensors(
  deviceId: string
): Promise<Record<string, number>> {
  return apiFetch<Record<string, number>>(`/api/sensors/${deviceId}`);
}

export async function executeCommand(
  deviceId: string,
  script: string
): Promise<unknown> {
  return apiFetch("/api/command", {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId, script }),
  });
}

export async function setLed(
  deviceId: string,
  r: number,
  g: number,
  b: number,
  ledId?: number
): Promise<void> {
  await apiFetch("/api/led", {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId, r, g, b, led_id: ledId }),
  });
}

export async function pushNotify(
  deviceId: string,
  text: string,
  color: string,
  size: number,
  flashLeds: boolean
): Promise<void> {
  await apiFetch("/api/notify", {
    method: "POST",
    body: JSON.stringify({
      device_id: deviceId,
      text,
      color,
      size,
      flash_leds: flashLeds,
    }),
  });
}
