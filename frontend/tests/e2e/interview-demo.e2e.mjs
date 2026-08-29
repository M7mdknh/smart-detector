/**
 * Interview-demo end-to-end acceptance test (make interview-demo-e2e). Exits
 * non-zero on failure.
 *
 * Expects a backend and frontend already running with
 * SENTINEL_INTERVIEW_DEMO_MODE=1 and SENTINEL_VISION_REPLAY_PATH pointed at
 * demo-assets/interview_compilation_source.mp4 (the shell wrapper
 * scripts/run-interview-demo-e2e.sh starts them). Loads a scenario through
 * the real ingestion path, raises the tick speed so the risk pipeline
 * evaluates real CV_MODEL evidence promptly (see
 * scripts/run-interview-demo.sh for why), waits for a genuine incident via
 * the real API, then drives the actual dashboard UI: opens the review
 * drawer, verifies the real captured evidence thumbnail loads, exercises
 * Acknowledge -> Resolve through the real buttons, and confirms no browser
 * console errors -- covering the "genuine video-triggered incident with real
 * evidence, reviewable end-to-end" requirement, not just the API surface
 * dashboard.e2e.mjs already covers for the simulator path.
 */
import { chromium } from "playwright";
import assert from "node:assert/strict";

const API_BASE = process.env.E2E_API_BASE ?? "http://127.0.0.1:8124/api/v1";
const APP_BASE = process.env.E2E_APP_BASE ?? "http://127.0.0.1:5184";

async function waitForIncident(timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${API_BASE}/incidents`);
    const rows = await res.json();
    if (rows.length > 0) return rows;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error(`no incident appeared within ${timeoutMs}ms`);
}

async function main() {
  const loadRes = await fetch(`${API_BASE}/simulation/scenarios/normal/load?seed=42`, { method: "POST" });
  assert.equal(loadRes.status, 200, "scenario load should succeed");

  const startRes = await fetch(`${API_BASE}/simulation/commands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command_id: crypto.randomUUID(), command: "start" }),
  });
  assert.equal(startRes.status, 200, "start should succeed");

  // See scripts/run-interview-demo.sh: default speed=1 ticks the risk
  // pipeline once per 5 SIMULATED minutes -- far too sparse to reliably
  // catch the video's transient real-time PPE state within the 30s CV_MODEL
  // evidence window.
  const speedRes = await fetch(`${API_BASE}/simulation/commands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command_id: crypto.randomUUID(), command: "set_speed", payload: { speed: 300 } }),
  });
  assert.equal(speedRes.status, 200, "set_speed should succeed");

  const incidents = await waitForIncident();
  console.log(`Genuine incident(s) via real API: ${incidents.map((i) => i.type).join(", ")}`);
  const target = incidents[0];

  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors = [];
  page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
  page.on("pageerror", (err) => errors.push(String(err)));

  await page.goto(`${APP_BASE}/dashboard`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Factory Safety Sentinel", { timeout: 15000 });

  // Camera panel: real detections, provenance always labelled CV_MODEL.
  await page.waitForSelector("text=source: CV_MODEL", { timeout: 15000 });

  // Incident table: the real incident just created via the API must appear
  // in the actual rendered table (not a value invented by the frontend).
  // IncidentTable renders each row's `explanation` text, not the raw `type`
  // enum value -- match on that (React Query polls every 5s, see
  // frontend/src/dashboard/hooks.ts, so this does not require a websocket
  // event to have arrived before the page loaded).
  await page.waitForSelector(`text=${target.explanation}`, { timeout: 20000 });

  const reviewButtons = page.locator(".review-btn");
  assert.ok((await reviewButtons.count()) > 0, "expected at least one Review button");
  await reviewButtons.first().click();

  await page.waitForSelector(".drawer", { timeout: 10000 });
  await page.waitForSelector("text=Evidence", { timeout: 10000 });

  // Real evidence thumbnail: must actually finish loading (not a broken/placeholder image).
  const thumb = page.locator(".evidence-thumbnail").first();
  await thumb.waitFor({ state: "visible", timeout: 10000 });
  await page.waitForFunction(
    (el) => el.complete && el.naturalWidth > 0,
    await thumb.elementHandle(),
    { timeout: 15000 },
  );
  const naturalWidth = await thumb.evaluate((img) => img.naturalWidth);
  assert.ok(naturalWidth > 0, "evidence thumbnail should be a real, loaded image (naturalWidth > 0)");

  // Acknowledge -> Resolve through the real buttons (real backend transitions).
  // Scoped to the drawer itself: the incident-table's filter tab is literally
  // labelled "Resolved", which a page-wide `hasText: "Resolve"` locator also
  // matches -- found live, it kept clicking the wrong element.
  const drawer = page.locator(".drawer");
  const ackButton = drawer.locator("button", { hasText: "Acknowledge" });
  if (await ackButton.count()) {
    await ackButton.first().click();
    await drawer.locator("button", { hasText: "Resolve" }).first().waitFor({ timeout: 10000 });
  }
  const resolveButton = drawer.locator("button", { hasText: "Resolve" });
  if (await resolveButton.count()) {
    await resolveButton.first().click();
    await drawer.locator("text=Audit history").waitFor({ timeout: 10000 });
  }

  await page.goto(`${APP_BASE}/simulation`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Playback", { timeout: 15000 });

  assert.deepEqual(errors, [], `expected no browser console errors, got: ${JSON.stringify(errors)}`);

  await browser.close();
  console.log("INTERVIEW-DEMO E2E OK: real incident reviewed end-to-end with a genuine evidence frame, no console errors.");
}

main().catch((err) => {
  console.error("INTERVIEW-DEMO E2E FAILED:", err);
  process.exit(1);
});
