import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { ThreeScene } from "./ThreeScene";
import { formatClock } from "../lib/format";

const PRESETS = ["normal", "gradual_leak", "ventilation_failure", "worker_exposure", "overhead_ppe", "sensor_fault"];
const SPEEDS = [1, 10, 60, 300];

export function SimulationPage() {
  const qc = useQueryClient();
  const { data: state } = useQuery({
    queryKey: ["simulation-state"],
    queryFn: api.simulationState,
    refetchInterval: 2000,
    retry: false,
  });

  const [advancedOpen, setAdvancedOpen] = useState(false);

  const loadMutation = useMutation({
    mutationFn: (preset: string) => api.loadScenario(preset),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["simulation-state"] }),
  });

  const cmdMutation = useMutation({
    mutationFn: ({ command, payload }: { command: string; payload?: Record<string, unknown> }) =>
      api.simulationCommand(command, payload, state?.state_version),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["simulation-state"] }),
  });

  function cmd(command: string, payload: Record<string, unknown> = {}) {
    cmdMutation.mutate({ command, payload });
  }

  return (
    <div className="page">
      <header className="app-header">
        <div className="brand">Factory Safety Sentinel</div>
        <div className="header-meta">
          <span>{state ? `${state.preset} · ${formatClock(state.event_time)} · ${state.state}` : "no scenario loaded"}</span>
          <span className="badge badge-provenance">SIMULATION GROUND TRUTH</span>
          <Link to="/dashboard" className="nav-link">
            Dashboard
          </Link>
        </div>
      </header>

      <main className="simulation-main">
        <ThreeScene state={state} onFloorClick={(x, y) => cmd("set_worker", { x, y })} />

        <div className="sim-controls">
          <section>
            <h3>Scenario</h3>
            <div className="control-row">
              {PRESETS.map((p) => (
                <button key={p} disabled={loadMutation.isPending} onClick={() => loadMutation.mutate(p)}>
                  {p}
                </button>
              ))}
            </div>
          </section>

          <section>
            <h3>Playback</h3>
            <div className="control-row">
              <button onClick={() => cmd("start")} disabled={!state}>
                Start
              </button>
              <button onClick={() => cmd("pause")} disabled={!state}>
                Pause
              </button>
              <button onClick={() => cmd("reset")} disabled={!state}>
                Reset
              </button>
              {SPEEDS.map((s) => (
                <button key={s} className={state?.speed === s ? "tab-active" : ""} onClick={() => cmd("set_speed", { speed: s })} disabled={!state}>
                  {s}x
                </button>
              ))}
            </div>
          </section>

          <section>
            <h3>Gas &amp; ventilation</h3>
            <label>
              Emission source: {state ? Math.round(state.source_ppm_m3_per_h).toLocaleString() : "--"} ppm·m³/h
              <input
                type="range"
                min={0}
                max={8_000_000}
                step={50_000}
                value={state?.source_ppm_m3_per_h ?? 0}
                onChange={(e) => cmd("set_controls", { source_ppm_m3h: Number(e.target.value) })}
                disabled={!state}
              />
            </label>
            <label>
              Ventilation: {state ? Math.round(state.ventilation_m3_per_h) : "--"} m³/h
              <input
                type="range"
                min={0}
                max={1000}
                step={10}
                value={state?.ventilation_m3_per_h ?? 500}
                onChange={(e) => cmd("set_controls", { ventilation_m3h: Number(e.target.value) })}
                disabled={!state}
              />
            </label>
          </section>

          <section>
            <h3>Worker</h3>
            <div className="control-row">
              <label>
                <input type="checkbox" checked={state?.worker_helmet ?? false} onChange={(e) => cmd("set_worker", { helmet: e.target.checked })} disabled={!state} />
                Helmet
              </label>
              <label>
                <input type="checkbox" checked={state?.worker_vest ?? false} onChange={(e) => cmd("set_worker", { vest: e.target.checked })} disabled={!state} />
                Vest
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={state?.overhead_zone_active ?? false}
                  onChange={(e) => cmd("set_worker", { overhead_active: e.target.checked })}
                  disabled={!state}
                />
                Overhead work active
              </label>
            </div>
            <p className="muted">Click the floor above to move the worker.</p>
          </section>

          <section>
            <button className="advanced-toggle" onClick={() => setAdvancedOpen((v) => !v)}>
              Advanced test controls {advancedOpen ? "▲" : "▼"}
            </button>
            {advancedOpen && (
              <div className="control-row">
                <button onClick={() => loadMutation.mutate("sensor_fault")}>Load sensor-fault preset</button>
                <span className="muted">Sensor override / fault injection is scenario-preset only in this build.</span>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
