import { useQuery } from "@tanstack/react-query";
import type { VisionStatus } from "../api/types";
import { formatAge } from "../lib/format";
import { api } from "../api/client";

const ZONE_COLOR: Record<string, string> = {
  GAS_EXPOSURE: "#c62828",
  OVERHEAD_WORK: "#c98a1d",
  MANDATORY_VEST: "#6fb3ff",
};

function ZoneOverlay() {
  const { data } = useQuery({ queryKey: ["vision-zones"], queryFn: api.visionZones, staleTime: 60_000 });
  if (!data) return null;

  return (
    <svg className="zone-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Configured camera zones">
      {data.zones.map((z) => (
        <polygon
          key={z.id}
          points={z.points.map(([x, y]) => `${x * 100},${y * 100}`).join(" ")}
          fill={ZONE_COLOR[z.type] ?? "#888"}
          fillOpacity={0.12}
          stroke={ZONE_COLOR[z.type] ?? "#888"}
          strokeOpacity={0.6}
          strokeWidth={0.5}
        >
          <title>{z.label}</title>
        </polygon>
      ))}
    </svg>
  );
}

export function CameraPanel({ vision, nowMs }: { vision: VisionStatus | undefined; nowMs: number }) {
  const { data: zoneConfig } = useQuery({ queryKey: ["vision-zones"], queryFn: api.visionZones, staleTime: 60_000 });

  if (!vision) {
    return <div className="panel camera-panel skeleton">Loading camera…</div>;
  }

  const degraded = vision.status !== "OK" && vision.status !== "HEALTHY";

  return (
    <div className="panel camera-panel">
      <div className="panel-header">
        <span>Camera — {vision.camera_id}</span>
        <span className={`badge ${degraded ? "badge-degraded" : "badge-ok"}`}>{vision.status}</span>
      </div>
      <div className="camera-frame">
        <ZoneOverlay />
        {degraded ? (
          <div className="camera-unavailable">
            <p>Camera/model unavailable.</p>
            <p className="muted">Worker presence cannot be confirmed as safe from this feed.</p>
          </div>
        ) : (
          <div className="camera-tracks">
            {vision.tracks.length === 0 && <p className="muted">No detections in the latest frames.</p>}
            {vision.tracks.slice(0, 5).map((t) => (
              <div key={t.evidence_id} className="track-row">
                <span className="track-label">
                  {t.detected_class === "person" ? `Worker #${t.track_id ?? "?"}` : t.detected_class}
                </span>
                <span className="track-meta">
                  helmet: {t.helmet_state} · vest: {t.vest_state} · gas zone: {t.gas_zone_membership} · overhead zone: {t.overhead_zone_membership}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="camera-footer">
        <span>source: CV_MODEL</span>
        <span>model: {vision.model_version ?? "--"}</span>
        <span>last frame: {formatAge(vision.tracks[0]?.event_time, nowMs)}</span>
        <span>fps: {vision.fps ? vision.fps.toFixed(1) : "--"}</span>
      </div>
      <div className="camera-zones muted">
        configured zones (v{zoneConfig?.version ?? "?"}): {zoneConfig?.zones.map((z) => z.label).join(" · ") ?? "loading…"}
      </div>
    </div>
  );
}
