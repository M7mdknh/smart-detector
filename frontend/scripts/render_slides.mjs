// Renders each slide HTML file to a full-resolution PNG (for QA/previews) and
// an individual single-page PDF (16:9, 13.333x7.5in) for later merging.
import { chromium } from "playwright";
import { readdirSync, mkdirSync } from "node:fs";
import path from "node:path";

const SLIDES_DIR = process.argv[2];
const PNG_DIR = process.argv[3];
const PDF_DIR = process.argv[4];

mkdirSync(PNG_DIR, { recursive: true });
mkdirSync(PDF_DIR, { recursive: true });

const files = readdirSync(SLIDES_DIR).filter((f) => f.endsWith(".html")).sort();

async function main() {
  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });

  for (const file of files) {
    const stem = file.replace(/\.html$/, "");
    const url = "file://" + path.join(SLIDES_DIR, file);
    await page.goto(url, { waitUntil: "networkidle" });
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(PNG_DIR, `${stem}.png`) });
    await page.pdf({
      path: path.join(PDF_DIR, `${stem}.pdf`),
      width: "1920px",
      height: "1080px",
      printBackground: true,
      margin: { top: 0, bottom: 0, left: 0, right: 0 },
    });
    console.log(`rendered ${stem}`);
  }

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
