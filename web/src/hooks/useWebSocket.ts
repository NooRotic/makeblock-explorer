"use client";

import { useEffect, useRef, useState } from "react";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8333/api/stream";

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const [sensorData, setSensorData] = useState<
    Record<string, Record<string, number>>
  >({});
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        ws.send(JSON.stringify({ type: "subscribe", device_id: "all" }));
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data as string) as {
            type: string;
            device_id: string;
            data: Record<string, number>;
          };
          if (msg.type === "sensor" && msg.device_id) {
            setSensorData((prev) => ({
              ...prev,
              [msg.device_id]: msg.data,
            }));
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        reconnectTimer.current = setTimeout(connect, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  return { isConnected, sensorData };
}
