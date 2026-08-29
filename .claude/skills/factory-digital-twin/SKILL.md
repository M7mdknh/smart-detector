---
name: factory-digital-twin
description: Build or change the low-poly factory simulation, accelerated clock, scenario generator, worker controls, gas/ventilation controls, or fault injection. Use for the deterministic test factory, not actual CV inference or model training.
---

# Factory Digital Twin

Read the simulation rules and P0 boundary in `CLAUDE.md` before implementing simulation behavior or UI. Read [simulator specification](references/simulator-specification.md) for the frozen state machine, presets, clock, numerical defaults, controls, and determinism tests.

## Purpose

Provide a deterministic, interactive source of synthetic sensor and personnel events that exercises the same backend path as future real devices. Visual fidelity is secondary to reproducibility and end-to-end testing.

## State Ownership

- Backend owns scenario state, simulation clock, random seed, workers, equipment, gas sources, ventilation, sensors, and fault modes.
- Frontend sends commands and renders backend state.
- Persist event time and ingestion time separately.
- Scenario reset with the same seed and commands must reproduce the same readings within documented numeric tolerance.

## Controls

Support the smallest set that proves the vertical slice:

- load/reset a scenario, pause/resume, and change time scale;
- adjust emission/leak rate and ventilation;
- start/stop configured machine, pump, or valve states;
- move workers and toggle allowed PPE;
- inject supported sensor/camera failures.

Control physical causes. A direct gas-value override must be clearly labelled as sensor override/fault injection.

## Historical Warm Start

Forecasting must work immediately in a demo. Loading a scenario should generate and ingest the configured lookback history, then enter interactive live time. Do not bypass validation or persistence for warm-start data.

## Visual Representation

Use a low-poly/isometric view with one workcell, a few machines, sensors, workers, camera, ventilation, gas-exposure zone, and overhead-work zone. Represent gas intensity and affected zones visually, but do not claim CFD or realistic plume dynamics.

## Vision Separation

- Simulation may emit deterministic worker/PPE evidence as `SIMULATION_GROUND_TRUTH`.
- Actual CV must process a real/replayed image stream and emit `CV_MODEL`.
- Both use the same evidence schema, but the UI and audit trail retain provenance.

## Acceptance Scenarios

At minimum, verify normal operation, gradual accumulation, ventilation reduction, worker exposure, overhead-zone helmet violation, and one sensor failure. Each scenario declares its expected ground-truth events so end-to-end metrics can be reproduced.

Do not add realistic physics, multi-floor navigation, collision engines, or asset-detail work while any required acceptance scenario is incomplete.
