export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type IncidentState = "OPEN" | "ACKNOWLEDGED" | "INVESTIGATING" | "RESOLVED";
export type CrossingOutcome = "ALREADY_EXCEEDED" | "CROSSING_EXPECTED" | "NO_CROSSING" | "INSUFFICIENT_DATA" | "INVALID_PARAMETERS";
export type ModelStatus = "OK" | "FALLBACK" | "UNAVAILABLE";
export type SimState = "UNLOADED" | "READY" | "RUNNING" | "PAUSED" | "RESETTING";

export interface Crossing {
  threshold_name: string;
  threshold_ppm: number;
  outcome: CrossingOutcome;
  minutes_to_cross: number | null;
}

export interface ForecastPoint {
  horizon_minutes: number;
  event_time: string;
  physics_ppm: number;
  residual_ppm: number | null;
  predicted_ppm: number;
  lower_ppm: number | null;
  upper_ppm: number | null;
}

export interface Forecast {
  forecast_id: string;
  zone_id: string;
  gas: string;
  generated_at: string;
  based_on_event_time: string;
  physics_model_version: string;
  ml_model_version: string | null;
  model_status: ModelStatus;
  gru_model_version: string | null;
  gru_status: ModelStatus;
  horizon_minutes: number;
  step_minutes: number;
  points: ForecastPoint[];
  leak_probability: number | null;
  leak_label: string | null;
  calibration_version: string | null;
  crossings: Crossing[];
}

export interface Incident {
  incident_id: string;
  type: string;
  zone_id: string;
  gas: string | null;
  severity: Severity;
  confidence: number | null;
  state: IncidentState;
  opened_at: string;
  updated_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  dedup_key: string;
  reason_codes: string[];
  explanation: string;
  recommended_action: string;
  version: number;
  evidence?: { evidence_type: string; evidence_id: string; reason: string }[];
  evidence_images?: {
    id: string;
    incident_id: string;
    created_at: string;
    reason: string;
    track_id: number | null;
    ppe_helmet_state: string | null;
    ppe_vest_state: string | null;
    confidence: number | null;
    model_version: string;
    source: string;
    source_frame_id: number | null;
    sha256: string;
    url: string;
  }[];
  allowed_actions?: string[];
}

export interface AuditEvent {
  audit_id: string;
  incident_id: string;
  actor: string;
  action: string;
  timestamp: string;
  previous_state: string | null;
  new_state: string | null;
  comment: string | null;
  correlation_id: string | null;
}

export interface SimulationState {
  run_id: string;
  scenario_id: string;
  preset: string;
  seed: number;
  generator_version: string;
  state: SimState;
  speed: number;
  state_version: number;
  event_time: string;
  zone_volume_m3: number;
  inlet_co2_ppm: number;
  source_ppm_m3_per_h: number;
  ventilation_m3_per_h: number;
  worker_x: number;
  worker_y: number;
  worker_helmet: boolean;
  worker_vest: boolean;
  overhead_zone_active: boolean;
  camera_status: string;
  sensor_fault: string | null;
}

export interface VisionTrack {
  evidence_id: string;
  track_id: number | null;
  detected_class: string;
  confidence: number;
  bbox: [number, number, number, number];
  helmet_state: string;
  vest_state: string;
  gas_zone_membership: string;
  overhead_zone_membership: string;
  event_time: string;
}

export interface VisionStatus {
  camera_id: string;
  status: string;
  model_version: string | null;
  last_frame_age_seconds: number | null;
  fps: number | null;
  tracks: VisionTrack[];
}

export interface VisionZone {
  id: string;
  type: "GAS_EXPOSURE" | "OVERHEAD_WORK" | "MANDATORY_VEST";
  label: string;
  points: [number, number][];
}

export interface VisionZoneConfig {
  version: string;
  camera_id: string;
  zones: VisionZone[];
}

export interface DashboardSnapshot {
  server_time: string;
  simulation: SimulationState | null;
  latest_reading: { value: number; event_time: string; quality: string; source: string } | null;
  forecast: Forecast | null;
  active_incidents: Incident[];
  vision: VisionStatus;
  model_versions: { physics: string; risk_policy: string; leak_model_status: string };
}

export interface SensorReadingOut {
  reading_id: string;
  sensor_id: string;
  zone_id: string;
  scenario_id: string;
  gas: string;
  value: number;
  unit: string;
  event_time: string;
  ingested_at: string;
  source: string;
  quality: string;
}

export interface WsEvent {
  schema_version: string;
  event_id: string;
  sequence: number;
  type: string;
  event_time: string;
  published_at: string;
  correlation_id: string;
  payload: Record<string, unknown>;
}
