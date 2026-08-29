import { chromium } from "playwright";

const HTML_PATH = process.argv[2];
const PDF_PATH = process.argv[3];

async function main() {
  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.goto("file://" + HTML_PATH, { waitUntil: "networkidle" });
  await page.pdf({
    path: PDF_PATH,
    format: "Letter",
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: "<div></div>",
    footerTemplate: `<div style="font-size:8px;width:100%;text-align:center;color:#94a3b8;">
      Factory Safety Sentinel — Final Project Report &nbsp;|&nbsp; Page <span class="pageNumber"></span> of <span class="totalPages"></span>
    </div>`,
    margin: { top: "22mm", bottom: "18mm", left: "20mm", right: "20mm" },
  });
  await browser.close();
  console.log(`Wrote ${PDF_PATH}`);
}

main().catch((err) => { console.error(err); process.exit(1); });
