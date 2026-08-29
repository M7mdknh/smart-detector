import type {
  DashboardSnapshot,
  Forecast,
  Incident,
  AuditEvent,
  SimulationState,
  SensorReadingOut,
  VisionZoneConfig,
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api/v1";
export const WS_BASE = import.meta.env.VITE_WS_BASE ?? "ws://127.0.0.1:8000/api/v1/ws";

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;
  status: number;
  constructor(code: string, message: string, status: number, details: Record<string, unknown>) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let body: { error?: { code: string; message: string; details?: Record<string, unknown> } } = {};
    try {
      body = await res.json();
    } catch {
      // non-JSON error body
    }
    const err = body.error ?? { code: "UNKNOWN_ERROR", message: res.statusText };
    throw new ApiError(err.code, err.message, res.status, err.details ?? {});
  }
  return res.json() as Promise<T>;
}

export const api = {
  dashboardSnapshot: () => request<DashboardSnapshot>("/dashboard/snapshot"),
  zoneForecastLatest: (zoneId: string) => request<Forecast>(`/zones/${zoneId}/forecast/latest`),
  zoneReadings: (zoneId: string, gas: string, from: string, to: string, scenarioId?: string) =>
    request<{ zone_id: string; gas: string; readings: SensorReadingOut[] }>(
      `/zones/${zoneId}/readings?gas=${gas}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}` +
        (scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""),
    ),
  listIncidents: (params?: { state?: string; severity?: string }) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return request<Incident[]>(`/incidents${q ? `?${q}` : ""}`);
  },
  getIncident: (id: string) => request<Incident>(`/incidents/${id}`),
  incidentAudit: (id: string) => request<AuditEvent[]>(`/incidents/${id}/audit`),
  incidentAction: (id: string, body: { action: string; actor: string; comment?: string; expected_version: number }) =>
    request<Incident>(`/incidents/${id}/actions`, { method: "POST", body: JSON.stringify(body) }),
  simulationState: () => request<SimulationState>("/simulation/state"),
  simulationPresets: () => request<{ presets: string[] }>("/simulation/presets"),
  loadScenario: (preset: string, seed?: number) =>
    request<{ accepted: boolean; state: SimulationState }>(`/simulation/scenarios/${preset}/load${seed ? `?seed=${seed}` : ""}`, {
      method: "POST",
    }),
  simulationCommand: (command: string, payload: Record<string, unknown> = {}, expectedVersion?: number) =>
    request<SimulationState>("/simulation/commands", {
      method: "POST",
      body: JSON.stringify({
        command_id: crypto.randomUUID(),
        command,
        payload,
        expected_state_version: expectedVersion,
      }),
    }),
  systemStatus: () => request<Record<string, string>>("/system/status"),
  visionZones: () => request<VisionZoneConfig>("/vision/zones"),
};
