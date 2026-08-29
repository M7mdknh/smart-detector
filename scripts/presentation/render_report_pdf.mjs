// Renders the print-styled report HTML (scripts/presentation/build_report_html.py's
// output) to a single paginated PDF via Playwright/Chromium, honoring the
// HTML's own @page CSS (Letter, margins, page-break rules) rather than
// forcing a fixed slide-style page size the way render_slides.mjs does for
// the 16:9 deck.
import { chromium } from "playwright";
import path from "node:path";

const HTML_PATH = process.argv[2];
const PDF_PATH = process.argv[3];

async function main() {
  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.goto("file://" + path.resolve(HTML_PATH), { waitUntil: "networkidle" });
  await page.pdf({ path: PDF_PATH, format: "Letter", printBackground: true, preferCSSPageSize: true });
  await browser.close();
  console.log(`Wrote ${PDF_PATH}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
