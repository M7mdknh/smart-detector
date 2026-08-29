import { useState } from "react";
import type { Incident } from "../api/types";
import { SEVERITY_COLOR, SEVERITY_ORDER, formatAge } from "../lib/format";

export function IncidentTable({
  incidents,
  nowMs,
  onReview,
}: {
  incidents: Incident[] | undefined;
  nowMs: number;
  onReview: (id: string) => void;
}) {
  const [filter, setFilter] = useState<"Active" | "Resolved">("Active");

  if (!incidents) {
    return <div className="panel skeleton">Loading incidents…</div>;
  }

  const rows = incidents
    .filter((i) => (filter === "Active" ? i.state !== "RESOLVED" : i.state === "RESOLVED"))
    .sort((a, b) => SEVERITY_ORDER[b.severity] - SEVERITY_ORDER[a.severity] || +new Date(b.updated_at) - +new Date(a.updated_at))
    .slice(0, 10);

  return (
    <div className="panel">
      <div className="panel-header">
        <span>Incidents</span>
        <div className="filter-tabs">
          {(["Active", "Resolved"] as const).map((f) => (
            <button key={f} className={f === filter ? "tab tab-active" : "tab"} onClick={() => setFilter(f)}>
              {f}
            </button>
          ))}
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="empty-state">
          {filter === "Active" ? "No active incidents. System healthy." : "No resolved incidents yet."}
        </div>
      ) : (
        <table className="incident-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Incident</th>
              <th>Zone</th>
              <th>Age</th>
              <th>State</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((i) => (
              <tr key={i.incident_id}>
                <td>
                  <span className="severity-chip" style={{ background: SEVERITY_COLOR[i.severity] }}>
                    {i.severity}
                  </span>
                </td>
                <td>{i.explanation}</td>
                <td>{i.zone_id}</td>
                <td>{formatAge(i.opened_at, nowMs)}</td>
                <td>{i.state}</td>
                <td>
                  <button className="review-btn" onClick={() => onReview(i.incident_id)}>
                    Review
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
