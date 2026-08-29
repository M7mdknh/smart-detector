# Factory Safety Sentinel — Demonstration Script

11 steps, each with the exact UI control or API route (verified against
`frontend/src/simulation/SimulationPage.tsx`, `frontend/src/dashboard/*.tsx`,
and `backend/app/api/routes.py` — no invented control names) and the expected
visible result. This rehearses the Definition of Done in `CLAUDE.md`.

**Screenshot status**: no screenshots are bundled under `demo-assets/` or
`docs/` at the time of this audit (only `replay.mp4`,
`replay_natural_motion.mp4`, and their `*_SOURCE.md` provenance files exist
in `demo-assets/`). Capturing real screenshots requires a headed browser,
which is not available in this sandbox — `docs/FINAL_VERIFICATION.md` already
covers a full live clean-environment run (`make setup && make demo`, both
servers reachable, API responses inspected) as the closest available
substitute for this pass. Where useful below, a `curl` illustration is given
instead of a screenshot; these are commands a reviewer can run against a
live `make demo` instance, not something executed by this audit (no stack
was started in this pass).

## 1. Start the app

```bash
make setup   # first time only
make demo
```

Expected: `Backend: http://127.0.0.1:8000` and
`Frontend: http://127.0.0.1:5173` printed; `curl http://127.0.0.1:8000/health/live`
returns `{"status":"ok"}`. Open `http://127.0.0.1:5173/dashboard` — the
compact header shows the product name, a connection indicator, and (once a
scenario is loaded) the scenario clock.

## 2. Show normal history

Navigate to `/simulation`. Under **Scenario**, click the `normal` preset
button (calls `POST /api/v1/simulation/scenarios/normal/load`). Expected:
the header shows `normal · <clock> · <state>`, and the isometric scene
renders with a `SIMULATION GROUND TRUTH` badge. Switch to `/dashboard`: the
gas history/forecast chart (left of the main row) shows ten simulated hours
(120 points at 5-minute cadence) of seeded CO2 history around ~450 ppm, and
the **CO2** status card shows a current value near the seeded baseline with
no active incidents in the table below ("No active incidents. System
healthy.").

## 3. Start a gradual leak

Back on `/simulation`, click the `gradual_leak` preset button, then click
**Start** under **Playback** (`POST /api/v1/simulation/commands` with
`{"command":"start"}`). Optionally raise speed via the `10x`/`60x`/`300x`
buttons to accelerate simulated time. Expected: the scene clock advances;
the **Emission source** slider under **Gas & ventilation** reflects the
preset's rising `source_ppm_m3_per_h` value.

## 4. Show physics + hybrid prediction

On `/dashboard`, watch the gas history/forecast chart's forecast segment
extend past the current reading. Illustration via API:

```bash
curl http://127.0.0.1:8000/api/v1/zones/gas_zone_1/forecast/latest
```

Expected: a `Forecast` object with 12 points (60 min horizon, 5 min step),
each carrying separate `physics_ppm`, `residual_ppm`, `predicted_ppm`, and
`lower_ppm`/`upper_ppm` fields — never a single collapsed number. If the
`forecast-gru.pt` artifact loaded, `gru_status: "OK"` and the dashboard's
Time-to-Action sub-label reads "hybrid (physics + GRU)"
(`StatusCards.tsx`'s `forecastModelLabel`); otherwise `gru_status:
"FALLBACK"` and the label reads "physics" — both are honest, not an error.

## 5. Show Time-to-Action

The **Time-to-Action** status card (`StatusCards.tsx`) updates from the same
forecast: as the leak progresses it moves from `NO CROSSING` to a plain-
language countdown, e.g. "CO2 may reach the 5000 ppm action reference in 34
minutes." (never "AI says unsafe", never "time to harm" — CLAUDE.md's
required terminology). If the forecast predicts no crossing within the
60-minute horizon, the card honestly reads `NO CROSSING`, not a fabricated
number.

## 6. Move a worker into the gas zone

On `/simulation`, click on the floor of the isometric scene inside the red
`GAS_EXPOSURE` zone outline (`onFloorClick` → `POST
/api/v1/simulation/commands` with `{"command":"set_worker","x":...,"y":...}`).
Expected: the scene's worker marker moves; after the 2-second zone-entry
dwell (`ZONE_ENTER_SECONDS` in `backend/app/services/vision_ground_truth.py`)
the simulation-ground-truth `VisionEvidence` reports
`gas_zone_membership: INSIDE` for that worker.

## 7. Show severity escalation

On `/dashboard`, the **People at risk** status card increments, and the
active-incident table (below the main row) shows the CO2 incident's severity
change from `MEDIUM` (`CO2_ACTION_CROSSING_PREDICTED`, no person confirmed)
to `HIGH` (`PERSON_IN_PREDICTED_GAS_RISK`, per `backend/app/domain/risk/policy.py`)
once the worker's dwell-confirmed presence is factored in. Click **Review**
on that row to open the drawer and see the updated reason codes.

## 8. PPE replay demo

On `/simulation`, load the `overhead_ppe` preset and toggle the **Helmet**
checkbox off under **Worker** (`POST .../commands` with
`{"command":"set_worker","helmet":false}`), then check **Overhead work
active**. On `/dashboard`, the camera panel (right of the main row) shows
**real CV replay inference** — bounding boxes/labels from the bundled
`demo-assets/replay.mp4` running through the fine-tuned YOLO11n + ByteTrack
pipeline (`camera_id`, `vision.status`, per-track `detected_class`) — shown
separately from the simulation-ground-truth badge on `/simulation`; the two
provenances (`CV_MODEL` vs. `SIMULATION_GROUND_TRUTH`) are never merged into
one label. After the 3-second PPE-violation dwell
(`PPE_VIOLATION_SECONDS = 3.0`), a `HIGH` severity
`PPE_HELMET_OVERHEAD_VIOLATION` incident opens.

## 9. Review and acknowledge the incident

In the active-incident table, click **Review** on the open incident to open
the side drawer (`ReviewDrawer.tsx`). Click **Acknowledge**
(`POST /api/v1/incidents/{incident_id}/actions` with
`{"action":"ACKNOWLEDGE","expected_version":<version>}`). Expected: the
incident's `state` moves `OPEN → ACKNOWLEDGED`; the drawer's audit history
section immediately shows the new entry. Type a note in the comment box and
click **Add comment**, then click **Start investigating**
(`INVESTIGATE`), then **Resolve** (`RESOLVE`). Expected: state progresses
`ACKNOWLEDGED → INVESTIGATING → RESOLVED`, matching the allowed transitions
in `CLAUDE.md` (`OPEN → ACKNOWLEDGED → INVESTIGATING → RESOLVED`).

## 10. Show audit evidence

Still in the drawer, scroll to **Audit history**
(`GET /api/v1/incidents/{incident_id}/audit`). Expected: an append-only,
causally-ordered list — `OPENED` (actor `SYSTEM`) followed by
`ACKNOWLEDGE`/`COMMENT`/`INVESTIGATE`/`RESOLVE` (actor: the human reviewer),
each with a timestamp and, for the comment, its text. Reload the page
(`F5`) — the incident, its evidence, and the full audit trail persist
(backed by SQLite, not frontend state), satisfying Definition-of-Done item
10.

## 11. Demonstrate one model fallback

Stop the backend, move the leak-classifier artifact aside, and restart:

```bash
mv models/artifacts/leak-classifier-xgb.json /tmp/
make demo
curl http://127.0.0.1:8000/api/v1/system/status
```

Expected: `leak_model_status: "MODEL_UNAVAILABLE"` (or equivalent
`FALLBACK` state per `app/inference/leak_model.py`), while `/zones/{id}/forecast/latest`
still returns a valid physics-only forecast and the dashboard keeps
functioning — degraded, never fabricated as healthy (CLAUDE.md's "honest
degradation" invariant). Restore the artifact afterward:

```bash
mv /tmp/leak-classifier-xgb.json models/artifacts/
```

This exact fallback behavior was live-verified once already, per
`docs/README.md`'s "Fallback" note under the leak-classifier model card
(§7) and reconfirmed structurally in `docs/FINAL_VERIFICATION.md`; this
audit pass did not re-run it live.
