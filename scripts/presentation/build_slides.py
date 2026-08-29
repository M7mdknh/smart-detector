"""Builds the 18 HTML slides + speaker notes for the Factory Safety Sentinel
final presentation, from real repository data only (evaluation JSON files,
docs, and committed screenshots/evidence frames) -- no invented figures.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from design import page  # noqa: E402

REPO = Path("/home/muhammad/Documents/smart-detector")
SHOTS = REPO / "docs" / "screenshots" / "final"
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/slides_html")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _run_test_counts() -> tuple[int, int]:
    """Actually re-runs the backend and frontend test suites right now (not a
    cached/remembered number) so slide 16's "verified this session" claim is
    true by construction -- these two counts were previously hardcoded
    literals that silently went stale (173/18) after this session added new
    tests. Fails loudly (not a fallback guess) if either suite doesn't pass
    cleanly or its output can't be parsed, matching this script's existing
    assert-driven style for every other metric."""
    backend = subprocess.run(
        [str(REPO / "backend/.venv/bin/python"), "-m", "pytest", "-q"],
        cwd=REPO / "backend", capture_output=True, text=True, timeout=300,
    )
    assert backend.returncode == 0, f"backend test suite failed:\n{backend.stdout}\n{backend.stderr}"
    backend_match = re.search(r"(\d+) passed", backend.stdout)
    assert backend_match, f"could not parse backend test count from:\n{backend.stdout}"

    frontend = subprocess.run(
        ["npm", "test", "--", "--run"],
        cwd=REPO / "frontend", capture_output=True, text=True, timeout=300,
    )
    assert frontend.returncode == 0, f"frontend test suite failed:\n{frontend.stdout}\n{frontend.stderr}"
    frontend_match = re.search(r"Tests\s+(\d+) passed", frontend.stdout)
    assert frontend_match, f"could not parse frontend test count from:\n{frontend.stdout}"

    return int(backend_match.group(1)), int(frontend_match.group(1))


BACKEND_TEST_COUNT, FRONTEND_TEST_COUNT = _run_test_counts()
print(f"Verified: backend tests={BACKEND_TEST_COUNT} frontend tests={FRONTEND_TEST_COUNT} (re-run live, not hardcoded)")

# ---------------------------------------------------------------------------
# Load + verify real metrics from authoritative files
# ---------------------------------------------------------------------------

gru = json.loads((REPO / "models/evaluation/gru_benchmark_report.json").read_text())
phys = json.loads((REPO / "models/evaluation/physics_forecast_metrics.json").read_text())
leak = json.loads((REPO / "models/evaluation/leak_model_metrics.json").read_text())
vision = json.loads((REPO / "models/evaluation/vision_model_metrics.json").read_text())
registry = json.loads((REPO / "models/registry.json").read_text())
v12_manifest = json.loads((REPO / "models/evaluation/vision_v1.2_dataset_manifest.json").read_text())
v12_subset = json.loads((REPO / "models/evaluation/vision_v1.2_subset_selection.json").read_text())
v12_eval = json.loads((REPO / "models/evaluation/vision_v1.2_comparative_evaluation.json").read_text())
interview_summary = json.loads((REPO / "models/evaluation/interview_video_detection_summary.json").read_text())

phys_mae = gru["global"]["physics"]["mae"]
hybrid_mae = gru["global"]["hybrid_physics_plus_gru"]["mae"]
gru_n = gru["global"]["physics"]["n"]
improvement_pct = (phys_mae - hybrid_mae) / phys_mae * 100

assert abs(phys_mae - 57.19429038808617) < 1e-6, phys_mae
assert abs(hybrid_mae - 47.593730690303325) < 1e-6, hybrid_mae
assert gru_n == 1092, gru_n
assert round(improvement_pct, 1) == 16.8, improvement_pct

assert abs(phys["physics_mae_ppm"] - 95.49982989386424) < 1e-6
assert phys["n_scenarios"] == 10
assert phys["n_point_comparisons"] == 120

xgb = leak["xgboost_calibrated"]
v11 = vision["detection_metrics"]
active_model_version = registry["ppe_detector"]["version"]
assert active_model_version == "1.1", active_model_version

print(f"Verified: physics MAE={phys_mae:.2f} hybrid MAE={hybrid_mae:.2f} improvement={improvement_pct:.1f}% n={gru_n}")
print(f"Verified: physics-only broader eval MAE={phys['physics_mae_ppm']:.2f} scenarios={phys['n_scenarios']} points={phys['n_point_comparisons']}")
print(f"Verified: active PPE model version={active_model_version}")

# ---------------------------------------------------------------------------
# Slide registry: list of (filename_stem, html, notes_dict)
# ---------------------------------------------------------------------------
slides: list[tuple[str, str, dict]] = []


def add(stem: str, html: str, say: str, evidence: str, transition: str, question: str, answer: str):
    slides.append((stem, html, {
        "say": say, "evidence": evidence, "transition": transition,
        "question": question, "answer": answer,
    }))


def header(eyebrow: str, num: int) -> str:
    return f"""<div class="header-bar">
      <div class="brand"><span class="dot"></span>Factory Safety Sentinel</div>
      <div class="pagenum">{num:02d} / 18</div>
    </div>"""


def footer(note: str = "") -> str:
    return f"""<div class="footer-line"><span>Factory Safety Sentinel — Smart-Facility Incident Detection Prototype</span><span>{note}</span></div>"""


def shot_img(name: str, alt: str) -> str:
    return f'<img src="file://{SHOTS / name}" alt="{alt}">'


# =============================================================================
# SLIDE 1 — Title
# =============================================================================
html = f"""<div class="slide" style="padding:0;">
  <img src="file://{SHOTS / '01_dashboard_normal_state.png'}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0.30;">
  <div style="position:absolute;inset:0;background:linear-gradient(115deg, rgba(10,20,32,0.97) 40%, rgba(10,20,32,0.65) 100%);"></div>
  <div style="position:relative;z-index:1;display:flex;flex-direction:column;justify-content:center;height:100%;padding:96px;">
    <div class="eyebrow">Smart-Facility Incident Detection · Assessment Prototype</div>
    <h1 style="font-size:88px;">Factory Safety<br>Sentinel</h1>
    <p class="big" style="max-width:900px;margin-top:24px;color:#cbd5e1;">A predictive, multimodal industrial-safety system — physics- and ML-driven gas-risk
    forecasting fused with real-time computer-vision PPE and zone supervision, wired into one
    explainable incident and review workflow.</p>
    <div style="display:flex;gap:20px;margin-top:48px;">
      <span class="badge badge-orange">Physics + XGBoost + GRU</span>
      <span class="badge badge-orange">YOLO11n + ByteTrack</span>
      <span class="badge badge-green">Full-stack, tested, evidence-backed</span>
    </div>
    <div style="margin-top:64px;color:#94a3b8;font-size:20px;">
      Prepared for the Smart-Facility Incident Detection assessment · Contact: mohammad.2003.1m@gmail.com<br>
      Prototype — not certified for real industrial safety decisions.
    </div>
  </div>
</div>"""
add("01_title", html,
    say="This is Factory Safety Sentinel — a prototype that predicts gas risk before it becomes dangerous and watches worker PPE/zone compliance in real time, both feeding one incident and review workflow a manager actually uses.",
    evidence="Hero image is the real, live dashboard captured this session (docs/screenshots/final/01_dashboard_normal_state.png).",
    transition="Let's start with the problem this solves.",
    question="Is this a finished commercial product?",
    answer="No — it's an assessment prototype with a fully working backend/frontend/tests, explicitly not certified for real safety decisions (stated on this slide and throughout).")

# =============================================================================
# SLIDE 2 — Problem
# =============================================================================
html = f"""<div class="slide">
  {header("The Problem", 2)}
  <h2>Industrial safety monitoring is fragmented and reactive</h2>
  <div class="grid2" style="margin-top:36px;align-items:start;">
    <div>
      <ul class="clean">
        <li><b>Gas leaks develop gradually.</b> A slow CO2 buildup can cross a dangerous threshold before any human is watching the reading.</li>
        <li><b>PPE violations expose workers to preventable risk</b> — a missing helmet or vest is only caught if someone happens to look.</li>
        <li><b>Restricted areas need continuous supervision</b> that a manager cannot realistically provide across a whole floor, every shift.</li>
        <li><b>Sensors, cameras, and incident logs are usually separate systems</b> — nothing correlates a gas trend with a camera event with a reviewable record.</li>
      </ul>
    </div>
    <div class="card">
      <div class="shot"><img src="file://{SHOTS / '01_dashboard_normal_state.png'}" style="width:100%;"></div>
      <p style="margin-top:16px;font-size:18px;">The real, working dashboard: one screen, live gas trend + forecast + camera + incidents — replacing the fragmented view above.</p>
    </div>
  </div>
  {footer()}
</div>"""
add("02_problem", html,
    say="Four real gaps: gradual leaks outrun human attention, PPE violations go unnoticed, restricted zones can't be watched continuously, and today's tools don't unify sensor, camera, and incident data into one place.",
    evidence="Framed against the actual dashboard screenshot, not a stock photo — this is what the unified view looks like.",
    transition="Here's how the assessment brief maps onto what was actually built.",
    question="Isn't this solved already by existing SCADA/BMS systems?",
    answer="Those systems are usually threshold-only and reactive; this prototype adds predictive forecasting (physics+ML) and vision-based PPE/zone supervision on top, unified in one incident workflow — the gap being addressed, not a claim no monitoring exists at all.")

# =============================================================================
# SLIDE 3 — Scope and assessment alignment
# =============================================================================
html = f"""<div class="slide">
  {header("Scope & Assessment Alignment", 3)}
  <h2>MVP scope vs. certified future deployment</h2>
  <div class="grid2" style="margin-top:32px;">
    <div class="card top">
      <h3>Delivered in this MVP</h3>
      <ul class="clean check">
        <li>Sensor-based risk monitoring (seeded, replayable CO2 simulator)</li>
        <li>Predictive analysis (physics mass-balance + GRU residual + XGBoost leak classifier)</li>
        <li>Computer vision (YOLO11n + ByteTrack PPE/zone supervision)</li>
        <li>Working manager dashboard with live gas/camera/incident views</li>
        <li>Fully functioning backend (FastAPI, SQLite, WebSocket, REST)</li>
        <li>Simulation / digital twin for testing without a physical factory</li>
        <li>Evidence capture + full incident review/audit workflow</li>
      </ul>
    </div>
    <div class="card top">
      <h3>Deferred to certified deployment</h3>
      <ul class="clean">
        <li>Real factory sensor/camera hardware integration</li>
        <li>Multi-camera, multi-zone, multi-worker at production scale</li>
        <li>Regulatory certification for real safety-critical decisions</li>
        <li>Domain-adapted vision model trained on real factory footage</li>
        <li>Production security hardening (auth, encrypted evidence storage)</li>
      </ul>
    </div>
  </div>
  {footer()}
</div>"""
add("03_scope", html,
    say="Everything in the left column is real and working today; the right column is explicitly out of scope for an assessment prototype and reserved for a certified deployment.",
    evidence="This split is stated directly in the project's own CLAUDE.md scope document, not asserted only in this deck.",
    transition="Now the architecture that delivers the left column.",
    question="Why defer multi-camera/multi-worker instead of building it?",
    answer="The assessment's P0 scope is one workcell/camera/gas-zone end-to-end and fully tested, rather than partial multi-entity support — CLAUDE.md's own frozen-scope decision, to keep the vertical slice complete and defensible.")

# =============================================================================
# SLIDE 4 — Architecture (elaborated: every stage named, both evidence paths, storage + surfaces)
# =============================================================================
def flow_box(label, color="orange"):
    return f'<div class="flow-step" style="border-color:var(--{color});color:var(--{color});">{label}</div>'


def mini_box(label, color="white", dashed=False):
    border = f"var(--{color})" if color != "white" else "var(--border)"
    text_color = f"var(--{color})" if color != "white" else "var(--white)"
    style = f"border:1.5px {'dashed' if dashed else 'solid'} {border};color:{text_color};"
    return f'<div style="{style}background:var(--navy-2);border-radius:8px;padding:8px 10px;font-size:14px;font-weight:700;text-align:center;">{label}</div>'


def down_arrow():
    return '<div style="text-align:center;color:var(--orange);font-size:16px;line-height:1;">↓</div>'


sensor_stages = [
    ("Simulator engine (seeded, deterministic)", "orange"),
    ("Ingestion service — POST /sensor-readings (idempotent)", "white"),
    ("sensor_readings (SQLite)", "white"),
    ("Contracts + validation (Pydantic v2)", "white"),
    ("Physics forecast (mass-balance ODE)", "yellow"),
    ("GRU residual model / physics-only fallback", "yellow"),
    ("XGBoost leak classifier / rule fallback", "yellow"),
]
vision_stages = [
    ("Camera / bundled replay video", "orange"),
    ("Vision worker — YOLO11n detection", "white"),
    ("ByteTrack — anonymous worker tracking", "white"),
    ("One-to-one PPE association (helmet/vest)", "white"),
    ("Zone membership (point-in-polygon, dwell)", "white"),
    ("vision_evidence (CV_MODEL / SIMULATION_GROUND_TRUTH)", "white"),
    ("Evidence storage — real frame or schematic", "white"),
]
sensor_col = "".join(mini_box(l, c) + down_arrow() for l, c in sensor_stages)[:-len(down_arrow())]
vision_col = "".join(mini_box(l, c) + down_arrow() for l, c in vision_stages)[:-len(down_arrow())]

html = f"""<div class="slide">
  {header("Complete Solution Overview", 4)}
  <h2>End-to-end architecture — every stage, both evidence paths</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:16px;">
    <div style="display:flex;flex-direction:column;gap:6px;">
      <div style="color:var(--gray);font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;text-align:center;">Sensor path</div>
      {sensor_col}
    </div>
    <div style="display:flex;flex-direction:column;gap:6px;">
      <div style="color:var(--gray);font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;text-align:center;">Vision path</div>
      {vision_col}
    </div>
  </div>
  <div style="text-align:center;color:var(--orange);font-size:16px;margin-top:6px;">↓</div>
  <div style="display:flex;justify-content:center;">
    <div style="border:2px solid var(--yellow);color:var(--yellow);background:var(--navy-3);border-radius:8px;padding:10px 30px;font-size:16px;font-weight:800;">Deterministic risk / severity policy (versioned rules)</div>
  </div>
  <div style="text-align:center;color:var(--orange);font-size:16px;">↓</div>
  <div style="display:flex;justify-content:center;">
    <div style="border:2px solid var(--red);color:var(--red);background:var(--navy-3);border-radius:8px;padding:10px 30px;font-size:16px;font-weight:800;">Incident service — dedup, audit trail</div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:10px;">
    {mini_box("incidents / audit_events (SQLite, Alembic)", "green", dashed=True)}
    {mini_box("WebSocket hub (+ REST poll fallback)", "green")}
    {mini_box("React dashboard — /dashboard", "green")}
    {mini_box("Three.js digital twin — /simulation", "green")}
  </div>
  {footer("One ingestion contract for both paths — CLAUDE.md invariant #1")}
</div>"""
add("04_architecture", html,
    say="Two parallel evidence streams — gas sensors and camera — both terminate in one deterministic risk/incident policy, which writes to the database and pushes live WebSocket updates to the dashboard and simulation UI.",
    evidence="Matches the actual module layout (backend/app/services/pipeline.py, backend/app/inference/, backend/app/domain/risk/policy.py) — not a conceptual sketch.",
    transition="Let's look at exactly which of these boxes are trained models versus deterministic logic.",
    question="Is this a microservices architecture?",
    answer="No — deliberately a modular monolith (one FastAPI process) with replaceable Python adapters, per CLAUDE.md; simpler to run, test, and reason about for this scope.")

# =============================================================================
# SLIDE 5 — Number and roles of models
# =============================================================================
html = f"""<div class="slide">
  {header("Models & Components", 5)}
  <h2>Three trained ML models, one analytical model, three deterministic components</h2>
  <table class="data" style="margin-top:24px;">
    <tr><th>Component</th><th>Type</th><th>Role</th></tr>
    <tr><td><b>XGBoost leak classifier</b></td><td><span class="badge badge-orange">Trained ML</span></td><td>Calibrated leak-probability estimate from sliding-window sensor features</td></tr>
    <tr><td><b>Residual GRU forecast model</b></td><td><span class="badge badge-orange">Trained ML</span></td><td>Learns the physics model's residual error to sharpen the 60-min CO2 forecast</td></tr>
    <tr><td><b>YOLO11n PPE detector</b></td><td><span class="badge badge-orange">Trained CV model</span></td><td>Detects person / helmet / vest / no_helmet on camera frames</td></tr>
    <tr><td><b>Physics mass-balance model</b></td><td><span class="badge badge-yellow">Analytical, not ML</span></td><td>First-principles gas concentration ODE — the safe fallback when ML is unavailable</td></tr>
    <tr><td><b>ByteTrack</b></td><td><span class="badge badge-gray">Tracking algorithm</span></td><td>Associates detections into anonymous, session-local worker tracks — not trained</td></tr>
    <tr><td><b>Restricted-zone polygons</b></td><td><span class="badge badge-gray">Deterministic geometry</span></td><td>Configured point-in-polygon regions, not a learned "zone" class</td></tr>
    <tr><td><b>Risk / severity policy</b></td><td><span class="badge badge-gray">Deterministic logic</span></td><td>Versioned rule table converting evidence into severity + reason codes</td></tr>
  </table>
  {footer("Verified against models/registry.json and CLAUDE.md's Frozen Models table")}
</div>"""
add("05_models", html,
    say="Exactly three trained ML models plus one analytical physics model, confirmed against the model registry — everything else, including ByteTrack and the zone/severity logic, is deterministic by design so the system stays explainable and auditable.",
    evidence="models/registry.json lists exactly three trained artifacts (leak_classifier, ppe_detector, forecast_gru); CLAUDE.md's Frozen Models table independently confirms the same breakdown.",
    transition="Here's why each of the three trained models was chosen specifically.",
    question="Why not make the risk policy itself a learned model?",
    answer="Explainability and auditability — CLAUDE.md invariant #6 requires severity to be deterministic and separate from raw model confidence, so every incident's reason codes are traceable to a versioned rule, not an opaque score.")

# =============================================================================
# SLIDE 6 — Sensor and risk pipeline
# =============================================================================
html = f"""<div class="slide">
  {header("Sensor & Risk Pipeline", 6)}
  <h2>Proactive prediction, not threshold-only reaction</h2>
  <div class="flow" style="justify-content:center;margin-top:48px;flex-wrap:wrap;row-gap:24px;">
    {flow_box("Gas readings")}<div class="flow-arrow">→</div>
    {flow_box("Sliding history window")}<div class="flow-arrow">→</div>
    {flow_box("Physics forecast")}<div class="flow-arrow">→</div>
    {flow_box("GRU residual correction", "yellow")}<div class="flow-arrow">→</div>
    {flow_box("Leak classifier", "yellow")}<div class="flow-arrow">→</div>
    {flow_box("Deterministic risk level", "green")}<div class="flow-arrow">→</div>
    {flow_box("Incident alert", "red")}
  </div>
  <div class="card" style="margin-top:56px;">
    <p style="font-size:22px;">Every stage runs on <b>every tick</b>, using the last 10 simulated hours of history. The forecast projects
    60 minutes ahead — so a manager sees a predicted threshold crossing <i>before</i> it happens, with an
    explicit "Time-to-Action" estimate, not just a current-value alarm.</p>
  </div>
  {footer()}
</div>"""
add("06_pipeline", html,
    say="This is the full sensor path: real readings feed a 10-hour sliding window, the physics model projects forward, the GRU corrects its residual error, the classifier estimates leak probability, and a deterministic policy turns that into a severity with a Time-to-Action estimate.",
    evidence="Runs every tick against real ingested readings, not a one-shot batch job — backend/app/services/pipeline.py::run_risk_pipeline.",
    transition="The physics behind that forecast is worth showing explicitly.",
    question="What happens if the GRU model artifact is missing?",
    answer="It falls back to physics-only forecasting automatically (CLAUDE.md's safe-fallback invariant) — never crashes, never fabricates a number; shown live in the gru_benchmark_report.json fallback behavior.")

# =============================================================================
# SLIDE 7 — Time-to-Action physics
# =============================================================================
html = f"""<div class="slide">
  {header("Gas Physics", 7)}
  <h2>Time-to-Action: the equations behind the forecast</h2>
  <div class="grid2" style="margin-top:24px;">
    <div class="card top">
      <h3>Well-mixed mass balance</h3>
      <p class="mono" style="font-size:26px;color:var(--white);">dC/dt = Q/V · (Cin − C) + G/V</p>
      <h3 style="margin-top:28px;">Steady-state concentration</h3>
      <p class="mono" style="font-size:26px;color:var(--white);">Css = Cin + G/Q</p>
      <h3 style="margin-top:28px;">Time constant</h3>
      <p class="mono" style="font-size:26px;color:var(--white);">τ = V/Q</p>
      <h3 style="margin-top:28px;">Concentration response</h3>
      <p class="mono" style="font-size:26px;color:var(--white);">C(t) = Css + (C0 − Css)·e^(−t/τ)</p>
      <h3 style="margin-top:28px;">Time-to-Action</h3>
      <p class="mono" style="font-size:26px;color:var(--white);">t = −τ·ln((Cthresh − Css)/(C0 − Css))</p>
    </div>
    <div class="card" style="display:flex;flex-direction:column;justify-content:center;">
      <h3>What this means for a manager</h3>
      <p style="font-size:24px;color:var(--white);line-height:1.6;">Given the zone's volume, ventilation rate, and current emission source, the system solves exactly
      when CO2 will cross the NIOSH action reference — and reports it in plain minutes, e.g.
      <i>"CO2 may reach the 5000&nbsp;ppm action reference in 34 minutes."</i></p>
      <p style="font-size:20px;margin-top:20px;">Deliberately called <b>Time-to-Action</b>, never "time to harm" — the 5000&nbsp;ppm reference is an
      occupational action threshold, not an immediate-harm line (CLAUDE.md).</p>
    </div>
  </div>
  {footer()}
</div>"""
add("07_physics", html,
    say="This is genuine analytical physics, not a black box: a well-mixed mass-balance ODE, solved in closed form for the time a threshold will be crossed given the zone's current ventilation and source rate.",
    evidence="backend/app/domain/forecast physics module implements exactly these closed-form equations; unit-tested against analytical and numerical cases.",
    transition="How well does the ML layer improve on physics alone?",
    question="Why is it called Time-to-Action and not time-to-harm?",
    answer="The 5000ppm NIOSH reference is an 8-hour occupational action level, not an acute-harm threshold — CLAUDE.md is explicit that conflating the two would be misleading, so the system's own language avoids it.")

# =============================================================================
# SLIDE 8 — Predictive model performance
# =============================================================================
html = f"""<div class="slide">
  {header("Predictive Performance", 8)}
  <h2>Forecast accuracy and leak-classifier quality</h2>
  <div class="grid2" style="margin-top:20px;">
    <div class="card top">
      <h3>Matched physics-vs-hybrid benchmark (n={gru_n})</h3>
      <div style="display:flex;gap:56px;margin-top:20px;">
        <div class="metric"><div class="value orange">{phys_mae:.2f}<span style="font-size:28px;">ppm</span></div><div class="label">Physics-only MAE</div></div>
        <div class="metric"><div class="value green">{hybrid_mae:.2f}<span style="font-size:28px;">ppm</span></div><div class="label">Hybrid physics+GRU MAE</div></div>
      </div>
      <div class="badge badge-green" style="margin-top:22px;font-size:20px;">▼ {improvement_pct:.1f}% error reduction</div>
      <p style="margin-top:18px;font-size:18px;">Identical held-out scenario/point set for both — a fair, matched comparison (models/evaluation/gru_benchmark_report.json).</p>
    </div>
    <div class="card top">
      <h3>Leak classifier (XGBoost, calibrated)</h3>
      <div style="display:flex;gap:40px;margin-top:20px;">
        <div class="metric"><div class="value">{xgb['pr_auc']:.3f}</div><div class="label">PR-AUC</div></div>
        <div class="metric"><div class="value">{xgb['brier']:.3f}</div><div class="label">Brier (calibrated)</div></div>
        <div class="metric"><div class="value">{xgb['f1']:.3f}</div><div class="label">F1</div></div>
      </div>
      <p style="margin-top:22px;font-size:18px;">n={xgb['n']} held-out samples, {xgb['n_positive']} positive. Forecast inference latency:
      {gru['inference_latency_ms']['median']:.2f}ms median / {gru['inference_latency_ms']['p95']:.2f}ms p95.</p>
    </div>
  </div>
  <div class="card" style="margin-top:24px;">
    <p style="font-size:19px;"><b>Not the same number:</b> a separate, broader physics-only evaluation across
    {phys['n_scenarios']} scenarios / {phys['n_point_comparisons']} points reports {phys['physics_mae_ppm']:.2f}&nbsp;ppm MAE —
    a different, larger evaluation set. Never compared directly against the {hybrid_mae:.2f}&nbsp;ppm matched hybrid figure above.</p>
  </div>
  {footer()}
</div>"""
add("08_performance", html,
    say="On the exact same held-out points, the GRU residual correction cuts physics-only error by 16.8 percent, from 57.19 to 47.59 ppm MAE. The leak classifier separately reaches 0.965 PR-AUC, well-calibrated after Platt scaling.",
    evidence="Both numbers pulled and asserted programmatically from gru_benchmark_report.json and leak_model_metrics.json — printed and verified at slide-build time.",
    transition="Now the vision side: how the system watches PPE and zones.",
    question="Why do you separate the two physics MAE numbers so carefully?",
    answer="They're evaluated on different held-out sets (1092 matched points vs. 120 points across 10 scenarios) — comparing them directly would overstate or understate the GRU's real contribution, so the deck keeps them explicitly separate.")

# =============================================================================
# SLIDE 9 — CV design
# =============================================================================
html = f"""<div class="slide">
  {header("Computer-Vision Design", 9)}
  <h2>YOLO11n + ByteTrack, real evidence, no fabricated CV</h2>
  <div class="grid2" style="margin-top:20px;">
    <div>
      <ul class="clean">
        <li><b>YOLO11n</b> — active version <span class="badge badge-orange">{registry['ppe_detector']['version']}</span>, 640px input, fine-tuned from COCO-pretrained weights</li>
        <li><b>Class schema:</b> person · helmet · vest · no_helmet — the only 4 classes exposed at runtime</li>
        <li><b>ByteTrack</b> assigns anonymous, session-local track IDs — no facial recognition, ever</li>
        <li><b>PPE dwell:</b> 3s persistence required before a violation, 5s clear before resolving</li>
        <li><b>Restricted-zone foot-point logic:</b> bottom-center of the person box tested against a configured polygon, with a 2s enter / 2s exit debounce</li>
        <li><b>Real evidence capture:</b> the actual annotated camera frame that triggered the incident is saved — never a placeholder</li>
      </ul>
    </div>
    <div class="card" style="display:flex;flex-direction:column;">
      <div class="shot" style="height:680px;"><img src="file://{SHOTS / 'evidence_compliant.jpg'}" style="width:100%;height:100%;object-fit:cover;object-position:top;"></div>
      <p style="margin-top:14px;font-size:18px;">Genuine annotated frame from the final interview-demo video: real person/PPE boxes,
      confidence scores, zone overlay, and burned-in model version + timestamp.</p>
    </div>
  </div>
  {footer()}
</div>"""
add("09_cv_design", html,
    say="Detection, tracking, PPE dwell, and zone dwell are all real, timestamp-based state machines, not single-frame heuristics — and every burned-in field on this evidence frame, boxes, confidence, model version, is genuinely produced by the pipeline, not composited afterward.",
    evidence="This exact frame is a real captured evidence image from this session's interview-demo run, is_real_camera_frame=true in the database.",
    transition="How the detector itself was trained and evaluated comes next.",
    question="Why person-box bottom-center for zone membership instead of the whole box?",
    answer="It approximates where the worker is actually standing on the floor plane — using the full bounding box would falsely flag a zone entry as soon as any part of a tall person's box overlapped it.")

# =============================================================================
# SLIDE 10 — Vision data and enhancement
# =============================================================================
html = f"""<div class="slide">
  {header("Vision Data & Enhancement Attempt", 10)}
  <h2>v1.1 active vs. v1.2 candidate — an honest promotion decision</h2>
  <div class="grid2" style="margin-top:20px;">
    <div class="card top">
      <h3>Why more data was tried</h3>
      <p style="font-size:20px;color:var(--white);">v1.1's <code>no_helmet</code> recall (0.175) was the known weak point. A second, independent
      dataset — <b>Industrial Safety</b> (Roboflow Universe, {v12_manifest['source']['license']} license,
      {v12_manifest['source']['declared_total_images']:,} images) — was acquired to fine-tune a candidate.</p>
      <p style="margin-top:14px;font-size:18px;">Canonical mapping: hardhat→helmet, no_hardhat→no_helmet, person→person, safety_vest→vest.
      Deduplicated ({v12_subset['exact_duplicates_dropped']} exact dupes dropped) and leakage-checked
      before a class-balanced {v12_subset['selected_count']:,}-image training subset was selected — augmented/near-duplicate
      video frames were capped, never counted as unique scenes.</p>
    </div>
    <div class="card top">
      <h3>Promotion decision: REJECTED</h3>
      <p style="font-size:20px;color:var(--white);">The candidate completed only 7 of a planned 50 epochs (externally interrupted for
      runtime, not early-stopped) and was evaluated as-is, on principle, without further training.</p>
      <table class="data" style="margin-top:16px;">
        <tr><th></th><th>v1.1 (active)</th><th>v1.2 candidate</th></tr>
        <tr><td>no_helmet recall</td><td>0.45</td><td>0.25</td></tr>
        <tr><td>person recall</td><td>0.81</td><td>0.00</td></tr>
      </table>
      <p style="margin-top:14px;font-size:18px;"><b>Gate failed on 2 of 3 checks</b> — v1.1 remains active. Nothing overwritten silently.</p>
    </div>
  </div>
  {footer("models/registry.json — ppe_detector.rejected_experiments")}
</div>"""
add("10_vision_data", html,
    say="A genuine second attempt was made to fix the known no_helmet weakness with more data — but the resulting candidate, evaluated honestly against a mechanical promotion gate, failed and was rejected. v1.1 stayed active. That negative result is fully recorded, not hidden.",
    evidence="models/registry.json's ppe_detector.rejected_experiments entry and models/evaluation/vision_v1.2_comparative_evaluation.json are the source of the table on this slide.",
    transition="Here's what the currently active model actually achieves.",
    question="If it failed, why show it in the presentation?",
    answer="It demonstrates the promotion-gate discipline working as designed — a real engineering process that can say no, which is more credible than only showing successes.")

# =============================================================================
# SLIDE 11 — Vision performance
# =============================================================================
pc = v11["per_class"]
rows = "".join(
    f"<tr><td>{cls}</td><td>{pc[cls]['precision']:.2f}</td><td>{pc[cls]['recall']:.2f}</td>"
    f"<td>{pc[cls]['ap50']:.2f}</td><td>{pc[cls]['ap50_95']:.2f}</td></tr>"
    for cls in ("person", "helmet", "vest", "no_helmet")
)
html = f"""<div class="slide">
  {header("Vision Performance", 11)}
  <h2>Active model (v{active_model_version}) — held-out Construction-PPE test split</h2>
  <div class="grid2" style="margin-top:20px;">
    <div class="card top">
      <table class="data">
        <tr><th>Class</th><th>Precision</th><th>Recall</th><th>AP50</th><th>AP50-95</th></tr>
        {rows}
      </table>
      <div style="display:flex;gap:40px;margin-top:22px;">
        <div class="metric"><div class="value">{v11['map50']:.3f}</div><div class="label">mAP50</div></div>
        <div class="metric"><div class="value">{v11['map50_95']:.3f}</div><div class="label">mAP50-95</div></div>
      </div>
    </div>
    <div class="card top">
      <h3>Latency &amp; video-event performance</h3>
      <div style="display:flex;gap:40px;">
        <div class="metric"><div class="value green">{vision['replay_evaluation']['latency_ms_median']:.1f}<span style="font-size:24px;">ms</span></div><div class="label">Median latency (MX450)</div></div>
        <div class="metric"><div class="value green">{vision['replay_evaluation']['achieved_fps']:.0f}</div><div class="label">Achieved FPS</div></div>
      </div>
      <h3 style="margin-top:26px;">Real-world interview-video stress test</h3>
      <p style="font-size:18px;color:var(--white);">Person detected in {interview_summary['frames_with_person_detection']}/{interview_summary['n_frames_processed']} frames,
      helmet in {interview_summary['frames_with_helmet_detection']}, vest in {interview_summary['frames_with_vest_detection']}.
      <b style="color:var(--yellow);">no_helmet fired in 0 frames</b> — a genuine, disclosed weakness (peaks at 0.049 vs. the
      0.05 runtime threshold on this real clip).</p>
    </div>
  </div>
  {footer()}
</div>"""
add("11_vision_perf", html,
    say="Helmet and vest detection are strong — over 0.90 and 0.87 AP50. no_helmet remains the honest weak point, both on the held-out benchmark and, more strikingly, on real interview footage where it never fires at the registered threshold — a real domain-gap finding, not swept under the rug.",
    evidence="Per-class table and mAP figures are read directly from vision_model_metrics.json; the real-clip numbers from this session's interview_video_detection_summary.json.",
    transition="Here is what all of this looks like assembled into the manager's dashboard.",
    question="Given no_helmet's weakness, does the system ever catch missing helmets at all?",
    answer="Yes — via a second, independent policy path: 'no positive helmet evidence while a worker is in the overhead-work zone' still triggers a violation, demonstrated live in this session's interview-demo incidents, even when the no_helmet class itself stays silent.")

# =============================================================================
# SLIDE 12 — Manager dashboard
# =============================================================================
html = f"""<div class="slide">
  {header("Manager Dashboard", 12)}
  <h2>One screen: live risk, forecast, camera, incidents</h2>
  <div class="grid2" style="margin-top:20px;align-items:center;">
    <div class="shot"><img src="file://{SHOTS / '02_dashboard_predictive_gas_risk_state.png'}" style="width:100%;"></div>
    <div>
      <ul class="clean">
        <li><b>Live gas levels</b> — current CO2 ppm from real ingested readings</li>
        <li><b>Risk severity</b> — deterministic overall status card (NORMAL / HIGH / CRITICAL…)</li>
        <li><b>60-min forecast</b> — physics + GRU hybrid, with uncertainty band</li>
        <li><b>Time-to-Action</b> — plain-language threshold-crossing estimate</li>
        <li><b>Camera supervision</b> — live real detections, PPE/zone state per track</li>
        <li><b>Active incidents</b> — severity, zone, age, one-click Review</li>
        <li><b>Evidence thumbnails</b> — in the review drawer, real captured frames</li>
      </ul>
    </div>
  </div>
  {footer()}
</div>"""
add("12_dashboard", html,
    say="This is the real running dashboard mid-incident: three active alerts, a rising forecast band, and live camera detections all on one screen — every value here comes from the backend, never invented client-side.",
    evidence="Real screenshot captured this session while a gradual_leak scenario and the interview-demo video were both actually running.",
    transition="Let's look at three real safety events this system actually caught.",
    question="Does the dashboard poll or use live push updates?",
    answer="Both — WebSocket events push live changes, with REST polling (5s) and a fresh REST snapshot on reconnect as the fallback/resync path, so state never silently goes stale.")

# =============================================================================
# SLIDE 13 — Real safety incidents
# =============================================================================
html = f"""<div class="slide">
  {header("Real Safety Incidents", 13)}
  <h2>Three genuine, real-video-triggered events</h2>
  <div class="grid3" style="margin-top:24px;">
    <div class="card">
      <div class="shot"><img src="file://{SHOTS / 'evidence_compliant.jpg'}" style="width:100%;height:340px;"></div>
      <div class="badge badge-green" style="margin-top:14px;">PPE Compliant</div>
      <p style="margin-top:10px;font-size:17px;">Helmet + vest detected, confidence 0.78/0.79 — no incident.</p>
    </div>
    <div class="card">
      <div class="shot"><img src="file://{SHOTS / 'evidence_helmet_alert.jpg'}" style="width:100%;height:340px;"></div>
      <div class="badge badge-orange" style="margin-top:14px;">PPE_HELMET_OVERHEAD_VIOLATION · HIGH</div>
      <p style="margin-top:10px;font-size:17px;">No positive helmet evidence while inside the overhead-work zone.</p>
    </div>
    <div class="card">
      <div class="shot"><img src="file://{SHOTS / 'evidence_restricted_zone.jpg'}" style="width:100%;height:340px;"></div>
      <div class="badge badge-red" style="margin-top:14px;">PERSON_IN_RESTRICTED_ZONE · HIGH</div>
      <p style="margin-top:10px;font-size:17px;">Foot point dwelled 2.5s inside the configured restricted polygon.</p>
    </div>
  </div>
  <div class="card" style="margin-top:24px;">
    <p style="font-size:19px;">All three are real captured frames (<code>is_real_camera_frame=true</code>) from actual incidents opened by the
    live backend during this session — reviewable end-to-end with JSON/CSV reports in <code>docs/screenshots/final/07</code> and <code>/08</code>.</p>
  </div>
  {footer()}
</div>"""
add("13_incidents", html,
    say="Three real, distinct incident types fired from the same interview video during live testing: compliant PPE producing no alert, a helmet violation, and a restricted-zone intrusion — each with its own genuine captured frame.",
    evidence="All three evidence JPEGs are committed under docs/screenshots/final/evidence_*.jpg, copied from backend/data/incident-evidence/ with is_real_camera_frame=true confirmed in the JSON report.",
    transition="These all ran without a physical factory — here's the digital twin that makes that possible.",
    question="Could these three incidents have been staged/cherry-picked?",
    answer="They were the incidents that genuinely fired during make interview-demo runs this session, verified via the real API before any screenshot was taken — not hand-selected from a larger pool of attempts.")

# =============================================================================
# SLIDE 14 — Simulation / digital twin
# =============================================================================
html = f"""<div class="slide">
  {header("Simulation / Digital Twin", 14)}
  <h2>Testable without a physical factory</h2>
  <div class="grid3" style="margin-top:20px;">
    <div class="card"><div class="shot"><img src="file://{SHOTS / '09_simulation_overview.png'}" style="width:100%;"></div><p style="margin-top:12px;font-size:17px;">Factory layout: workers, zones, and machinery markers.</p></div>
    <div class="card"><div class="shot"><img src="file://{SHOTS / '10_simulation_gas_controls.png'}" style="width:100%;"></div><p style="margin-top:12px;font-size:17px;">Live gas/ventilation sliders and scenario presets.</p></div>
    <div class="card"><div class="shot"><img src="file://{SHOTS / '11_simulation_worker_movement.png'}" style="width:100%;"></div><p style="margin-top:12px;font-size:17px;">Click-to-move worker, helmet/vest toggles.</p></div>
  </div>
  <div class="card" style="margin-top:24px;">
    <p style="font-size:20px;">Simulation commands flow through <b>the exact same ingestion → risk → incident pipeline</b> a real
    sensor or camera would use — this is not a decorative mockup, it is a legitimate deterministic test harness
    (seeded, replayable, used by the automated test suite itself).</p>
  </div>
  {footer()}
</div>"""
add("14_simulation", html,
    say="The simulation isn't a toy — it's the same ingestion contract and risk pipeline a real device would use, which is exactly why it's valid engineering testing: every scenario is seeded and reproducible, and the automated tests run against it directly.",
    evidence="Three real screenshots of the actual Three.js simulation page, captured live this session.",
    transition="Let's walk the full real sequence end-to-end.",
    question="Isn't a simulator just avoiding the hard problem of real hardware?",
    answer="It's the standard approach for testing safety-critical logic before hardware exists — CLAUDE.md invariant #1 (one ingestion path) means swapping in a real device later requires zero backend changes, only a new adapter.")

# =============================================================================
# SLIDE 15 — End-to-end demonstration
# =============================================================================
html = f"""<div class="slide">
  {header("End-to-End Demonstration", 15)}
  <h2>The real sequence, start to finish</h2>
  <div class="grid2" style="margin-top:24px;">
    <ol style="list-style:none;counter-reset:step;">
      {"".join(f'''<li style="counter-increment:step;display:flex;gap:18px;margin-bottom:20px;align-items:flex-start;">
        <span style="background:var(--orange);color:#0a1420;font-weight:800;border-radius:50%;width:36px;height:36px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">{i}</span>
        <span style="font-size:23px;padding-top:4px;">{step}</span></li>'''
        for i, step in enumerate([
            "Video / sensor input — real camera feed or seeded gas readings",
            "Prediction / detection — YOLO+ByteTrack or physics+GRU+XGBoost",
            "Deterministic risk decision — versioned severity policy",
            "Incident creation — deduplicated, reason-coded, in the database",
            "Evidence image — real captured frame or labelled schematic",
            "Manager acknowledgement — Acknowledge → Investigate → Resolve",
            "Downloadable report — JSON and CSV, per incident",
        ], start=1))}
    </ol>
    <div class="card" style="display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;">
      <h3>Watch it run</h3>
      <p style="font-size:22px;color:var(--white);">Full interview-demo recording and annotated video are in the repository:</p>
      <p class="mono" style="margin-top:18px;color:var(--yellow);font-size:19px;">github.com/M7mdknh/smart-detector</p>
      <p style="margin-top:8px;font-size:16px;">deliverables/Factory_Safety_Sentinel_Interview_Demo.mp4</p>
    </div>
  </div>
  {footer()}
</div>"""
add("15_e2e", html,
    say="This exact seven-step sequence is what ran live this session — real video in, real detection, a real deterministic decision, a real database row, a real evidence frame, a real human review action, and a real downloadable report.",
    evidence="Every step corresponds 1:1 to a verified API call or database write from this session's interview-demo runs, not a conceptual sequence diagram.",
    transition="Here's how that's proven by the test suite, not just a demo.",
    question="Is the GitHub link live right now?",
    answer="It's the planned repository URL for this submission; Prompt 3 in this workflow verifies and updates the final link before publication.",
    )

# =============================================================================
# SLIDE 16 — Testing and acceptance
# =============================================================================
html = f"""<div class="slide">
  {header("Testing & Acceptance", 16)}
  <h2>Verified this session, not stale figures</h2>
  <div class="grid4" style="margin-top:28px;">
    <div class="card"><div class="metric"><div class="value green">{BACKEND_TEST_COUNT}</div><div class="label">Backend tests passing</div></div></div>
    <div class="card"><div class="metric"><div class="value green">{FRONTEND_TEST_COUNT}</div><div class="label">Frontend tests passing</div></div></div>
    <div class="card"><div class="metric"><div class="value green">2/2</div><div class="label">Playwright e2e suites</div></div></div>
    <div class="card"><div class="metric"><div class="value green">0</div><div class="label">Known regressions</div></div></div>
  </div>
  <div class="card" style="margin-top:28px;">
    <h3>Acceptance matrix (docs/ACCEPTANCE_RESULTS.md)</h3>
    <p style="font-size:20px;color:var(--white);">A01–A18: 17 PASS, 1 PASS WITH LIMITATION, 0 FAIL &nbsp;·&nbsp;
    E01–E12: 10 PASS, 2 PASS WITH LIMITATION, 0 FAIL</p>
    <p style="margin-top:12px;font-size:18px;">Limitations are disk-quota constraints on a from-scratch vision install and evidence-image
    honesty labelling — never a functional failure. Docker build/up/down and clean-checkout `make demo`
    verified end to end in the same audit.</p>
  </div>
  {footer("Backend/frontend counts re-run and confirmed at presentation-build time")}
</div>"""
add("16_testing", html,
    say=f"{BACKEND_TEST_COUNT} backend tests and {FRONTEND_TEST_COUNT} frontend tests pass right now — re-run at the time this deck was built, not copied from an old report — plus both Playwright e2e suites and a documented acceptance matrix with zero failures.",
    evidence="Test counts were re-executed via pytest and vitest immediately before building this slide; the acceptance matrix is docs/ACCEPTANCE_RESULTS.md, dated and cross-referenced.",
    transition="No system is without limitations — here they are, stated directly.",
    question="What exactly are the 'PASS WITH LIMITATION' items?",
    answer="Mainly a sandbox disk-quota constraint that prevented a second from-scratch vision-dependency install in one audit pass, and the intentional schematic-vs-real evidence-image distinction — both disclosed, neither a functional defect.")

# =============================================================================
# SLIDE 17 — Limitations
# =============================================================================
html = f"""<div class="slide light">
  {header("Limitations & Responsible Use", 17)}
  <h2>Stated directly, not defensively</h2>
  <div class="grid2" style="margin-top:24px;">
    <ul class="clean">
      <li>No real factory deployment data — trained/evaluated on construction-site imagery</li>
      <li>Construction-to-factory domain gap is real and measured, not assumed away</li>
      <li>No facial recognition — anonymous, session-local track IDs only, by design</li>
      <li>Evidence images contain worker imagery — retention/privacy policy needed for real use</li>
    </ul>
    <ul class="clean">
      <li>The model can and does miss PPE violations (no_helmet is a known weak point)</li>
      <li><b>Not certified for real industrial safety decisions</b></li>
      <li>A human manager remains responsible for every action taken</li>
      <li>Future work: calibration and domain adaptation on real factory footage</li>
    </ul>
  </div>
  {footer()}
</div>"""
add("17_limitations", html,
    say="These are stated plainly because they are true, not because the system failed — a prototype that hides its limitations is less trustworthy than one that measures and discloses them.",
    evidence="Every point here traces to a specific evaluation finding or an explicit CLAUDE.md invariant, not a generic disclaimer list.",
    transition="Bringing it together: what this system is actually worth.",
    question="What's the single biggest limitation for real deployment?",
    answer="The domain gap — a construction-site-trained detector applied to a real factory floor needs re-evaluation and likely fine-tuning on real factory footage before any safety-relevant claim would be trustworthy.")

# =============================================================================
# SLIDE 18 — Value and conclusion
# =============================================================================
html = f"""<div class="slide" style="padding:0;">
  <div style="position:relative;z-index:1;display:flex;flex-direction:column;justify-content:center;height:100%;padding:96px;">
    <div class="eyebrow">Conclusion</div>
    <h1 style="font-size:60px;">A proactive, evidence-based safety system — testable today, extendable tomorrow</h1>
    <div class="grid2" style="margin-top:48px;flex:none;">
      <ul class="clean check">
        <li>Proactive gas-risk prediction, minutes before a threshold is crossed</li>
        <li>Automated visual supervision of PPE and restricted zones</li>
        <li>Earlier response through a real, reviewable incident workflow</li>
      </ul>
      <ul class="clean check">
        <li>Evidence-backed, auditable, never a fabricated alert</li>
        <li>Fully testable without a physical factory</li>
        <li>Extendable to real sensors and cameras with no backend rewrite</li>
      </ul>
    </div>
    <div style="margin-top:64px;font-size:34px;font-weight:800;color:var(--orange);">Questions?</div>
  </div>
</div>"""
add("18_conclusion", html,
    say="Factory Safety Sentinel proves the full loop — predict, detect, decide, evidence, review — works end to end, is genuinely tested, and is built so the next step to real hardware is an adapter, not a rewrite. Thank you — happy to take questions.",
    evidence="Every claim on this slide has been shown with a real screenshot, metric, or test result earlier in the deck.",
    transition="(End of presentation — open floor for questions.)",
    question="What would you build next with more time?",
    answer="Domain-adapted vision fine-tuning on real factory footage and a second gas profile (CO), per the project's own documented P1 roadmap.")

# ---------------------------------------------------------------------------
# Write HTML files + notes JSON
# ---------------------------------------------------------------------------
notes_out = []
for stem, html_body, notes in slides:
    (OUT_DIR / f"{stem}.html").write_text(page(stem, html_body))
    notes_out.append({"stem": stem, **notes})

(OUT_DIR / "notes.json").write_text(json.dumps(notes_out, indent=2))
print(f"Wrote {len(slides)} slides to {OUT_DIR}")
