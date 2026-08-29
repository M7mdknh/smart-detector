import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusCards } from "../src/dashboard/StatusCards";
import type { DashboardSnapshot } from "../src/api/types";

function baseSnapshot(overrides: Partial<DashboardSnapshot> = {}): DashboardSnapshot {
  return {
    server_time: new Date().toISOString(),
    simulation: null,
    latest_reading: { value: 420, event_time: new Date().toISOString(), quality: "GOOD", source: "SIMULATOR" },
    forecast: {
      forecast_id: "f1",
      zone_id: "zone-1",
      gas: "CO2",
      generated_at: new Date().toISOString(),
      based_on_event_time: new Date().toISOString(),
      physics_model_version: "1.0",
      ml_model_version: null,
      model_status: "OK",
      gru_model_version: null,
      gru_status: "UNAVAILABLE",
      horizon_minutes: 60,
      step_minutes: 5,
      points: [],
      leak_probability: null,
      leak_label: "NO_LEAK_SIGNAL",
      calibration_version: null,
      crossings: [{ threshold_name: "NIOSH_ACTION_5000", threshold_ppm: 5000, outcome: "NO_CROSSING", minutes_to_cross: null }],
    },
    active_incidents: [],
    vision: { camera_id: "camera-1", status: "OK", model_version: "1.0", last_frame_age_seconds: 1, fps: 8, tracks: [] },
    model_versions: { physics: "1.0", risk_policy: "1.0", leak_model_status: "OK" },
    ...overrides,
  };
}

describe("StatusCards", () => {
  it("renders NO CROSSING for time-to-action when no crossing predicted", () => {
    render(<StatusCards snapshot={baseSnapshot()} nowMs={Date.now()} />);
    expect(screen.getByText("NO CROSSING")).toBeInTheDocument();
  });

  it("shows UNAVAILABLE time-to-action when there is no forecast at all", () => {
    render(<StatusCards snapshot={baseSnapshot({ forecast: null })} nowMs={Date.now()} />);
    expect(screen.getByText("UNAVAILABLE")).toBeInTheDocument();
  });

  it("never reports zero people as confirmed safe when the camera is degraded", () => {
    const snap = baseSnapshot({
      vision: { camera_id: "camera-1", status: "UNAVAILABLE", model_version: null, last_frame_age_seconds: null, fps: null, tracks: [] },
    });
    render(<StatusCards snapshot={snap} nowMs={Date.now()} />);
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("shows NORMAL overall risk with no active incidents", () => {
    render(<StatusCards snapshot={baseSnapshot()} nowMs={Date.now()} />);
    expect(screen.getByText("NORMAL")).toBeInTheDocument();
  });

  it("shows the worst active severity as overall risk", () => {
    const snap = baseSnapshot({
      active_incidents: [
        {
          incident_id: "i1", type: "CO2_ACTION_CROSSING_PREDICTED", zone_id: "zone-1", gas: "CO2", severity: "MEDIUM",
          confidence: null, state: "OPEN", opened_at: new Date().toISOString(), updated_at: new Date().toISOString(),
          acknowledged_at: null, resolved_at: null, dedup_key: "zone-1:GAS_RISK", reason_codes: [], explanation: "x",
          recommended_action: "y", version: 1,
        },
        {
          incident_id: "i2", type: "PPE_HELMET_OVERHEAD_VIOLATION", zone_id: "zone-1", gas: null, severity: "HIGH",
          confidence: null, state: "OPEN", opened_at: new Date().toISOString(), updated_at: new Date().toISOString(),
          acknowledged_at: null, resolved_at: null, dedup_key: "zone-1:PPE_HELMET_OVERHEAD_VIOLATION", reason_codes: [],
          explanation: "z", recommended_action: "w", version: 1,
        },
      ],
    });
    render(<StatusCards snapshot={snap} nowMs={Date.now()} />);
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });

  it("shows ALREADY EXCEEDED in plain language, never an AI-says-unsafe phrasing", () => {
    const snap = baseSnapshot({
      forecast: {
        ...baseSnapshot().forecast!,
        crossings: [{ threshold_name: "NIOSH_ACTION_5000", threshold_ppm: 5000, outcome: "ALREADY_EXCEEDED", minutes_to_cross: 0 }],
      },
    });
    render(<StatusCards snapshot={snap} nowMs={Date.now()} />);
    expect(screen.getByText("ALREADY EXCEEDED")).toBeInTheDocument();
    expect(screen.getByText(/CO2 has already crossed the 5000 ppm action reference/)).toBeInTheDocument();
    expect(screen.queryByText(/AI says/i)).not.toBeInTheDocument();
  });

  it("shows INSUFFICIENT DATA distinctly from NO CROSSING", () => {
    const snap = baseSnapshot({
      forecast: {
        ...baseSnapshot().forecast!,
        crossings: [{ threshold_name: "NIOSH_ACTION_5000", threshold_ppm: 5000, outcome: "INSUFFICIENT_DATA", minutes_to_cross: null }],
      },
    });
    render(<StatusCards snapshot={snap} nowMs={Date.now()} />);
    expect(screen.getByText("INSUFFICIENT DATA")).toBeInTheDocument();
  });

  it("shows FORECAST DEGRADED and keeps physics forecast noted as active when the leak model falls back", () => {
    const snap = baseSnapshot({
      forecast: { ...baseSnapshot().forecast!, model_status: "FALLBACK" },
    });
    render(<StatusCards snapshot={snap} nowMs={Date.now()} />);
    expect(screen.getByText("FORECAST DEGRADED")).toBeInTheDocument();
    expect(screen.getByText(/physics forecast remains active/)).toBeInTheDocument();
  });

  it("distinguishes hybrid (physics + GRU) from physics-only in the Time-to-Action sub-label", () => {
    const physicsOnly = baseSnapshot();
    render(<StatusCards snapshot={physicsOnly} nowMs={Date.now()} />);
    expect(screen.getByText(/\[physics/)).toBeInTheDocument();

    const hybrid = baseSnapshot({ forecast: { ...baseSnapshot().forecast!, gru_status: "OK", gru_model_version: "1.0" } });
    render(<StatusCards snapshot={hybrid} nowMs={Date.now()} />);
    expect(screen.getByText(/\[hybrid \(physics \+ GRU\)/)).toBeInTheDocument();
  });

  it("shows predicted CO2 in 60 minutes on the CO2 card when a forecast point exists", () => {
    const snap = baseSnapshot({
      forecast: {
        ...baseSnapshot().forecast!,
        points: [
          {
            horizon_minutes: 60, event_time: new Date().toISOString(), physics_ppm: 900,
            residual_ppm: null, predicted_ppm: 900, lower_ppm: null, upper_ppm: null,
          },
        ],
      },
    });
    render(<StatusCards snapshot={snap} nowMs={Date.now()} />);
    expect(screen.getByText(/in 60min: 900 ppm/)).toBeInTheDocument();
  });
});
