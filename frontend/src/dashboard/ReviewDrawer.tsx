import { useState } from "react";
import { useIncidentAction, useIncidentAudit, useIncidentDetail } from "./hooks";
import { SEVERITY_COLOR, formatClock } from "../lib/format";
import { ApiError, API_BASE } from "../api/client";

const ACTION_LABEL: Record<string, string> = {
  ACKNOWLEDGE: "Acknowledge",
  INVESTIGATE: "Start investigating",
  RESOLVE: "Resolve",
};

export function ReviewDrawer({ incidentId, onClose }: { incidentId: string | null; onClose: () => void }) {
  const { data: incident, isLoading } = useIncidentDetail(incidentId);
  const { data: audit } = useIncidentAudit(incidentId);
  const mutation = useIncidentAction(incidentId);
  const [comment, setComment] = useState("");
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);

  if (!incidentId) return null;

  function act(action: string) {
    if (!incident) return;
    setConflictMessage(null);
    mutation.mutate(
      { action, comment: comment || undefined, expected_version: incident.version },
      {
        onSuccess: () => setComment(""),
        onError: (err) => {
          if (err instanceof ApiError && err.code === "VERSION_CONFLICT") {
            setConflictMessage("This incident changed since you loaded it. Refreshed — please retry.");
          } else if (err instanceof ApiError) {
            setConflictMessage(err.message);
          }
        },
      },
    );
  }

  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <div className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Incident review" aria-modal="true">
        <button className="drawer-close" onClick={onClose} aria-label="Close review drawer">
          ×
        </button>
        {isLoading || !incident ? (
          <p>Loading…</p>
        ) : (
          <>
            <div className="drawer-header">
              <span className="severity-chip" style={{ background: SEVERITY_COLOR[incident.severity] }}>
                {incident.severity}
              </span>
              <h2>{incident.type}</h2>
              <span className="muted">Updated {formatClock(incident.updated_at)}</span>
            </div>

            <section>
              <h3>Explanation</h3>
              <p>{incident.explanation}</p>
              <p className="muted">Reason codes: {incident.reason_codes.join(", ")}</p>
            </section>

            <section>
              <h3>Recommended action</h3>
              <p>{incident.recommended_action}</p>
            </section>

            <section>
              <h3>Evidence</h3>
              {incident.evidence && incident.evidence.length > 0 ? (
                <ul>
                  {incident.evidence.map((e, idx) => (
                    <li key={idx}>
                      {e.evidence_type}: {e.evidence_id} — {e.reason}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No linked evidence records.</p>
              )}
              {incident.evidence_images && incident.evidence_images.length > 0 && (
                <div className="evidence-images">
                  {incident.evidence_images.map((img) => (
                    <div key={img.id} className="evidence-image-item">
                      <a href={`${API_BASE}${img.url}`} target="_blank" rel="noreferrer">
                        <img
                          src={`${API_BASE}${img.url}`}
                          alt={`Evidence snapshot (${img.reason})`}
                          className="evidence-thumbnail"
                        />
                      </a>
                      <p className="muted">
                        {img.reason} — track {img.track_id ?? "unknown"} — {formatClock(img.created_at)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
              <div className="action-row">
                <a href={`${API_BASE}/incidents/${incident.incident_id}/report.json`} target="_blank" rel="noreferrer">
                  <button type="button">Download report (JSON)</button>
                </a>
                <a href={`${API_BASE}/incidents/${incident.incident_id}/report.csv`} target="_blank" rel="noreferrer">
                  <button type="button">Download report (CSV)</button>
                </a>
              </div>
            </section>

            <section>
              <h3>Comment &amp; actions</h3>
              {conflictMessage && <p className="conflict-banner">{conflictMessage}</p>}
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Add a comment (optional)"
                rows={3}
              />
              <div className="action-row">
                {(incident.allowed_actions ?? []).filter((a) => a !== "COMMENT").map((a) => (
                  <button key={a} disabled={mutation.isPending} onClick={() => act(a)}>
                    {ACTION_LABEL[a] ?? a}
                  </button>
                ))}
                <button disabled={mutation.isPending || !comment} onClick={() => act("COMMENT")}>
                  Add comment
                </button>
              </div>
            </section>

            <section>
              <h3>Audit history</h3>
              <ul className="audit-list">
                {(audit ?? []).map((a) => (
                  <li key={a.audit_id}>
                    <strong>{a.action}</strong> by {a.actor} at {formatClock(a.timestamp)}
                    {a.comment && <div className="muted">{a.comment}</div>}
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
