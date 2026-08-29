import type { DashboardSnapshot } from "../api/types";
import { SEVERITY_COLOR, SEVERITY_ORDER, formatMinutes, formatPpm, isStale } from "../lib/format";

function Card({ label, value, sub, tone }: { label: string; value: string; sub: string; tone?: string }) {
  return (
    <div className="card" style={tone ? { borderLeftColor: tone } : undefined}>
      <div className="card-label">{label}</div>
      <div className="card-value">{value}</div>
      <div className="card-sub">{sub}</div>
    </div>
  );
}

export function StatusCards({ snapshot, nowMs }: { snapshot: DashboardSnapshot | undefined; nowMs: number }) {
  if (!snapshot) {
    return (
      <div className="card-row">
        {["Overall risk", "CO2", "Time-to-Action", "People at risk"].map((l) => (
          <div className="card card-skeleton" key={l}>
            <div className="card-label">{l}</div>
            <div className="card-value">…</div>
          </div>
        ))}
      </div>
    );
  }

  const active = snapshot.active_incidents;
  const worstSeverity = active.length
    ? active.reduce((worst, i) => (SEVERITY_ORDER[i.severity] > SEVERITY_ORDER[worst] ? i.severity : worst), active[0].severity)
    : null;

  const reading = snapshot.latest_reading;
  const readingStale = reading ? isStale(reading.event_time, nowMs, 600) : true;

  const forecast = snapshot.forecast;
  const actionCrossing = forecast?.crossings.find((c) => c.threshold_name === "NIOSH_ACTION_5000");

  // Plain-language Time-to-Action text, per the required examples ("CO2 may reach the
  // 5000 ppm action reference in 34 minutes.", never "AI says unsafe").
  let ttaValue = "NO CROSSING";
  let ttaSub = "No configured threshold crossing predicted within 60 minutes.";
  if (!forecast) {
    ttaValue = "UNAVAILABLE";
    ttaSub = "No forecast available yet.";
  } else if (actionCrossing) {
    switch (actionCrossing.outcome) {
      case "ALREADY_EXCEEDED":
        ttaValue = "ALREADY EXCEEDED";
        ttaSub = "CO2 has already crossed the 5000 ppm action reference.";
        break;
      case "CROSSING_EXPECTED":
        ttaValue = formatMinutes(actionCrossing.minutes_to_cross);
        ttaSub = `CO2 may reach the 5000 ppm action reference in ${formatMinutes(actionCrossing.minutes_to_cross)}.`;
        break;
      case "NO_CROSSING":
        ttaValue = "NO CROSSING";
        ttaSub = "No configured threshold crossing predicted within 60 minutes.";
        break;
      case "INSUFFICIENT_DATA":
        ttaValue = "INSUFFICIENT DATA";
        ttaSub = "Not enough recent history to forecast a crossing yet.";
        break;
      default:
        ttaValue = "UNAVAILABLE";
        ttaSub = "Forecast crossing could not be evaluated.";
    }
  }
  if (forecast?.model_status === "FALLBACK") {
    ttaValue = "FORECAST DEGRADED";
    ttaSub = "Leak-probability model unavailable; physics forecast remains active.";
  }
  const forecastModelLabel = forecast?.gru_status === "OK" ? "hybrid (physics + GRU)" : "physics";
  const forecastFreshness = forecast ? isStale(forecast.generated_at, nowMs, 600) : true;

  const camera = snapshot.vision;
  const cameraDegraded = camera.status !== "OK" && camera.status !== "HEALTHY";
  const confirmedTracks = camera.tracks.filter((t) => t.detected_class === "person" && t.gas_zone_membership === "INSIDE");

  // Predicted CO2 in 60 minutes (last forecast point) and simple trend, for the CO2
  // card's secondary line -- current vs. projected risk shown separately, not merged.
  const lastPoint = forecast?.points[forecast.points.length - 1];
  const predicted60 = lastPoint ? Math.round(lastPoint.predicted_ppm) : null;
  const trend = reading && predicted60 != null ? predicted60 - reading.value : null;
  const trendLabel = trend == null ? "" : trend > 50 ? "rising" : trend < -50 ? "falling" : "steady";

  return (
    <div className="card-row">
      <Card
        label="Overall risk"
        value={worstSeverity ?? "NORMAL"}
        sub={`${active.length} active incident${active.length === 1 ? "" : "s"}`}
        tone={worstSeverity ? SEVERITY_COLOR[worstSeverity] : "#3f9142"}
      />
      <Card
        label="CO2"
        value={reading ? formatPpm(reading.value) : "UNKNOWN"}
        sub={
          reading
            ? `${readingStale ? "STALE · " : ""}${reading.source} · ${reading.quality}` +
              (predicted60 != null ? ` · in 60min: ${predicted60} ppm (${trendLabel})` : "")
            : "no data"
        }
        tone={readingStale ? "#9aa0a6" : undefined}
      />
      <Card
        label="Time-to-Action"
        value={ttaValue}
        sub={`${ttaSub} [${forecastModelLabel}${forecastFreshness ? ", stale" : ""}]`}
      />
      <Card
        label="People at risk"
        value={cameraDegraded ? "UNKNOWN" : String(confirmedTracks.length)}
        sub={cameraDegraded ? "camera degraded" : "confirmed in gas zone"}
        tone={cameraDegraded ? "#9aa0a6" : undefined}
      />
    </div>
  );
}
