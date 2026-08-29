"""Shared design system (CSS) for the Factory Safety Sentinel final presentation.
1920x1080 (16:9) HTML slides, rendered by render_slides.mjs (Playwright).
"""

CSS = """
:root {
  --navy: #0a1420;
  --navy-2: #101c2c;
  --navy-3: #16263a;
  --white: #f4f7fb;
  --gray: #94a3b8;
  --gray-dim: #64748b;
  --orange: #ff7a1a;
  --yellow: #ffc93c;
  --green: #3cb878;
  --red: #e63946;
  --border: #24374f;
  --font: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  --mono: "SF Mono", "Consolas", "Menlo", monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1920px; height: 1080px; overflow: hidden; }
body {
  font-family: var(--font);
  background: var(--navy);
  color: var(--white);
  position: relative;
}
.slide { width: 1920px; height: 1080px; position: relative; padding: 64px 96px; display: flex; flex-direction: column; }
.slide.light { background: var(--white); color: #0a1420; }
.slide.light .muted { color: #475569; }
.slide.light ul.clean li { color: #0a1420; }
.slide.light p { color: #334155; }
.slide.light .card { background: #f8fafc; border: 1px solid #e2e8f0; }

.eyebrow { color: var(--orange); font-size: 22px; font-weight: 700; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 14px; }
h1 { font-size: 58px; font-weight: 800; line-height: 1.12; letter-spacing: -0.5px; }
h2 { font-size: 44px; font-weight: 800; margin-bottom: 8px; letter-spacing: -0.3px; }
h3 { font-size: 26px; font-weight: 700; color: var(--orange); text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 12px; }
p { font-size: 24px; line-height: 1.5; color: var(--gray); }
.muted { color: var(--gray); }
.big { font-size: 30px; }

.header-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 40px; }
.brand { display: flex; align-items: center; gap: 14px; font-weight: 800; font-size: 22px; color: var(--white); }
.brand .dot { width: 14px; height: 14px; border-radius: 3px; background: var(--orange); }
.pagenum { color: var(--gray-dim); font-size: 18px; font-variant-numeric: tabular-nums; }

.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 56px; flex: 1; min-height: 0; }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 40px; }
.grid4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 32px; }

.card { background: var(--navy-2); border: 1px solid var(--border); border-radius: 16px; padding: 32px; display: flex; flex-direction: column; justify-content: center; }
.card.top { justify-content: flex-start; }
.card.light { background: #ffffff; border: 1px solid #e2e8f0; }

.badge { display: inline-flex; align-items: center; gap: 8px; padding: 6px 16px; border-radius: 999px; font-size: 16px; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; }
.badge-green { background: rgba(60,184,120,0.15); color: var(--green); border: 1px solid rgba(60,184,120,0.4); }
.badge-orange { background: rgba(255,122,26,0.15); color: var(--orange); border: 1px solid rgba(255,122,26,0.4); }
.badge-red { background: rgba(230,57,70,0.15); color: var(--red); border: 1px solid rgba(230,57,70,0.4); }
.badge-gray { background: rgba(148,163,184,0.12); color: var(--gray); border: 1px solid rgba(148,163,184,0.3); }
.badge-yellow { background: rgba(255,201,60,0.15); color: var(--yellow); border: 1px solid rgba(255,201,60,0.4); }

.metric { display: flex; flex-direction: column; gap: 6px; }
.metric .value { font-size: 64px; font-weight: 800; line-height: 1; letter-spacing: -1px; }
.metric .label { font-size: 18px; color: var(--gray); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
.metric .value.green { color: var(--green); }
.metric .value.orange { color: var(--orange); }
.metric .value.red { color: var(--red); }
.metric .value.yellow { color: var(--yellow); }

.shot { border-radius: 14px; border: 1px solid var(--border); overflow: hidden; box-shadow: 0 20px 50px rgba(0,0,0,0.45); }
.shot img { display: block; width: 100%; height: 100%; object-fit: cover; }

ul.clean { list-style: none; }
ul.clean li { position: relative; padding-left: 34px; margin-bottom: 16px; font-size: 24px; color: var(--white); line-height: 1.4; }
ul.clean li::before { content: ""; position: absolute; left: 0; top: 10px; width: 12px; height: 12px; border-radius: 3px; background: var(--orange); }
ul.clean.check li::before { background: var(--green); }

.footer-line { position: absolute; left: 96px; right: 96px; bottom: 40px; display: flex; justify-content: space-between; align-items: center; font-size: 16px; color: var(--gray-dim); border-top: 1px solid var(--border); padding-top: 18px; }

table.data { width: 100%; border-collapse: collapse; }
table.data th { text-align: left; font-size: 16px; color: var(--gray); text-transform: uppercase; letter-spacing: 1px; padding: 10px 14px; border-bottom: 2px solid var(--border); }
table.data td { padding: 14px 14px; font-size: 22px; border-bottom: 1px solid var(--border); }
table.data tr:last-child td { border-bottom: none; }

.mono { font-family: var(--mono); }

.flow { display: flex; align-items: center; gap: 0; flex-wrap: wrap; }
.flow-step { background: var(--navy-2); border: 1px solid var(--border); border-radius: 12px; padding: 18px 24px; font-size: 20px; font-weight: 700; text-align: center; }
.flow-arrow { color: var(--orange); font-size: 28px; padding: 0 14px; }

.pill-row { display: flex; gap: 14px; flex-wrap: wrap; }
.pill { background: var(--navy-3); border: 1px solid var(--border); border-radius: 999px; padding: 10px 20px; font-size: 18px; font-weight: 600; }
"""

FONT_PRELOAD = ""


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>{CSS}</style>
</head><body>{body}</body></html>"""
