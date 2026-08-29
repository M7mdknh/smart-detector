# Factory Safety Sentinel Claude Guidance

This package contains implementation instructions for Claude Code. Extract it into the root of the Factory Safety Sentinel repository, preserving the `.claude` directory.

## Included

- `CLAUDE.md`: authoritative product scope, architecture, exact P0 models, risk policy, dashboard boundary, reliability rules, commands, and repository structure.
- `.claude/skills/factory-system-architecture`: API, persistence, WebSocket, and incident workflow guidance.
- `.claude/skills/sensor-risk-modeling`: physics, XGBoost, optional residual GRU, data splits, artifacts, and evaluation guidance.
- `.claude/skills/vision-worker-safety`: YOLO11n, Construction-PPE data, ByteTrack, association/dwell, provenance, and evaluation guidance.
- `.claude/skills/factory-manager-dashboard`: simple dashboard layout, data synchronization, states, accessibility, and UI tests.
- `.claude/skills/factory-digital-twin`: deterministic simulator, scenarios, controls, clock, Three.js boundary, and tests.
- `.claude/skills/assessment-quality-gate`: end-to-end acceptance and submission checks.

## Verify after extraction

The target repository should contain:

```text
CLAUDE.md
.claude/skills/.../SKILL.md
.claude/skills/.../references/*.md
```

On Linux/macOS, `.claude` is a hidden directory; use `ls -la` if it is not visible in the file browser.
