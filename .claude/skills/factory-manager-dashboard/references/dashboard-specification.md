# Dashboard Specification

Read this reference when building manager-facing components, queries, real-time synchronization, annotations, or tests.

## Information Architecture

Only two top-level links exist: `Dashboard` and `Simulation`. The default route is `/dashboard`.

### Header

- Product name.
- Current scenario and simulation time.
- Connection status: `Live`, `Reconnecting`, or `Offline`.
- Provenance badge: `SIMULATION`, `REPLAY`, or mixed.
- Link to Simulation.

Do not place model configuration or training actions in the header.

### Four cards

| Card | Primary value | Secondary value | Failure behavior |
|---|---|---|---|
| Overall risk | Highest active severity or `NORMAL` | Number of active incidents | `UNKNOWN` if snapshot unavailable |
| CO2 | Latest ppm | Trend and reading age | `STALE` after two expected intervals |
| Time-to-Action | Minimum honest crossing or `NO CROSSING` | Threshold label and forecast model | `UNAVAILABLE`, never infinity/zero by default |
| People at risk | Count of confirmed tracks in risk zones | Unknown/untracked evidence count | `UNKNOWN` if camera degraded |

Cards are buttons only if they perform a clear navigation/filter action. Use text/icon plus colour; do not use animated gauges.

### Main row

Gas chart uses approximately two-thirds width on desktop; camera uses one-third. Stack vertically on narrow screens.

Chart series:

- observed CO2 as a solid line;
- physics forecast as a dashed line;
- optional GRU-corrected forecast as a second distinct dashed line only when P1 is active;
- uncertainty band only when bounds exist;
- horizontal labelled reference lines for internal advisory, 5000 action/TWA reference, 30000 short-term reference, and 40000 IDLH;
- a vertical `Now` line separating history and forecast.

Default view shows the last two simulated hours plus next hour. Provide a simple `2h`, `8h`, `10h` selector. Tooltip includes event time, value, source, and quality. Do not smooth the line in a way that changes extrema.

Camera panel:

- annotated bundled replay or webcam frame;
- person box with anonymous `Worker #track_id`;
- helmet/vest state, gas/overhead polygons, and source/model badge;
- last-frame age, FPS, and degraded overlay;
- no facial crop, employee name, or biometric inference.

The camera may update at a lower rate than sensor cards without blocking the page.

### Incident table

Default sort: severity descending, then most recently updated. Columns: severity, incident, zone/track, age, state, and `Review`. Show up to 10 active rows; use a simple filter for `Active` and `Resolved`, not a full analytics toolbar.

Plain-language examples:

- `CO2 may reach the 5000 ppm action reference in 34 min.`
- `Worker #7 has remained in the predicted gas-risk zone for 18 s.`
- `Helmet non-compliance persisted in the overhead-work zone.`

Avoid `AI says unsafe` or unexplained probability-only text.

### Review drawer

Display:

1. severity/state and last update;
2. explanation and reason codes;
3. recommended human action;
4. sensor/forecast/vision evidence with provenance and freshness;
5. model/config versions and fallback/degraded status;
6. comment input and only currently allowed actions;
7. chronological audit events.

Default recommendations are informational: inspect the zone, verify ventilation/source, contact safety personnel, and follow site procedures. Never instruct the app to actuate equipment.

## Visual Rules

- Neutral background, one accent colour, and standard severity tokens: grey/blue, amber, orange, red.
- `NORMAL`, `UNKNOWN`, and `DEGRADED` are visually distinct.
- Minimum 4.5:1 text contrast and keyboard-visible focus.
- Use one icon library and one chart library.
- Avoid gradients, glass effects, metric walls, 3D on dashboard, unnecessary animations, and excessive decimal precision.
- CO2 shows a whole ppm; probability may show a whole percent; Time-to-Action shows whole minutes or `<1 min`.

## State Behavior

- Initial loading: skeleton for cards/chart/table; camera placeholder.
- Empty: `No active incidents` plus healthy context, not a blank table.
- REST error: retain last confirmed snapshot with stale banner when possible.
- WebSocket reconnect: display status, fetch snapshot, then resume.
- Model fallback: chart labels `Physics fallback`; do not hide prediction.
- Camera failure: camera panel says unavailable and people-at-risk becomes unknown unless simulation truth is explicitly selected.
- Incident action pending: disable only relevant drawer actions; show success/error result.
- Version conflict: refresh incident and explain that state changed.

## Query and Event Ownership

Use a typed API client. The REST snapshot initializes state; TanStack Query owns server state. WebSocket handlers update/invalidate queries and must respect sequence numbers. Do not maintain an independent duplicate global store for the same incident/readings.

## Required UI Tests

1. Snapshot maps to all four cards and exact chart series.
2. `NO_CROSSING`, `ALREADY_EXCEEDED`, and unavailable predictions render correctly.
3. WebSocket sequence gap triggers snapshot refresh.
4. Camera degraded state never displays zero people as confirmed safe.
5. Allowed incident actions and optimistic-version conflict work.
6. Simulation ground truth and CV model badges cannot be confused.
7. Keyboard user can open, act in, and close the review drawer.
8. Dashboard remains usable at 1280x720 and a narrow mobile viewport.
