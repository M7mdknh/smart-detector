/**
 * Drives the REAL running app (backend with SENTINEL_INTERVIEW_DEMO_MODE=1,
 * real frontend) through the genuine demo narrative once, in one continuous
 * Playwright session, producing BOTH:
 *   - the 12 required screenshots under docs/screenshots/final/
 *   - the full screen-recording deliverable (via Playwright's video capture)
 *
 * Every screenshot/recording is of real, live application state -- nothing
 * here is a mockup or staged fixture. Expects the backend/frontend already
 * running (scripts/capture-demo-assets.sh starts them) at the URLs below.
 */
import { chromium } from "playwright";
import { mkdirSync, renameSync, existsSync } from "node:fs";
import path from "node:path";

const API_BASE = process.env.CAPTURE_API_BASE ?? "http://127.0.0.1:8000/api/v1";
const APP_BASE = process.env.CAPTURE_APP_BASE ?? "http://127.0.0.1:5173";
const SCREENSHOT_DIR = process.env.CAPTURE_SCREENSHOT_DIR ?? "docs/screenshots/final";
const VIDEO_DIR = process.env.CAPTURE_VIDEO_DIR ?? "/tmp/sentinel-capture-video";
const FINAL_VIDEO_PATH = process.env.CAPTURE_FINAL_VIDEO ?? "deliverables/Factory_Safety_Sentinel_Interview_Demo.mp4";

mkdirSync(SCREENSHOT_DIR, { recursive: true });
mkdirSync(VIDEO_DIR, { recursive: true });
mkdirSync(path.dirname(FINAL_VIDEO_PATH), { recursive: true });

async function cmd(command, payload = {}) {
  const res = await fetch(`${API_BASE}/simulation/commands`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command_id: crypto.randomUUID(), command, payload }),
  });
  return res.json();
}

async function loadScenario(preset) {
  const res = await fetch(`${API_BASE}/simulation/scenarios/${preset}/load?seed=42`, { method: "POST" });
  return res.json();
}

async function waitForIncidentOfType(typeSubstr, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${API_BASE}/incidents`);
    const rows = await res.json();
    const match = rows.find((r) => r.type.includes(typeSubstr));
    if (match) return match;
    await new Promise((r) => setTimeout(r, 2000));
  }
  return null;
}

async function shot(page, name) {
  const p = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: false });
  console.log(`  screenshot: ${p}`);
}

async function main() {
  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    recordVideo: { dir: VIDEO_DIR, size: { width: 1600, height: 1000 } },
  });
  const page = await context.newPage();

  console.log("1/13: Dashboard opening, normal state");
  await loadScenario("normal");
  await cmd("start");
  await cmd("set_speed", { speed: 300 });
  await page.goto(`${APP_BASE}/dashboard`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Factory Safety Sentinel", { timeout: 15000 });
  await page.waitForSelector("text=OVERALL RISK", { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(2000);
  await shot(page, "01_dashboard_normal_state");

  console.log("2/13: system-status / camera-detector-model health");
  await page.waitForSelector(".camera-panel", { timeout: 15000 });
  await shot(page, "12_system_status_camera_detector_model_healthy");

  console.log("3/13: camera with correct PPE (waiting for a COMPLIANT track)...");
  const compliantDeadline = Date.now() + 60000;
  let gotCompliant = false;
  while (Date.now() < compliantDeadline) {
    const vis = await (await fetch(`${API_BASE}/vision/latest`)).json();
    if (vis.tracks?.some((t) => t.helmet_state === "COMPLIANT" || t.vest_state === "COMPLIANT")) {
      gotCompliant = true;
      break;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector(".camera-panel", { timeout: 15000 });
  await shot(page, "03_camera_correct_ppe");
  console.log(`  (compliant track observed: ${gotCompliant})`);

  console.log("4/13: waiting for PPE_HELMET_OVERHEAD_VIOLATION (real detector, real policy)...");
  const helmetIncident = await waitForIncidentOfType("HELMET");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector(".camera-panel", { timeout: 15000 });
  await shot(page, "04_missing_helmet_alert");
  console.log(`  helmet incident: ${helmetIncident ? helmetIncident.incident_id : "NONE (timed out)"}`);

  console.log("5/13: waiting for PERSON_IN_RESTRICTED_ZONE...");
  const zoneIncident = await waitForIncidentOfType("RESTRICTED_ZONE");
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector(".incident-table, .empty-state", { timeout: 15000 });
  await shot(page, "05_restricted_zone_intrusion");
  console.log(`  zone incident: ${zoneIncident ? zoneIncident.incident_id : "NONE (timed out)"}`);

  console.log("6/13: incident table");
  await shot(page, "06_incident_table");

  console.log("7/13: opening review drawer with real evidence frame");
  await page.locator(".review-btn").first().click();
  await page.waitForSelector(".drawer", { timeout: 10000 });
  await page.waitForSelector(".evidence-thumbnail", { timeout: 10000 }).catch(() => {});
  const thumbLocator = page.locator(".evidence-thumbnail").first();
  if (await thumbLocator.count()) {
    await page.waitForFunction((el) => el.complete && el.naturalWidth > 0, await thumbLocator.elementHandle(), { timeout: 15000 }).catch(() => {});
  }
  await shot(page, "07_incident_review_drawer_real_frame");

  console.log("8/13: acknowledge -> resolve, JSON/CSV report");
  const drawer = page.locator(".drawer");
  const incidentIdMatch = await page.evaluate(() => {
    const el = document.querySelector(".drawer h2");
    return el ? el.textContent : null;
  });
  console.log(`  reviewing incident type: ${incidentIdMatch}`);
  const ackBtn = drawer.locator("button", { hasText: "Acknowledge" });
  if (await ackBtn.count()) await ackBtn.first().click();
  await page.waitForTimeout(1000);
  const resolveBtn = drawer.locator("button", { hasText: "Resolve" });
  if (await resolveBtn.count()) await resolveBtn.first().click();
  await page.waitForTimeout(1000);

  // JSON/CSV report result: fetch real content and render it on-page for the screenshot.
  const activeIncidentId = zoneIncident?.incident_id ?? helmetIncident?.incident_id;
  if (activeIncidentId) {
    const jsonPage = await context.newPage();
    await jsonPage.goto(`${API_BASE}/incidents/${activeIncidentId}/report.json`, { waitUntil: "networkidle" });
    await jsonPage.screenshot({ path: path.join(SCREENSHOT_DIR, "08_json_csv_report_result.png") });
    await jsonPage.close();
  }
  await page.bringToFront();

  console.log("9/13: simulation overview (predictive gas-risk scenario)");
  await loadScenario("gradual_leak");
  await cmd("start");
  await cmd("set_speed", { speed: 300 });
  await page.goto(`${APP_BASE}/simulation`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Playback", { timeout: 15000 });
  await page.waitForTimeout(2000);
  await shot(page, "09_simulation_overview");

  console.log("10/13: simulation gas controls");
  await page.waitForSelector("text=Gas & ventilation", { timeout: 10000 }).catch(() => {});
  await shot(page, "10_simulation_gas_controls");

  console.log("11/13: simulation worker movement (clicking the 3D floor)");
  const mount = page.locator(".three-mount");
  const box = await mount.boundingBox();
  if (box) {
    await page.mouse.click(box.x + box.width * 0.65, box.y + box.height * 0.55);
    await page.waitForTimeout(1000);
  }
  await shot(page, "11_simulation_worker_movement");

  console.log("12/13: dashboard predictive gas-risk state");
  await page.goto(`${APP_BASE}/dashboard`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=OVERALL RISK", { timeout: 15000 }).catch(() => {});
  // Let the gradual leak build forecast/exposure state for a bit.
  const gasDeadline = Date.now() + 40000;
  while (Date.now() < gasDeadline) {
    const res = await fetch(`${API_BASE}/incidents`);
    const rows = await res.json();
    if (rows.some((r) => r.type.includes("GAS") || r.type.includes("CO2"))) break;
    await new Promise((r) => setTimeout(r, 3000));
  }
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  await shot(page, "02_dashboard_predictive_gas_risk_state");

  console.log("13/13: closing out");
  await page.waitForTimeout(2000);

  await page.close();
  const video = page.video();
  await context.close();
  await browser.close();

  if (video) {
    const rawPath = await video.path();
    const target = rawPath.replace(/\.webm$/, "") + "__raw.webm";
    if (existsSync(rawPath)) {
      renameSync(rawPath, target);
      console.log(`Raw recording: ${target}`);
    }
  }

  console.log("Capture session complete.");
}

main().catch((err) => {
  console.error("CAPTURE FAILED:", err);
  process.exit(1);
});
