import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { DashboardSnapshot } from "../api/types";

interface ChartPoint {
  t: number;
  label: string;
  observed?: number;
  physicsForecast?: number;
  hybridForecast?: number;
  uncertaintyRange?: [number, number]; // recharts "range area": [low, high]
  source?: string;
  quality?: string;
}

export function GasChart({ snapshot }: { snapshot: DashboardSnapshot | undefined }) {
  const eventTime = snapshot?.latest_reading?.event_time;
  const from = useMemo(() => {
    const base = eventTime ? new Date(eventTime) : new Date();
    return new Date(base.getTime() - 2 * 3600 * 1000).toISOString();
  }, [eventTime]);
  const to = eventTime ?? new Date().toISOString();

  const scenarioId = snapshot?.simulation?.scenario_id;
  const historyQuery = useQuery({
    queryKey: ["zone-readings", from, to, scenarioId],
    queryFn: () => api.zoneReadings("zone-1", "CO2", from, to, scenarioId),
    enabled: !!snapshot,
  });

  if (!snapshot) {
    return <div className="panel chart-panel skeleton">Loading chart…</div>;
  }

  const nowMs = eventTime ? new Date(eventTime).getTime() : Date.now();
  const history = historyQuery.data?.readings ?? [];
  const forecastPoints = snapshot.forecast?.points ?? [];
  const gruActive = snapshot.forecast?.gru_status === "OK";

  const data: ChartPoint[] = [
    ...history.map((r) => ({
      t: new Date(r.event_time).getTime(),
      label: new Date(r.event_time).toLocaleTimeString(),
      observed: r.value,
      source: r.source,
      quality: r.quality,
    })),
    ...forecastPoints.map((p) => ({
      t: new Date(p.event_time).getTime(),
      label: new Date(p.event_time).toLocaleTimeString(),
      // Physics baseline is always shown; the hybrid (physics + GRU residual) line is
      // only distinct from physics when the GRU actually corrected this point --
      // otherwise predicted_ppm === physics_ppm and only one dashed line is visible.
      physicsForecast: p.physics_ppm,
      hybridForecast: gruActive ? p.predicted_ppm : undefined,
      uncertaintyRange: (gruActive && p.lower_ppm != null && p.upper_ppm != null ? [p.lower_ppm, p.upper_ppm] : undefined) as
        | [number, number]
        | undefined,
    })),
  ].sort((a, b) => a.t - b.t);

  const modelFallback = snapshot.forecast?.model_status === "FALLBACK";

  return (
    <div className="panel chart-panel">
      <div className="panel-header">
        <span>CO2 concentration — history &amp; forecast</span>
        <span className="chart-badges">
          {modelFallback && <span className="badge badge-fallback">Physics fallback (leak model)</span>}
          {gruActive ? (
            <span className="badge badge-ok">Hybrid forecast (physics + GRU)</span>
          ) : (
            <span className="badge badge-fallback">Physics-only forecast</span>
          )}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3a" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} interval="preserveStartEnd" minTickGap={40} />
          <YAxis tick={{ fontSize: 11 }} width={60} />
          <Tooltip
            formatter={(value, name) => [`${Math.round(Number(value))} ppm`, String(name)]}
            labelFormatter={(_, payload) => {
              const p = payload?.[0]?.payload as ChartPoint | undefined;
              return p ? `${p.label}${p.source ? ` · ${p.source}${p.quality ? ` · ${p.quality}` : ""}` : " · forecast"}` : "";
            }}
          />
          <ReferenceLine y={1000} stroke="#5b7fa6" strokeDasharray="2 2" label={{ value: "Advisory 1000", fontSize: 10, fill: "#5b7fa6" }} />
          <ReferenceLine y={5000} stroke="#c98a1d" strokeDasharray="2 2" label={{ value: "Action 5000", fontSize: 10, fill: "#c98a1d" }} />
          <ReferenceLine y={30000} stroke="#d9622b" strokeDasharray="2 2" label={{ value: "Short-term 30000", fontSize: 10, fill: "#d9622b" }} />
          <ReferenceLine y={40000} stroke="#c62828" strokeDasharray="2 2" label={{ value: "IDLH 40000", fontSize: 10, fill: "#c62828" }} />
          <ReferenceLine x={data.find((d) => d.t >= nowMs)?.label} stroke="#e5e7eb" label={{ value: "Now", fontSize: 10, fill: "#e5e7eb" }} />
          {gruActive && (
            <Area
              type="monotone"
              dataKey="uncertaintyRange"
              stroke="none"
              fill="#6fb3ff"
              fillOpacity={0.12}
              isAnimationActive={false}
              name="uncertainty band"
              connectNulls={false}
            />
          )}
          <Line type="monotone" dataKey="observed" stroke="#6fb3ff" dot={false} strokeWidth={2} isAnimationActive={false} connectNulls={false} name="observed" />
          <Line type="monotone" dataKey="physicsForecast" stroke="#9aa0a6" strokeDasharray="4 3" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls={false} name="physics forecast" />
          {gruActive && (
            <Line type="monotone" dataKey="hybridForecast" stroke="#3fb98c" strokeDasharray="5 2" dot={false} strokeWidth={2} isAnimationActive={false} connectNulls={false} name="hybrid (physics + GRU)" />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
