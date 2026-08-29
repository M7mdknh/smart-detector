# Simulator Specification

Read this reference when implementing scenario state, controls, synthetic history, worker movement, or the Three.js view.

## State Machine

```text
UNLOADED -> READY -> RUNNING <-> PAUSED
READY/RUNNING/PAUSED -> RESETTING -> READY
```

Loading a preset creates a new run ID, fixed seed, ten-hour warm start, persisted state, and `READY` status. `reset` reproduces the initial history for the same preset/seed. Commands include expected state version and are idempotent by command ID.

## Authoritative State

The backend owns:

- run/scenario/seed/generator version;
- event clock, speed, and state version;
- zone volume, inlet concentration, source load, and ventilation;
- sensor state and configured fault;
- worker position and PPE ground truth;
- camera/replay state;
- machines and hazard-zone activation.

The frontend owns only view camera, selection, and temporary form state.

## Default Presets

| Preset | Warm start | Interactive starting state | Expected result |
|---|---|---|---|
| `normal` | 450–900 ppm with bounded noise | source 0, ventilation 500 m3/h | No gas incident |
| `gradual_leak` | normal, then small developing rise | source ramps toward 4,000,000 ppm·m3/h | Predicted 5000 ppm action crossing |
| `ventilation_failure` | stable operational concentration | ventilation falls 500 -> 100 m3/h | Rising concentration; leak classifier should distinguish control change |
| `worker_exposure` | gradual leak history | worker can enter gas polygon | Severity increases with presence |
| `overhead_ppe` | safe gas | overhead zone active; helmet toggle off | Persistent helmet incident |
| `sensor_fault` | safe process | sensor stuck or biased | Data-quality incident, not confirmed leak |

Use seed `42` for the default demo. Other seeds support evaluation.

## Numerical Generation

- Canonical integration and reading step: five simulated minutes.
- For time-varying controls, integrate piecewise at a step no greater than five minutes.
- Sensor value = physical concentration + seeded noise + configured fault transformation.
- Default healthy noise may be Gaussian with standard deviation 20 ppm, clipped only to non-negative readings.
- Store true physical concentration separately from observed sensor value and never expose truth as a device measurement.
- All generated readings enter through `POST /api/v1/sensor-readings` application logic with `SIMULATOR` source.

Warm start must use the same generator, validation, ingestion, persistence, and feature code as live ticks. It may batch calls internally for speed but must not insert directly into tables.

## Clock

- Supported speed values: `1x`, `10x`, `60x`, `300x` simulation time.
- Backend advances event time; frontend displays it.
- Pause stops event-time advancement but allows review/API actions.
- Do not couple simulation to wall-clock sleeps in tests; inject a fake clock/tick command.
- Throttle UI broadcasts to at most one per real second while preserving every five-minute sensor reading in persistence.

## Controls

P0 controls:

- load preset;
- start, pause, reset;
- speed selection;
- emission/source slider from 0 to 8,000,000 ppm·m3/h;
- ventilation slider from 0 to 1000 m3/h, with zero handled safely;
- worker position by click/drag or simple directional controls;
- helmet and vest toggles;
- overhead-work active toggle.

Changing a control records a command and affects the next numerical segment. A direct CO2 value edit is not a normal control. If retained for tests, label it `Sensor override` under advanced fault controls and set evidence quality/source accordingly.

## Worker and Vision Ground Truth

Represent each worker with anonymous simulation ID, 2D floor coordinate, PPE booleans, and zone state. Convert floor state to `VisionEvidence` only through the simulation-ground-truth adapter with `SIMULATION_GROUND_TRUTH` source. It may drive incident logic for deterministic scenario tests, while the camera panel independently runs CV replay.

## Three.js View

Keep the scene lightweight:

- one floor plane and workcell boundary;
- two or three simple machine boxes;
- one ventilation marker, one gas sensor, one camera cone;
- one worker capsule/model;
- translucent gas-risk and overhead-zone planes;
- colour/intensity based on backend truth, explicitly labelled `Simulation ground truth`.

Use basic geometry/materials; no downloaded 3D assets are required. No shadows/physics engine is required. The view must remain usable without WebGL by showing a simple control/status fallback.

## Determinism Tests

1. Same preset, seed, and commands produce equal readings within `1e-6` before serialization.
2. Reset reproduces the same warm-start IDs deterministically or uses a documented new run ID with equivalent values.
3. Pause/tick behavior is testable without sleeping.
4. A command with stale state version is rejected.
5. Changing ventilation/source affects the next physics segment, not historical readings.
6. Simulation truth and CV evidence retain different provenance through the incident audit trail.
