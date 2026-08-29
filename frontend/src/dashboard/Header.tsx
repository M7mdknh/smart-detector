import { Link } from "react-router-dom";
import type { ConnectionStatus } from "../lib/useWebSocket";
import type { DashboardSnapshot } from "../api/types";
import { formatClock } from "../lib/format";

export function Header({ snapshot, connection }: { snapshot: DashboardSnapshot | undefined; connection: ConnectionStatus }) {
  const sim = snapshot?.simulation;
  return (
    <header className="app-header">
      <div className="brand">Factory Safety Sentinel</div>
      <div className="header-meta">
        <span>{sim ? `${sim.preset} · ${formatClock(sim.event_time)}` : "no scenario loaded"}</span>
        <span className={`conn-badge conn-${connection.toLowerCase()}`}>{connection}</span>
        <span className="badge badge-provenance">{sim ? "SIMULATION" : "—"}</span>
        <Link to="/simulation" className="nav-link">
          Simulation
        </Link>
      </div>
    </header>
  );
}
