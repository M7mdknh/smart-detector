# Factory Safety Sentinel

Smart-facility incident detection prototype: physics + ML CO2 forecasting,
YOLO11n/ByteTrack worker-safety vision, an explainable severity policy, and a
manager dashboard with a full human review workflow — built on a deterministic,
seeded factory-workcell simulator.

**Prototype for an assessment. Not certified for real industrial safety decisions.**

```bash
make setup
make demo
# open http://127.0.0.1:5173/dashboard and http://127.0.0.1:5173/simulation
```

Full documentation — architecture, model cards, evaluation results, licenses,
limitations, security/privacy, and AI-tool disclosure — is in
[`docs/README.md`](docs/README.md). Product scope and non-negotiable invariants
are in [`CLAUDE.md`](CLAUDE.md).
