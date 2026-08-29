# API and Data Specification

Read this reference when creating or changing routes, persistence, WebSocket events, incident state, or frontend/backend contracts.

## REST Surface

All routes use `/api/v1`. Return `{error:{code,message,details,correlation_id}}` for failures.

| Method and route | Purpose | Important behavior |
|---|---|---|
| `GET /health/live` | Process liveness | No database/model inference |
| `GET /health/ready` | Dependency readiness | Database plus required P0 modules |
| `GET /system/status` | Sensor, camera, model, simulator status | Returns `HEALTHY`, `DEGRADED`, or `UNAVAILABLE` per component |
| `POST /sensor-readings` | Public reading ingestion | Idempotent by `reading_id`; validates unit/event time |
| `GET /zones/{zone_id}/readings` | Chart history | Requires `gas`, `from`, `to`; bounded page size |
| `GET /zones/{zone_id}/forecast/latest` | Latest 60-minute forecast | Includes model/fallback state and typed crossings |
| `GET /vision/latest` | Latest annotated evidence projection | Does not return raw frames from persistence |
| `GET /incidents` | Filtered incident list | Filters for state, severity, type, zone; cursor pagination |
| `GET /incidents/{id}` | Incident and referenced evidence | Includes explanation and allowed next actions |
| `POST /incidents/{id}/actions` | Human workflow command | Body includes action, actor, comment, expected version |
| `GET /incidents/{id}/audit` | Append-only incident history | Chronological events |
| `GET /dashboard/snapshot` | Atomic dashboard boot/reconnect view | Cards, chart tail, camera status, incidents, versions |
| `GET /simulation/state` | Authoritative simulator state | Includes event clock and seed |
| `POST /simulation/scenarios/{id}/load` | Warm-start a preset | Returns accepted operation and resulting state version |
| `POST /simulation/commands` | Pause/resume/reset/speed/controls | Idempotent by `command_id`; optimistic state version |

Do not create separate REST routes for each card. `/dashboard/snapshot` prevents inconsistent initial reads while normal history/detail routes remain available.

## WebSocket

Use `/api/v1/ws`. On connection, the client sends or receives a monotonically increasing event sequence. After a disconnect, fetch `/dashboard/snapshot` before applying new events.

Event envelope:

```json
{
  "schema_version": "1.0",
  "event_id": "uuid",
  "sequence": 123,
  "type": "forecast.updated",
  "event_time": "2026-01-01T10:05:00Z",
  "published_at": "2026-01-01T10:05:00.250Z",
  "correlation_id": "uuid",
  "payload": {}
}
```

Allowed P0 event types:

- `sensor.reading.created`
- `forecast.updated`
- `vision.evidence.updated`
- `incident.created`
- `incident.updated`
- `incident.audit.created`
- `simulation.state.updated`
- `system.status.updated`

The WebSocket transports projections of committed backend state. Publish after the database transaction commits.

## Tables

### `sensor_readings`

Primary key `reading_id`; indexed by `(zone_id, gas, event_time)`. Store value as finite real, canonical unit, event/ingestion times, source, quality, scenario, sequence, correlation, and raw fault marker. Reject duplicate IDs with conflicting payloads.

### `forecasts`

Primary key `forecast_id`; indexed by `(zone_id, gas, generated_at)`. Store the input cutoff, model/fallback status, versions, probability/calibration metadata, crossing outcomes, and serialized or child-table horizon points. Forecast points remain immutable.

### `vision_evidence`

Primary key `evidence_id`; indexed by `(camera_id, event_time)` and `(track_id, event_time)`. Store normalized boxes and derived PPE/zone state, not biometric embeddings. Raw frames remain transient demo assets, not database blobs.

### `incidents`

Primary key `incident_id`; unique active deduplication key; indexed by state/severity/update time. Store current projection and optimistic `version`. Resolved incidents remain queryable.

### `incident_evidence`

Join table from incidents to immutable reading, forecast, vision, or rule-decision references. Include evidence type, ID, and association reason.

### `audit_events`

Append-only primary key `audit_id`; indexed by incident and timestamp. Application code receives no update/delete repository method.

### `simulation_runs` and `simulation_commands`

Store run/scenario/seed/generator version, current simulation state, clock and speed. Commands store `command_id`, expected/resulting state version, actor, payload, and time for reproducible replay.

### `model_registry`

Store logical name, semantic version, artifact path, SHA-256, training-data version, config version, metrics file, load status, and loaded time. Runtime startup validates checksums.

## Transaction Boundaries

- Ingestion transaction: validate -> insert reading -> commit. Forecast/risk work may follow asynchronously, but P0 can execute in-process through a bounded job queue.
- Incident transaction: upsert/deduplicate incident -> attach evidence -> append audit -> commit -> publish event.
- Human action transaction: lock/check expected version -> validate transition -> update incident -> append audit -> commit -> publish.
- Simulation command transaction: check command id/state version -> persist command/new state -> commit -> emit resulting observations through normal ingestion.

## Idempotency and Ordering

- A repeated identical `reading_id` or `command_id` returns the original success.
- A repeated ID with a different payload returns `409 IDEMPOTENCY_CONFLICT`.
- Readings older than the configured lateness window are persisted with `LATE` quality but do not silently rewrite an already-issued current forecast. A deliberate replay/recalculation command is separate.
- Sequence gaps mark the sensor stream degraded; they do not manufacture readings.
- Incident actions require `expected_version`; stale updates return `409 VERSION_CONFLICT`.

## Typed Failures

At minimum define: `VALIDATION_ERROR`, `UNKNOWN_GAS`, `UNIT_MISMATCH`, `INVALID_EVENT_TIME`, `IDEMPOTENCY_CONFLICT`, `VERSION_CONFLICT`, `INVALID_TRANSITION`, `MODEL_UNAVAILABLE`, `INSUFFICIENT_DATA`, and `SIMULATION_STATE_CONFLICT`.

## Backend Module Boundaries

```text
api -> application services -> domain policies -> repositories/adapters
```

- Domain policy has no FastAPI, SQLAlchemy, React, or model-package imports.
- Inference adapters return domain results and typed failures.
- Repositories isolate database models from Pydantic API contracts.
- Simulation calls application ingestion services instead of repositories directly.
- Frontend types are generated from OpenAPI or checked by contract fixtures in CI.

## Required Integration Tests

1. Identical duplicate reading is idempotent; conflicting duplicate is rejected.
2. One reading produces persisted forecast/risk output and a correctly ordered WebSocket event.
3. Repeated evidence updates one active incident rather than creating duplicates.
4. Human transition and audit append are atomic.
5. Backend restart retains active incidents and audit history.
6. WebSocket reconnect snapshot and subsequent sequence do not double-apply events.
