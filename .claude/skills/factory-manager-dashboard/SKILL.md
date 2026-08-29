---
name: factory-manager-dashboard
description: Build or change the simple Factory Safety Sentinel manager dashboard, incident review drawer, live charts, camera panel, status states, or frontend data synchronization. Use for manager-facing UI behavior, not Three.js simulation rendering or backend model training.
---

# Factory Manager Dashboard

Read `CLAUDE.md` and [dashboard specification](references/dashboard-specification.md) before implementing dashboard UI.

## Outcome

Provide one calm, glanceable manager screen backed entirely by REST/WebSocket state. It must answer: What is wrong? How serious is it? When may it become unsafe? Is anyone exposed? What action should I review?

## Boundaries

- Keep `/dashboard` to four summary cards, one gas chart, one camera panel, one incident table, and one review drawer.
- Keep simulation controls on `/simulation`.
- Do not calculate gas, Time-to-Action, confidence, severity, or incident transitions in React.
- Show source, freshness, model/fallback status, and degraded/unknown conditions.
- Accessibility cannot depend on colour alone.
- Prefer functional empty/loading/error states to visual effects or dense analytics.

## Data Workflow

1. Load an atomic REST snapshot.
2. Render persisted state with event/ingestion freshness.
3. Subscribe to WebSocket events.
4. Apply events by sequence and invalidate affected queries.
5. On gaps/reconnect, fetch a new snapshot before resuming.
6. Send review actions with incident version and handle conflict/validation errors visibly.

## Completion Check

Prove normal, developing-risk, critical/degraded, reconnect, empty, and review-action states with automated component or end-to-end tests. Refreshing the browser must preserve authoritative state.
