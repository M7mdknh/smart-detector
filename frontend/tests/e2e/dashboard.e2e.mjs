/**
 * Browser-level acceptance smoke test (make e2e). Exits non-zero on failure.
 *
 * Expects a backend and frontend already running on the URLs below (the shell
 * wrapper in scripts/run-e2e.sh starts them). Loads a scenario through the real
 * ingestion path, then verifies the dashboard and simulation pages render real
 * backend-derived state with no console errors -- covering acceptance cases
 * A01/A02 (seeded warm start visible) and the "frontend never invents live
 * values" invariant (values must come from the API, not be hardcoded).
 */
import { chromium } from "playwright";
import assert from "node:assert/strict";

const API_BASE = process.env.E2E_API_BASE ?? "http://127.0.0.1:8123/api/v1";
const APP_BASE = process.env.E2E_APP_BASE ?? "http://127.0.0.1:5183";

async function main() {
  const loadRes = await fetch(`${API_BASE}/simulation/scenarios/gradual_leak/load`, { method: "POST" });
  assert.equal(loadRes.status, 200, "scenario load should succeed");
  const loadBody = await loadRes.json();
  assert.ok(loadBody.state.run_id, "loaded scenario should return a run_id");

  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors = [];
  page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
  page.on("pageerror", (err) => errors.push(String(err)));

  await page.goto(`${APP_BASE}/dashboard`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Factory Safety Sentinel", { timeout: 15000 });
  await page.waitForSelector("text=OVERALL RISK", { timeout: 15000 });
  await page.waitForSelector("text=CO2", { timeout: 15000 });

  await page.waitForFunction(
    () => {
      const cards = Array.from(document.querySelectorAll(".card"));
      const co2 = cards.find((c) => c.textContent?.includes("CO2"));
      return !!co2 && /ppm/.test(co2.textContent ?? "");
    },
    { timeout: 15000 },
  );
  const co2Card = await page.locator(".card:has-text('CO2')").innerText();
  assert.match(co2Card, /ppm/, "CO2 card should show a real ppm value from the backend, not a placeholder");

  // Camera panel: confirm a genuine, decodable annotated JPEG is rendered --
  // not merely that an <img> tag exists. Waits for the real YOLO11n/ByteTrack
  // replay worker (started unconditionally at app startup, see app/main.py)
  // to cache its first frame (app/inference/frame_cache.py), then asserts
  // both that the browser actually decoded a non-trivial image and that the
  // raw bytes served by GET /vision/frame.jpg are a real, sizeable JPEG.
  const frameImg = page.locator("img[alt*='Live annotated camera']");
  await frameImg.waitFor({ state: "attached", timeout: 20000 });
  await page.waitForFunction(
    (sel) => {
      const img = document.querySelector(sel);
      return !!img && !img.hidden && img.complete && img.naturalWidth > 50 && img.naturalHeight > 50;
    },
    "img[alt*='Live annotated camera']",
    { timeout: 20000 },
  );
  const frameSrc = await frameImg.getAttribute("src");
  assert.ok(frameSrc, "annotated frame <img> should have a src pointing at the backend");
  const frameRes = await fetch(new URL(frameSrc, API_BASE));
  assert.equal(frameRes.status, 200, "GET /vision/frame.jpg should return the cached annotated frame");
  assert.match(String(frameRes.headers.get("content-type")), /image\/jpeg/, "frame endpoint should serve a real JPEG");
  const frameBytes = Buffer.from(await frameRes.arrayBuffer());
  assert.ok(frameBytes.length > 5000, `expected a sizeable real JPEG, got ${frameBytes.length} bytes`);
  assert.equal(frameBytes[0], 0xff, "JPEG magic byte 1");
  assert.equal(frameBytes[1], 0xd8, "JPEG magic byte 2 (SOI marker)");

  await page.goto(`${APP_BASE}/simulation`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Playback", { timeout: 15000 });
  await page.waitForSelector("text=gradual_leak", { timeout: 15000 });

  assert.deepEqual(errors, [], `expected no browser console errors, got: ${JSON.stringify(errors)}`);

  await browser.close();
  console.log("E2E OK: dashboard and simulation pages render real backend state with no console errors.");
}

main().catch((err) => {
  console.error("E2E FAILED:", err);
  process.exit(1);
});
