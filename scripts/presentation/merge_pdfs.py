"""Merges per-slide PDFs (scripts/presentation/render_slides.mjs's PDF_DIR
output) into one ordered deck PDF, in filename-sorted order (slide stems are
zero-padded like "01_title", "02_...", so lexical sort is chronological).
"""
import sys
from pathlib import Path

from pypdf import PdfWriter

PDF_DIR = Path(sys.argv[1])
OUT_PATH = Path(sys.argv[2])

files = sorted(PDF_DIR.glob("*.pdf"))
if not files:
    raise SystemExit(f"no PDFs found in {PDF_DIR}")

writer = PdfWriter()
for f in files:
    writer.append(str(f))

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "wb") as fh:
    writer.write(fh)

print(f"Merged {len(files)} PDFs -> {OUT_PATH}")
