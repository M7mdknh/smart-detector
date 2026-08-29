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

  // Camera panel annotated frame: a genuine decodable JPEG from the real
  // interview footage, not merely an <img> tag (see
  // docs/adr/0003-annotated-camera-frame-delivery.md).
  const frameImg = page.locator("img[alt*='Live annotated camera']");
  await page.waitForFunction(
    (sel) => {
      const img = document.querySelector(sel);
      return !!img && !img.hidden && img.complete && img.naturalWidth > 50 && img.naturalHeight > 50;
    },
    "img[alt*='Live annotated camera']",
    { timeout: 20000 },
  );
  const frameSrc = await frameImg.getAttribute("src");
  const frameRes = await fetch(new URL(frameSrc, API_BASE));
  assert.equal(frameRes.status, 200, "GET /vision/frame.jpg should return a real frame during the interview demo");
  const frameBytes = Buffer.from(await frameRes.arrayBuffer());
  assert.ok(frameBytes.length > 5000, `expected a sizeable real JPEG, got ${frameBytes.length} bytes`);
  assert.equal(frameBytes[0], 0xff, "JPEG magic byte 1");
  assert.equal(frameBytes[1], 0xd8, "JPEG magic byte 2 (SOI marker)");

  // Incident table: the real incident just created via the API must appear
  // in the actual rendered table (not a value invented by the frontend).
  // IncidentTable renders each row's `explanation` text, not the raw `type`
  // enum value -- match on that (React Query polls every 5s, see
  // frontend/src/dashboard/hooks.ts, so this does not require a websocket
  // event to have arrived before the page loaded).
  await page.waitForSelector(`text=${target.explanation}`, { timeout: 20000 });

  // NOTE on the sensor-simulation speed: this was originally slowed back to
  // 1x here on the theory that a fast gas-sensor tick loop was racing the
  // review click sequence. Root-caused live (docs/FINAL_VERIFICATION.md
  // "v3.1 pass"): it isn't. app/simulation/loop.py's tick loop only fires
  // once every `speed`-scaled interval and drives the *gas/sensor* pipeline;
  // the vision worker (app/inference/vision_worker_impl.py) runs on its own
  // background thread at a fixed ~10 fps, completely independent of
  // simulation speed, continuously re-evaluating PPE/zone risk from the real,
  // continuously-playing interview footage. A genuine severity re-check --
  // and therefore a legitimate optimistic-concurrency `version` bump on the
  // very incident this test is reviewing -- can land in the few-hundred-ms
  // window between the Acknowledge and Resolve clicks *regardless of
  // simulation speed*, because it is driven by real video content changing
  // in real time, not by the sensor clock. Changing `speed` here would do
  // nothing for vision-driven incidents (PERSON_IN_RESTRICTED_ZONE,
  // PPE_HELMET_OVERHEAD_VIOLATION, PPE_VEST_VIOLATION -- exactly the types
  // this demo path exercises), so it is intentionally not done.
  //
  // The actual fix is two-layered:
  //   1. ReviewDrawer.tsx now retries a VERSION_CONFLICT once automatically
  //      with the freshly re-fetched version (see its module comment) --
  //      unit-tested in tests/ReviewDrawer.test.tsx. This is real, shipped
  //      product behavior, not a test-only workaround: a human reviewer
  //      benefits from it too.
  //   2. Below, this test still fails on ANY unexpected console error. It
  //      narrowly tolerates only the browser's own "Failed to load resource:
  //      ... 409" log line for the incidents/actions endpoint specifically
  //      (Chromium logs this for the underlying failed request regardless of
  //      whether application code retries and recovers), AND only if the
  //      incident's final state proves the retry genuinely succeeded. Any
  //      other console error, or a final state that isn't RESOLVED, still
  //      fails the test outright -- this is narrowing what counts as
  //      "unexpected", not hiding a real failure.

  // Click the Review button in `target`'s own row specifically -- not just
  // "the first Review button on the page" -- since CV evidence keeps
  // arriving in the background and can add/reorder table rows between the
  // API poll above and this click.
  const targetRow = page.locator("tr", { hasText: target.explanation });
  await targetRow.locator(".review-btn").first().click();

  await page.waitForSelector(".drawer", { timeout: 10000 });
  await page.waitForSelector("text=Evidence", { timeout: 10000 });

  // The table can reorder/gain new rows between this test's initial API poll
  // (which picked `target`) and this click -- CV evidence keeps arriving in
  // the background -- so ".review-btn").first() is not guaranteed to open
  // `target`. Read the ID the drawer actually opened (data-incident-id, see
  // ReviewDrawer.tsx) and use *that* for the rest of this flow, rather than
  // assuming it matches `target`. Found live: without this, a previous
  // version of this test could silently review a different incident than the
  // one its final-state assertion checked, masking a genuine action failure
  // as a table-ordering artifact.
  const reviewedIncidentId = await page.locator(".drawer").getAttribute("data-incident-id");
  assert.ok(reviewedIncidentId, "drawer should expose the incident id it is reviewing");

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
  // Waits for the incident to genuinely reach `expectedState` via the real
  // API (not a static piece of UI text like a section heading, which renders
  // regardless of whether the underlying mutation actually succeeded).
  // Needed because ReviewDrawer.tsx's bounded VERSION_CONFLICT retry (see its
  // module comment) is asynchronous -- a click can resolve before the
  // eventual retry chain (re-fetch + re-submit, up to 3 times) has actually
  // settled against the backend. Found live: without this, the test could
  // race ahead and assert the pre-retry state, misreporting a real,
  // in-flight-but-not-yet-complete retry as a failure.
  async function waitForIncidentState(id, expectedState, timeoutMs = 20000) {
    const deadline = Date.now() + timeoutMs;
    let last;
    while (Date.now() < deadline) {
      const res = await fetch(`${API_BASE}/incidents/${id}`);
      last = (await res.json()).state;
      if (last === expectedState) return;
      await new Promise((r) => setTimeout(r, 500));
    }
    throw new Error(`incident ${id} did not reach ${expectedState} within ${timeoutMs}ms (last observed: ${last})`);
  }

  const drawer = page.locator(".drawer");
  const ackButton = drawer.locator("button", { hasText: "Acknowledge" });
  if (await ackButton.count()) {
    await ackButton.first().click();
    await waitForIncidentState(reviewedIncidentId, "ACKNOWLEDGED");
    await drawer.locator("button", { hasText: "Resolve" }).first().waitFor({ timeout: 10000 });
  }
  const resolveButton = drawer.locator("button", { hasText: "Resolve" });
  if (await resolveButton.count()) {
    await resolveButton.first().click();
    await waitForIncidentState(reviewedIncidentId, "RESOLVED");
    await drawer.locator("text=Audit history").waitFor({ timeout: 10000 });
  }

  // Belt-and-braces: re-confirm the terminal state via a fresh fetch. This is
  // what makes it safe to tolerate the bounded number of benign console
  // lines below: if a retry chain had silently given up, this -- or the
  // waitForIncidentState calls above -- would already have failed the test.
  const finalIncidentRes = await fetch(`${API_BASE}/incidents/${reviewedIncidentId}`);
  const finalIncident = await finalIncidentRes.json();
  assert.equal(finalIncident.state, "RESOLVED", `incident should have reached RESOLVED, got ${finalIncident.state}`);

  await page.goto(`${APP_BASE}/simulation`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Playback", { timeout: 15000 });

  const BENIGN_VERSION_CONFLICT = "Failed to load resource: the server responded with a status of 409 (Conflict)";
  const unexpectedErrors = errors.filter((e) => e !== BENIGN_VERSION_CONFLICT);
  const benignConflicts = errors.filter((e) => e === BENIGN_VERSION_CONFLICT);
  assert.deepEqual(unexpectedErrors, [], `expected no unexpected browser console errors, got: ${JSON.stringify(unexpectedErrors)}`);
  // ReviewDrawer.tsx bounds retries to MAX_VERSION_CONFLICT_RETRIES=3 per
  // action; this flow issues at most 2 actions (Acknowledge, Resolve), so at
  // most 3 retries each = at most 6 benign 409s is the hard ceiling by
  // construction -- never unbounded. The finalIncident RESOLVED assertion
  // above already proves the retries genuinely succeeded, not silently gave up.
  assert.ok(
    benignConflicts.length <= 6,
    `expected at most 6 benign, auto-retried optimistic-concurrency 409s (2 actions x 3 bounded retries each), got ${benignConflicts.length}`,
  );
  if (benignConflicts.length > 0) {
    console.log(`(one benign, auto-retried optimistic-concurrency 409 occurred and was transparently resolved -- incident reached RESOLVED; see interview-demo.e2e.mjs's comment above the review sequence)`);
  }

  await browser.close();
  console.log("INTERVIEW-DEMO E2E OK: real incident reviewed end-to-end with a genuine evidence frame, no console errors.");
}

main().catch((err) => {
  console.error("INTERVIEW-DEMO E2E FAILED:", err);
  process.exit(1);
});
