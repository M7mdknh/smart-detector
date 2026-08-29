# Assessment Acceptance Matrix

Read this reference when writing end-to-end tests, evaluating release readiness, or rehearsing the assessment demonstration.

## P0 Scenarios

| ID | Setup/action | Required observable result |
|---|---|---|
| A01 | `make demo` in a clean environment | Backend, frontend, SQLite migrations, seeded scenario, bundled replay, and UI start without credentials |
| A02 | Load `normal`, advance 60 simulated min | Persisted readings/forecast visible; no false gas incident |
| A03 | Load `gradual_leak`, advance until forecast crossing | XGBoost probability and physics forecast update; one MEDIUM predicted-action incident opens with TTA/evidence |
| A04 | Move worker into gas zone during A03 | Same incident or linked exposure incident becomes HIGH with person reason; no duplicate per tick |
| A05 | Raise source toward IDLH-imminent condition | CRITICAL state and immediate human recommendation; audit records escalation |
| A06 | Acknowledge -> investigate -> resolve with comments | Valid transitions persist; refresh/restart retains state and complete audit |
| A07 | Load `ventilation_failure` | Physics predicts rise; classifier/policy records known ventilation cause and does not blindly call it a leak |
| A08 | Worker without helmet remains in overhead zone | After dwell, one HIGH helmet incident tied to anonymous track/ground truth provenance |
| A09 | Remove vest in mandatory-PPE zone | After dwell, one MEDIUM vest incident; ambiguous association remains UNKNOWN |
| A10 | Duplicate reading/evidence/command | Idempotent result and no duplicate incident/audit side effect |
| A11 | Remove/corrupt XGBoost artifact | System shows degraded model, physics/rules continue, no ingestion crash |
| A12 | Stop camera/replay frames | Camera/model status degraded; UI does not claim zero workers/safe scene |
| A13 | Disconnect/reconnect WebSocket | Reconnecting status, REST snapshot, then ordered updates without duplication |
| A14 | Restart backend after opening incident | Active incident, readings, forecast, versions, and audit remain available |
| A15 | Invalid incident transition or stale version | Typed 409/validation response; no partial audit/state mutation |
| A16 | Run `make test`, `make e2e`, `make evaluate`, `make lint` | Commands succeed and reported artifacts/metrics are reproducible |

## Calculation Cases

- Constant-parameter analytic forecast matches a known solution.
- Current value already above threshold returns `ALREADY_EXCEEDED` and zero minutes.
- Rising steady state below threshold returns `NO_CROSSING`.
- Falling concentration does not report a rising crossing.
- Zero ventilation uses a safe numerical/source accumulation path, not division by zero.
- Negative volume/flow, wrong unit, non-finite reading, and invalid logarithm input are rejected/typed.
- Rolling 15-minute and eight-hour exposure calculations handle irregular event times.
- Partial eight-hour history is labelled `PARTIAL_WINDOW`.

## Model/Data Leakage Cases

- Split manifest proves no scenario ID/seed crosses train/validation/test.
- Feature timestamps are never after label cutoff.
- Calibration does not use the test split.
- Normal ventilation/machine transitions appear in every split.
- Artifact registry checksum and feature schema are verified at startup.

## Vision Cases

- Actual replay inference is labelled `CV_MODEL`; deterministic simulation evidence is `SIMULATION_GROUND_TRUTH`.
- PPE boxes associate to at most one person.
- Single-frame missed helmet/vest does not open an incident.
- Zone and PPE dwell use timestamps.
- Occluded/ambiguous PPE state is `UNKNOWN`.
- Tracker loss does not fabricate persistent worker identity.

## Documentation Gate

The submission includes:

- exact setup/run/test/evaluate commands;
- architecture/data-flow diagram matching code;
- assumptions and technical decisions;
- sensor, leak-model, forecast, vision, latency, and system metrics;
- model/data versions, checksums, licences, and source URLs;
- threshold source and correct TWA/ST/IDLH language;
- security/privacy, reliability, monitoring/logging, audit behavior;
- limitations: synthetic-to-real gap, construction-to-factory PPE gap, well-mixed assumption, camera occlusion, no safety certification;
- production improvements and approximate compute/storage cost;
- AI tool disclosure.

## Demo Rehearsal

The primary demonstration should take fewer than eight minutes:

1. Start app and show healthy/degraded component status.
2. Show normal warm history and the separate camera provenance.
3. Trigger gradual leak and explain physics, probability, forecast, and TTA.
4. Move worker into the zone and show evidence-based severity escalation.
5. Review/acknowledge/resolve and show audit persistence.
6. Briefly demonstrate one fallback/failure.
7. Show reproducible tests/evaluation and limitations.

Prepare one small live change such as adjusting configured PPE dwell or a policy threshold through versioned configuration, with a focused test. Do not rehearse a scope-expanding feature.
