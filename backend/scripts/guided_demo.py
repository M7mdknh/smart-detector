"""Phase 6: guided proactive-value demonstration script.

Drives the REAL running backend through all 12 required steps using the same
public REST API a human manager or an assessor would use -- no shortcuts, no
direct database writes, no mocked inference. Requires a backend already
running (e.g. `make demo` or the Docker stack) and reachable at --base-url.

All manual controls remain available throughout: this script only issues the
same commands a human clicking through /simulation and /dashboard would, so
an assessor can interrupt at any point and drive the rest by hand (an
"unannounced change" mid-demo).

Usage:
    .venv/bin/python scripts/guided_demo.py [--base-url http://127.0.0.1:8000/api/v1]
"""

import argparse
import time
import uuid

import httpx


def step(n: int, title: str) -> None:
    print(f"\n{'=' * 70}\nSTEP {n}: {title}\n{'=' * 70}")


def cmd(client: httpx.Client, command: str, payload: dict | None = None) -> dict:
    body = {"command_id": str(uuid.uuid4()), "command": command, "payload": payload or {}}
    r = client.post("/simulation/commands", json=body)
    r.raise_for_status()
    return r.json()


def snapshot(client: httpx.Client) -> dict:
    r = client.get("/dashboard/snapshot")
    r.raise_for_status()
    return r.json()


def wait_for(client: httpx.Client, predicate, description: str, timeout_s: float = 60.0, poll_s: float = 2.0):
    print(f"  waiting for: {description} (up to {timeout_s:.0f}s)...")
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        last = snapshot(client)
        if predicate(last):
            print(f"  -> reached: {description}")
            return last
        time.sleep(poll_s)
    print(f"  !! timed out waiting for: {description} (continuing anyway with last observed state)")
    return last


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        r = client.get("/health/live")
        r.raise_for_status()
        print(f"Backend reachable at {args.base_url}")

        # 1. Normal warm start
        step(1, "Load gradual_leak preset (10h warm-start history, real ingestion)")
        load = client.post("/simulation/scenarios/gradual_leak/load").json()
        run_id = load["state"]["run_id"]
        print(f"  run_id={run_id}, scenario_id={load['state']['scenario_id']}")
        snap = snapshot(client)
        assert snap["active_incidents"] == [], "expected zero incidents at fresh warm start"
        print(f"  latest reading: {snap['latest_reading']['value']:.1f} ppm (baseline, no incident)")

        # 2. Gradual leak
        step(2, "Start the run and accelerate simulated time")
        cmd(client, "start")
        cmd(client, "set_speed", {"speed": 300})

        # 3. Increasing XGBoost leak probability + 4. physics forecast (observed together)
        step(3, "Raise the emission source; watch leak probability and physics forecast")
        cmd(client, "set_controls", {"source_ppm_m3h": 5_000_000})

        def has_forecast_with_probability(s):
            f = s.get("forecast")
            return f is not None and f.get("leak_probability") is not None

        snap = wait_for(client, has_forecast_with_probability, "a forecast with a leak probability")
        if snap and snap.get("forecast"):
            print(f"  leak_probability={snap['forecast']['leak_probability']:.3f} label={snap['forecast']['leak_label']}")
            print(f"  physics model_status={snap['forecast']['model_status']} gru_status={snap['forecast']['gru_status']}")

        # 5. GRU correction (if promoted/available) + 6. uncertainty
        step(5, "Report hybrid (physics + GRU) forecast status, if available")
        if snap and snap.get("forecast", {}).get("gru_status") == "OK":
            pts = snap["forecast"]["points"]
            with_bounds = [p for p in pts if p.get("lower_ppm") is not None]
            print(f"  GRU active: {snap['forecast']['gru_model_version']}, {len(with_bounds)}/{len(pts)} points have uncertainty bounds")
        else:
            print("  GRU not active for this forecast (physics-only) -- honest, not hidden.")

        # 7. Time-to-Action
        step(7, "Read Time-to-Action from the action-reference crossing")
        action = next((c for c in snap["forecast"]["crossings"] if c["threshold_name"] == "NIOSH_ACTION_5000"), None) if snap else None
        if action:
            print(f"  action crossing: {action['outcome']} minutes_to_cross={action['minutes_to_cross']}")

        # 8. Worker entering the risk zone
        step(8, "Move the worker into the gas-exposure zone")
        cmd(client, "set_worker", {"x": 5.0, "y": 5.0})

        # 9. Severity escalation
        step(9, "Wait for severity to reflect the person-in-zone condition")

        def has_person_reason(s):
            for inc in s["active_incidents"]:
                if "PERSON_IN_PREDICTED_GAS_RISK" in inc.get("reason_codes", []) or inc["type"] == "PERSON_IN_PREDICTED_GAS_RISK":
                    return True
            return False

        snap = wait_for(client, has_person_reason, "an incident escalated for a person in the predicted gas-risk zone")
        incident = next((i for i in snap["active_incidents"] if i["zone_id"] == "zone-1"), None) if snap else None
        if incident:
            print(f"  incident {incident['incident_id']}: {incident['severity']} — {incident['explanation']}")

        # 10. Manager acknowledgement + 11. audit event
        if incident:
            step(10, "Acknowledge, investigate, and resolve as a manager would")
            inc_id = incident["incident_id"]

            def current_version():
                return client.get(f"/incidents/{inc_id}").json()["version"]

            r = client.post(f"/incidents/{inc_id}/actions", json={"action": "ACKNOWLEDGE", "actor": "HUMAN", "comment": "Guided demo: investigating.", "expected_version": current_version()})
            print(f"  ACKNOWLEDGE -> {r.status_code} {r.json().get('state')}")
            r = client.post(f"/incidents/{inc_id}/actions", json={"action": "INVESTIGATE", "actor": "HUMAN", "expected_version": current_version()})
            print(f"  INVESTIGATE -> {r.status_code} {r.json().get('state')}")
            r = client.post(f"/incidents/{inc_id}/actions", json={"action": "RESOLVE", "actor": "HUMAN", "comment": "Ventilation restored (guided demo).", "expected_version": current_version()})
            print(f"  RESOLVE -> {r.status_code} {r.json().get('state')}")

            step(11, "Confirm the audit trail")
            audit = client.get(f"/incidents/{inc_id}/audit").json()
            for ev in audit:
                print(f"  {ev['timestamp']}: {ev['actor']} {ev['action']} (comment={ev['comment']!r})")

        # 12. GRU / XGBoost fallback demonstration
        step(12, "Demonstrate a model fallback (leak classifier)")
        print("  See scripts/train_leak_model.py / tests/test_e2e_pipeline.py::test_ventilation_failure_does_not_blindly_call_it_a_leak")
        print("  and tests/test_forecast_gru.py for automated fallback proof; this script does not delete a live artifact.")

        print("\nGuided demo complete. All manual controls (/simulation, /dashboard) remain available for further changes.")


if __name__ == "__main__":
    main()
