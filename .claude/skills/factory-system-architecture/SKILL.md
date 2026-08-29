---
name: factory-system-architecture
description: Design or change Factory Safety Sentinel APIs, domain contracts, persistence, incident workflow, module boundaries, or end-to-end data flow. Use for architectural and backend integration work, not isolated model training or UI styling.
---

# Factory System Architecture

Read `CLAUDE.md` before changing architecture. Preserve its P0 scope and non-negotiable invariants. For routes, tables, transactions, idempotency, typed failures, or WebSocket events, also read [API and data specification](references/api-and-data-specification.md).

## Outcome

Maintain one locally runnable modular monolith whose simulator, replay, sensor, vision, forecasting, risk, incident, and dashboard components communicate through versioned contracts.

## Architecture Decisions

- Keep adapters replaceable but avoid network service boundaries unless operationally necessary.
- Treat event/simulation time and ingestion time separately.
- Persist source provenance, scenario seed, model/config version, and correlation ID.
- Send all simulator readings through the public ingestion path.
- Keep physics/rule fallback available when learned inference fails.
- Persist immutable evidence references and audit events for incident decisions.
- Deduplicate repeated evidence into an evolving incident rather than opening one incident per reading or frame.
- Keep `/dashboard/snapshot` as the atomic boot/reconnect projection; do not build one endpoint per UI card.
- Publish WebSocket events only after authoritative state commits.

## Change Workflow

1. Identify the affected domain contract and its current consumers.
2. Define backward-compatible schema evolution or deliberately increment `schema_version`.
3. Update backend and frontend representations together.
4. Preserve idempotency for ingestion and incident commands.
5. Define typed failure behavior, health status, and degraded-mode behavior.
6. Add unit, integration, and end-to-end tests for the changed path.
7. Update architecture or decision documentation when the change alters a boundary or invariant.

## Required Behaviors

- REST commands return explicit validation errors.
- WebSocket events are projections of persisted/backend state, not a second source of truth.
- Human workflow rejects invalid transitions and records actor, time, reason, and before/after state.
- Model timeouts or missing artifacts reduce confidence and trigger fallback rather than crashing ingestion.
- Restarting the backend does not erase active incidents or audit history.

## Do Not

- Add cloud credentials or external infrastructure to the clean-run path.
- Use in-memory-only state for incidents or audit history.
- Couple severity directly to a model probability.
- let the frontend calculate authoritative gas concentration, forecasts, or incident status.
- let WebSocket payloads become an unpersisted second source of truth.
- Expand into P1/P2 while the P0 vertical slice is incomplete.

## Completion Check

Demonstrate one traceable request from simulated reading to persisted forecast, incident update, WebSocket event, dashboard state, human action, and audit record.
