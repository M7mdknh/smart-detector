import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WS_BASE } from "../api/client";
import type { WsEvent } from "../api/types";

export type ConnectionStatus = "Live" | "Reconnecting" | "Offline";

const EVENT_TO_QUERY_KEYS: Record<string, string[][]> = {
  "sensor.reading.created": [["dashboard-snapshot"], ["zone-readings"]],
  "forecast.updated": [["dashboard-snapshot"]],
  "vision.evidence.updated": [["dashboard-snapshot"]],
  "incident.created": [["dashboard-snapshot"], ["incidents"]],
  "incident.updated": [["dashboard-snapshot"], ["incidents"], ["incident"]],
  "incident.audit.created": [["incident-audit"]],
  "simulation.state.updated": [["dashboard-snapshot"], ["simulation-state"]],
  "system.status.updated": [["system-status"]],
};

/**
 * Applies events strictly by sequence number. A gap (or first connection)
 * triggers a snapshot refetch before further events are trusted, per
 * dashboard-specification.md's reconnect rule.
 */
export function useLiveConnection(): ConnectionStatus {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<ConnectionStatus>("Offline");
  const lastSequence = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retryDelay = useRef(1000);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      if (cancelled) return;
      const ws = new WebSocket(WS_BASE);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("Live");
        retryDelay.current = 1000;
        lastSequence.current = null;
        queryClient.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
      };

      ws.onmessage = (evt) => {
        try {
          const parsed: WsEvent = JSON.parse(evt.data);
          const expectedNext = lastSequence.current === null ? parsed.sequence : lastSequence.current + 1;
          if (parsed.sequence !== expectedNext) {
            // Gap detected: refetch snapshot before trusting further events.
            queryClient.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
          }
          lastSequence.current = parsed.sequence;

          const keys = EVENT_TO_QUERY_KEYS[parsed.type] ?? [];
          for (const key of keys) {
            queryClient.invalidateQueries({ queryKey: key });
          }
        } catch {
          // ignore malformed frame
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        setStatus("Reconnecting");
        retryTimer = setTimeout(connect, retryDelay.current);
        retryDelay.current = Math.min(retryDelay.current * 2, 10000);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, [queryClient]);

  return status;
}
