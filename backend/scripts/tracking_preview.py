"""Write a standalone HTML preview of a tracking clip (for reviewing motion, ADR-010).

Usage: uv run python scripts/tracking_preview.py [--from 11:30] [--to 13:00]
Reads data/tracking/<live match>.jsonl.gz (run `formline-gen tracking` first) and writes
docs/tracking/preview.html, which plays the clip in any browser with no server.
"""

import argparse
import json
from pathlib import Path

from formline.schema.tracking import read_tracking, tracking_path

BACKEND = Path(__file__).resolve().parents[1]
LIVE = "mtc_s26_md11_har_nor"


def clock(text: str) -> int:
    m, s = (int(x) for x in text.split(":"))
    return (m * 60 + s) * 1000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="11:30")
    ap.add_argument("--to", dest="end", default="13:00")
    ap.add_argument("--out", type=Path, default=BACKEND.parent / "docs" / "tracking" / "preview.html")
    args = ap.parse_args()
    lo, hi = clock(args.start), clock(args.end)
    period = 2 if lo >= 45 * 60_000 and hi > 47 * 60_000 else 1
    league = json.loads((BACKEND / "data" / "league.json").read_text())
    rows = [f.to_row() for f in read_tracking(tracking_path(BACKEND / "data", LIVE))
            if f.period == period and lo <= f.match_clock_ms <= hi]
    clubs = {c["club_id"]: c for c in league["clubs"]}
    matches = json.loads((BACKEND / "data" / "matches.json").read_text())
    match = next(m for m in matches if m["match_id"] == LIVE)
    home, away = clubs[match["home_club_id"]], clubs[match["away_club_id"]]
    names = {}
    for p in league["players"]:
        side = "h" if p["club_id"] == home["club_id"] else "a" if p["club_id"] == away["club_id"] else None
        if side:
            names[f"{side}{p['shirt_number']}"] = p["display_name"].split()[-1]
    html = TEMPLATE.replace("__ROWS__", json.dumps(rows, separators=(",", ":"))) \
        .replace("__NAMES__", json.dumps(names)) \
        .replace("__HOME__", json.dumps(_club(home))) \
        .replace("__AWAY__", json.dumps(_club(away)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out} ({len(rows)} frames, {args.start}–{args.end})")


def _club(c: dict) -> dict:
    return {"name": c["name"], "color": c["colors"]["primary"], "text": c["colors"]["secondary"]}


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tracking preview</title>
<style>
:root { --bg:#0d1117; --panel:#161b22; --text:#e6edf3; --muted:#8b949e; --pitch:#2f6b3a; --stripe:#2b6435; --accent:#f2a93b; }
body { margin:0; background:var(--bg); color:var(--text); font:15px system-ui, sans-serif; }
main { max-width:1100px; margin:0 auto; padding:16px; }
h1 { font-size:20px; margin:0 0 4px; } p { color:var(--muted); margin:0 0 12px; }
.bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:10px; }
button, select { background:var(--panel); color:var(--text); border:1px solid #30363d; border-radius:8px; padding:6px 12px; font:inherit; }
input[type=range] { flex:1; min-width:160px; }
#clock { font:600 20px ui-monospace, monospace; color:var(--accent); min-width:70px; }
svg { width:100%; height:auto; display:block; border-radius:10px; }
.lbl { font:600 11px system-ui; fill:#fff; paint-order:stroke; stroke:#0d1117; stroke-width:3px; }
</style></head><body><main>
<h1>Synthetic tracking preview</h1>
<p>All 22 players and the ball at 10 frames per second, derived from the event feed (ADR-010). Synthetic data; no real clubs or players.</p>
<div class="bar">
  <button id="play">Pause</button>
  <label>Speed <select id="speed"><option>1</option><option selected>2</option><option>5</option><option>10</option></select>×</label>
  <span id="clock">00:00</span>
  <input id="seek" type="range" min="0" value="0">
  <label><input id="names" type="checkbox"> names</label>
</div>
<svg id="pitch" viewBox="0 0 1050 680" role="img" aria-label="Tracking preview pitch"></svg>
</main>
<script>
const ROWS = __ROWS__, NAMES = __NAMES__, HOME = __HOME__, AWAY = __AWAY__;
const svg = document.getElementById('pitch'), NS = 'http://www.w3.org/2000/svg';
const el = (tag, attrs, parent = svg) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.appendChild(e); return e; };
el('rect', { width: 1050, height: 680, fill: 'var(--pitch)' });
for (const x of [105, 315, 525, 735, 945]) el('rect', { x, y: 0, width: 105, height: 680, fill: 'var(--stripe)' });
const g = el('g', { fill: 'none', stroke: 'rgba(255,255,255,.8)', 'stroke-width': 2 });
[['rect', { x: 2, y: 2, width: 1046, height: 676 }], ['line', { x1: 525, y1: 2, x2: 525, y2: 678 }], ['circle', { cx: 525, cy: 340, r: 91.5 }],
 ['rect', { x: 2, y: 138.5, width: 163, height: 403 }], ['rect', { x: 885, y: 138.5, width: 163, height: 403 }]].forEach(([t, a]) => el(t, a, g));
const players = {};
function marker(key, club) {
  const grp = el('g', {});
  el('circle', { r: 11, fill: club.color, stroke: club.text, 'stroke-width': 2 }, grp);
  const num = el('text', { y: 4, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 700, fill: club.text }, grp);
  num.textContent = key.slice(1);
  const lbl = el('text', { y: -16, 'text-anchor': 'middle', class: 'lbl' }, grp);
  lbl.textContent = NAMES[key] || '';
  return { grp, lbl };
}
const shadow = el('ellipse', { rx: 6, ry: 3, fill: 'rgba(0,0,0,.35)' });
const ball = el('circle', { r: 6, fill: '#fff', stroke: '#111', 'stroke-width': 1.5 });
const seek = document.getElementById('seek'); seek.max = ROWS.length - 1;
let i = 0, playing = true, speed = 2, last = performance.now(), acc = 0;
function lerp(a, b, u) { return a + (b - a) * u; }
function draw(pos) {
  pos = Math.min(Math.max(pos, 0), ROWS.length - 1);
  const n = Math.floor(pos), u = pos - n, a = ROWS[n], b = ROWS[Math.min(n + 1, ROWS.length - 1)];
  const seen = new Set();
  for (const [side, club] of [['h', HOME], ['a', AWAY]]) {
    const nb = new Map(b[side].map((p) => [p[0], p]));
    for (const p of a[side]) {
      const key = side + p[0], q = nb.get(p[0]) || p;
      players[key] ||= marker(key, club);
      const x = lerp(p[1], q[1], u) * 10.5, y = lerp(p[2], q[2], u) * 6.8;
      players[key].grp.setAttribute('transform', `translate(${x},${y})`);
      players[key].grp.style.display = '';
      players[key].lbl.style.display = document.getElementById('names').checked ? '' : 'none';
      seen.add(key);
    }
  }
  for (const k in players) if (!seen.has(k)) players[k].grp.style.display = 'none';
  const bx = lerp(a.b[0], b.b[0], u) * 10.5, by = lerp(a.b[1], b.b[1], u) * 6.8, bz = lerp(a.b[2], b.b[2], u);
  shadow.setAttribute('cx', bx); shadow.setAttribute('cy', by);
  ball.setAttribute('cx', bx); ball.setAttribute('cy', by - bz * 4); ball.setAttribute('r', 6 + bz * 0.6);
  const t = Math.round(lerp(a.t, b.t, u) / 1000);
  document.getElementById('clock').textContent = String(Math.floor(t / 60)).padStart(2, '0') + ':' + String(t % 60).padStart(2, '0');
  seek.value = n;
}
function tick(now) {
  const dt = Math.max(0, now - last); last = now;  // the first frame can predate `last`
  if (playing) { acc += dt * speed / 100; if (acc >= ROWS.length - 1) acc = 0; }
  draw(acc);
  requestAnimationFrame(tick);
}
document.getElementById('play').onclick = (e) => { playing = !playing; e.target.textContent = playing ? 'Pause' : 'Play'; };
document.getElementById('speed').onchange = (e) => { speed = Number(e.target.value); };
seek.oninput = () => { acc = Number(seek.value); };
requestAnimationFrame(tick);
</script></body></html>
"""

if __name__ == "__main__":
    main()
