"""Converts docs/FINAL_PROJECT_REPORT.md to a print-styled HTML file for PDF
rendering (scripts/presentation/render_report_pdf.mjs) and for visual review.
"""
import sys
from pathlib import Path

import markdown

REPO = Path("/home/muhammad/Documents/smart-detector")
SRC = REPO / "docs" / "FINAL_PROJECT_REPORT.md"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/report.html")

md_text = SRC.read_text()
body_html = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])

CSS = """
@page { size: Letter; margin: 20mm 14mm 20mm 14mm; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  color: #16202c;
  font-size: 11pt;
  line-height: 1.55;
  max-width: 100%;
  margin: 0 auto;
}
h1 { font-size: 22pt; color: #0a1420; border-bottom: 3px solid #ff7a1a; padding-bottom: 8px; margin-top: 0; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 16pt; color: #0a1420; margin-top: 28px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; }
h3 { font-size: 12.5pt; color: #b45309; margin-top: 18px; }
p, li, h1, h2, h3 { max-width: 760px; }
p { margin: 8px 0; }
code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 9.5pt; word-break: break-word; }
pre { background: #0f1c2e; color: #e2e8f0; padding: 12px 14px; border-radius: 8px; overflow-x: auto; font-size: 9pt; page-break-inside: avoid; max-width: 760px; }
pre code { background: none; color: inherit; padding: 0; }
table { border-collapse: collapse; table-layout: fixed; width: 100%; margin: 14px 0; font-size: 7.3pt; page-break-inside: avoid; }
th, td { border: 1px solid #cbd5e1; padding: 3px 5px; text-align: left; vertical-align: top; word-wrap: break-word; overflow-wrap: break-word; }
th { background: #f1f5f9; font-weight: 700; }
ul, ol { margin: 6px 0; padding-left: 24px; max-width: 760px; }
li { margin-bottom: 4px; }
hr { border: none; border-top: 1px solid #cbd5e1; margin: 24px 0; }
a { color: #b45309; }
strong { color: #0a1420; }
.titlepage { text-align: center; padding-top: 22vh; page-break-after: always; }
.titlepage h1 { border: none; font-size: 30pt; }
.titlepage .sub { font-size: 13pt; color: #475569; margin-top: 18px; }
"""

TITLE_HTML = """
<div class="titlepage">
  <div style="color:#ff7a1a;font-weight:800;letter-spacing:2px;">FACTORY SAFETY SENTINEL</div>
  <h1>Final Project Report</h1>
  <div class="sub">Smart-Facility Incident Detection System<br>Assessment Submission — 2026-08-29<br>
  Repository: github.com/M7mdknh/smart-detector</div>
</div>
"""

full_html = f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body>{TITLE_HTML}{body_html}</body></html>"""

OUT.write_text(full_html)
print(f"Wrote {OUT} ({len(md_text)} chars markdown -> {len(full_html)} chars html)")
