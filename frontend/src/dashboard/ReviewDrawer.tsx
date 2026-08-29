import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useIncidentAction, useIncidentAudit, useIncidentDetail } from "./hooks";
import { SEVERITY_COLOR, formatClock } from "../lib/format";
import { api, ApiError, API_BASE } from "../api/client";

const ACTION_LABEL: Record<string, string> = {
  ACKNOWLEDGE: "Acknowledge",
  INVESTIGATE: "Start investigating",
  RESOLVE: "Resolve",
};

export function ReviewDrawer({ incidentId, onClose }: { incidentId: string | null; onClose: () => void }) {
  const { data: incident, isLoading } = useIncidentDetail(incidentId);
  const { data: audit } = useIncidentAudit(incidentId);
  const mutation = useIncidentAction(incidentId);
  const qc = useQueryClient();
  const [comment, setComment] = useState("");
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);

  if (!incidentId) return null;

  // A background risk-policy tick (e.g. a severity change from live sensor/CV
  // evidence -- the vision worker re-evaluates PPE/zone risk on every
  // processed frame, ~10/sec, independent of anything the reviewer does) can
  // legitimately bump `incident.version` between when this drawer's data was
  // fetched and when the reviewer clicks a button. This is optimistic
  // concurrency working as intended, not a bug. Retry with the freshly
  // re-fetched version resolves that ordinary race transparently instead of
  // surfacing a conflict the reviewer did nothing to cause. Bounded to a
  // small number of attempts (not unbounded): under genuinely contested,
  // rapid changes this still surfaces to the reviewer rather than retrying
  // forever, and a bounded retry cannot mask a real, non-concurrency failure
  // (any other error code still surfaces on the first attempt).
  const MAX_VERSION_CONFLICT_RETRIES = 3;

  function act(action: string, expectedVersion?: number, attempt = 0) {
    if (!incident) return;
    if (attempt === 0) setConflictMessage(null);
    mutation.mutate(
      { action, comment: comment || undefined, expected_version: expectedVersion ?? incident.version },
      {
        onSuccess: () => setComment(""),
        onError: async (err) => {
          if (err instanceof ApiError && err.code === "VERSION_CONFLICT" && attempt < MAX_VERSION_CONFLICT_RETRIES) {
            const fresh = await qc.fetchQuery({ queryKey: ["incident", incidentId], queryFn: () => api.getIncident(incidentId as string) });
            qc.setQueryData(["incident", incidentId], fresh);
            act(action, fresh.version, attempt + 1);
          } else if (err instanceof ApiError && err.code === "VERSION_CONFLICT") {
            setConflictMessage("This incident keeps changing faster than the retry could keep up — please review the latest state and try again.");
          } else if (err instanceof ApiError) {
            setConflictMessage(err.message);
          }
        },
      },
    );
  }

  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <div
        className="drawer"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Incident review"
        aria-modal="true"
        data-incident-id={incident?.incident_id}
      >
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
