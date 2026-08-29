---
name: assessment-quality-gate
description: Review Factory Safety Sentinel for submission readiness, clean-environment execution, automated tests, evaluation, documentation, failure handling, live-change readiness, and compliance with the assessment. Use for verification and release work, not ordinary feature implementation.
---

# Assessment Quality Gate

Use this skill only when reviewing a milestone or preparing the assessment submission. Read `CLAUDE.md`, the attached assessment brief, and [acceptance matrix](references/acceptance-matrix.md) first.

## Gate Order

1. Verify P0 behavior before reviewing polish or P1 features.
2. Run the documented clean-environment setup without personal credentials.
3. Run lint, unit, integration, end-to-end, and evaluation commands.
4. Reproduce reported metrics from versioned scenarios and artifacts.
5. Exercise degraded modes and restart recovery.
6. Review security, privacy, licences, limitations, production improvements, and AI disclosure.
7. Rehearse one diagnosis and one small live policy/configuration change.

## Required End-to-End Proof

Demonstrate a seeded developing-leak scenario through ingestion, persistence, physics/ML forecast, time-to-action, worker exposure, severity change, WebSocket/dashboard update, human acknowledgement/resolution, and audit history.

Also demonstrate:

- no alert during a valid operational transient;
- sensor fault without false leak confirmation;
- camera/model outage with degraded state;
- duplicate evidence without duplicate incidents;
- invalid workflow transition rejection.

## Evidence Checklist

- Architecture diagram matches implementation.
- Setup/run instructions work on a clean machine.
- No hidden dataset, credential, infrastructure, or sample-file dependency.
- Tests cover equations, boundary cases, contracts, risk policy, incident state, and main scenarios.
- Metrics cover forecasting, incident events, CV, latency, and resilience.
- Every P0 row in the acceptance matrix has an automated or precisely reproducible proof.
- Train/validation/test split is by scenario before overlapping windows.
- Model/data licences and versions are documented.
- Logs contain correlation IDs without sensitive identity.
- Known limitations explicitly include synthetic-to-real gap and lack of safety certification.
- AI development tools are disclosed.

## Review Standard

Fail the gate for fake UI data, unavailable model artifacts, undocumented thresholds, simulator ground truth presented as CV, metrics that cannot be reproduced, a broken clean-run command, or a critical P0 scenario that only works manually.

Report failures with exact reproduction steps and the smallest safe remediation. Do not expand scope during release review.
