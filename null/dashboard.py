"""Live training dashboard.

Read-only web view of NULL training state — compliance trend, recent
cycles, failure-mode distribution, bank sizes, cost-so-far. Polls the
JSONL stores every few seconds and refreshes; never writes anything.

Stdlib-only (http.server + json) so no new dependencies. Single HTML
page is embedded below; vanilla JS polls /api/state and updates the
DOM.

Usage::

    null dashboard --sessions logs/sim/sessions.jsonl \\
                   --prefix-bank logs/sim/prefix_bank.jsonl \\
                   --negative-bank logs/sim/negative_bank.jsonl \\
                   --port 8420

Open http://localhost:8420 while a training run writes to the same
JSONL paths. The dashboard updates ~every 3s.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from null import cost as null_cost
from null.negative_bank import JsonlNegativeBank
from null.prefix_bank import JsonlPrefixBank
from null.storage import JsonlSessionStore

log = logging.getLogger("null.dashboard")


# ---------- state aggregation ----------------------------------------


def _aggregate_state(
    sessions_path: Path,
    prefix_bank_path: Optional[Path],
    negative_bank_path: Optional[Path],
) -> dict:
    """Read JSONLs and return the JSON payload the dashboard consumes."""
    cycles: list[dict] = []
    by_target_compliance: dict[str, list[float]] = defaultdict(list)
    failure_counts: Counter = Counter()
    advances = 0

    if sessions_path.exists():
        store = JsonlSessionStore(sessions_path)
        for r in store:
            score = float((r.compliance or {}).get("score", 0.0))
            cycles.append({
                "session": r.session_id,
                "cycle": r.cycle_index,
                "scenario": r.scenario_id,
                "target": r.target,
                "score": score,
                "replayed": r.replayed,
                "failure_mode": r.failure_mode,
                "ts": r.ended_ts,
                "input_tok": r.input_tokens,
                "output_tok": r.output_tokens,
            })
            by_target_compliance[r.target].append(score)
            if r.failure_mode:
                failure_counts[r.failure_mode] += 1
            if score >= 0.85:
                advances += 1

    avg_compliance = (
        sum(c["score"] for c in cycles) / len(cycles) if cycles else 0.0
    )
    last_20 = cycles[-20:]

    cost_rows = []
    if sessions_path.exists():
        for tc in null_cost.summarize(JsonlSessionStore(sessions_path)):
            cost_rows.append({
                "target": tc.target,
                "cycles": tc.cycles,
                "input_tokens": tc.input_tokens,
                "output_tokens": tc.output_tokens,
                "estimated_usd": tc.estimated_usd,
            })

    return {
        "total_cycles": len(cycles),
        "advances": advances,
        "avg_compliance": round(avg_compliance, 4),
        "compliance_trend": [c["score"] for c in cycles[-100:]],
        "by_target_compliance": {
            k: round(sum(v) / len(v), 4) for k, v in by_target_compliance.items() if v
        },
        "failure_counts": dict(failure_counts.most_common()),
        "recent_cycles": list(reversed(last_20)),
        "prefix_bank_size": JsonlPrefixBank(prefix_bank_path).count() if prefix_bank_path else 0,
        "negative_bank_size": JsonlNegativeBank(negative_bank_path).count() if negative_bank_path else 0,
        "cost": cost_rows,
    }


# ---------- HTTP handler ---------------------------------------------


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NULL · training dashboard</title>
<style>
  :root {
    --bg: #0a0a0a;
    --panel: #111;
    --text: #d0d0d0;
    --dim: #777;
    --accent: #5fd87f;
    --warn: #d8a85f;
    --bad: #d85f5f;
    --grid: #1f1f1f;
    --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text); font-family: var(--mono); font-size: 13px; }
  header { padding: 16px 24px; border-bottom: 1px solid var(--grid); display: flex; justify-content: space-between; align-items: baseline; }
  header h1 { margin: 0; font-size: 16px; letter-spacing: 0.1em; }
  header .stamp { color: var(--dim); font-size: 11px; }
  main { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px 24px; }
  .panel { background: var(--panel); border: 1px solid var(--grid); padding: 14px 16px; border-radius: 4px; }
  .panel h2 { margin: 0 0 12px 0; font-size: 11px; color: var(--dim); letter-spacing: 0.15em; text-transform: uppercase; font-weight: 500; }
  .stat { display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px; }
  .stat .key { color: var(--dim); width: 180px; flex-shrink: 0; }
  .stat .val { color: var(--text); font-variant-numeric: tabular-nums; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 4px 8px 4px 0; border-bottom: 1px solid var(--grid); }
  th { color: var(--dim); font-weight: 500; font-size: 11px; }
  td.score { font-variant-numeric: tabular-nums; }
  .ok { color: var(--accent); }
  .warn { color: var(--warn); }
  .bad { color: var(--bad); }
  .dim { color: var(--dim); }
  .full { grid-column: 1 / -1; }
  svg { display: block; }
  .bar { fill: var(--accent); }
  .bar.warn { fill: var(--warn); }
  .bar.bad { fill: var(--bad); }
</style>
</head>
<body>
<header>
  <h1>N U L L · training dashboard</h1>
  <span class="stamp" id="stamp">…</span>
</header>
<main>
  <section class="panel">
    <h2>Cycle totals</h2>
    <div class="stat"><span class="key">total cycles</span><span class="val" id="total-cycles">—</span></div>
    <div class="stat"><span class="key">advances (≥0.85)</span><span class="val" id="advances">—</span></div>
    <div class="stat"><span class="key">avg compliance</span><span class="val" id="avg-compliance">—</span></div>
    <div class="stat"><span class="key">prefix bank size</span><span class="val" id="prefix-size">—</span></div>
    <div class="stat"><span class="key">negative bank size</span><span class="val" id="negative-size">—</span></div>
  </section>
  <section class="panel">
    <h2>Compliance trend (last 100 cycles)</h2>
    <svg id="trend" width="100%" height="120" preserveAspectRatio="none" viewBox="0 0 400 120"></svg>
  </section>
  <section class="panel full">
    <h2>Failure modes</h2>
    <div id="failure-rows"></div>
  </section>
  <section class="panel full">
    <h2>Recent cycles (last 20)</h2>
    <table>
      <thead><tr><th>scenario</th><th>target</th><th>score</th><th>failure</th><th>replayed</th></tr></thead>
      <tbody id="recent"></tbody>
    </table>
  </section>
  <section class="panel full">
    <h2>Cost summary</h2>
    <table>
      <thead><tr><th>target</th><th>cycles</th><th>in</th><th>out</th><th>est. usd</th></tr></thead>
      <tbody id="cost"></tbody>
    </table>
  </section>
</main>
<script>
async function poll() {
  try {
    const r = await fetch('/api/state', {cache: 'no-store'});
    const s = await r.json();
    const $ = id => document.getElementById(id);
    $('total-cycles').textContent = s.total_cycles;
    $('advances').textContent = s.advances;
    const ac = s.avg_compliance.toFixed(3);
    $('avg-compliance').textContent = ac;
    $('avg-compliance').className = 'val ' + (s.avg_compliance >= 0.85 ? 'ok' : s.avg_compliance >= 0.5 ? 'warn' : 'bad');
    $('prefix-size').textContent = s.prefix_bank_size;
    $('negative-size').textContent = s.negative_bank_size;

    // Trend bars
    const trend = $('trend');
    trend.innerHTML = '';
    const xs = s.compliance_trend;
    const w = 400 / Math.max(xs.length, 1);
    xs.forEach((v, i) => {
      const h = Math.max(2, v * 120);
      const cls = v >= 0.85 ? 'bar' : v >= 0.5 ? 'bar warn' : 'bar bad';
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', (i * w).toFixed(2));
      rect.setAttribute('y', (120 - h).toFixed(2));
      rect.setAttribute('width', Math.max(1, w - 1).toFixed(2));
      rect.setAttribute('height', h.toFixed(2));
      rect.setAttribute('class', cls);
      trend.appendChild(rect);
    });

    // Failure modes
    const fm = $('failure-rows');
    const total = Object.values(s.failure_counts).reduce((a, b) => a + b, 0) || 1;
    fm.innerHTML = Object.entries(s.failure_counts).map(([k, v]) => {
      const pct = ((v / total) * 100).toFixed(1);
      return '<div class="stat"><span class="key">' + k + '</span><span class="val">' + v + ' <span class="dim">(' + pct + '%)</span></span></div>';
    }).join('') || '<div class="dim">no failures recorded yet</div>';

    // Recent
    $('recent').innerHTML = s.recent_cycles.map(c => {
      const cls = c.score >= 0.85 ? 'ok' : c.score >= 0.5 ? 'warn' : 'bad';
      return '<tr><td>' + c.scenario + '</td><td>' + c.target + '</td><td class="score ' + cls + '">' + c.score.toFixed(3) + '</td><td class="dim">' + (c.failure_mode || '—') + '</td><td class="dim">' + (c.replayed ? 'yes' : 'no') + '</td></tr>';
    }).join('');

    // Cost
    $('cost').innerHTML = s.cost.map(c => {
      const usd = c.estimated_usd === null ? '<span class="dim">—</span>' : '$' + c.estimated_usd.toFixed(4);
      return '<tr><td>' + c.target + '</td><td>' + c.cycles + '</td><td>' + c.input_tokens.toLocaleString() + '</td><td>' + c.output_tokens.toLocaleString() + '</td><td>' + usd + '</td></tr>';
    }).join('');

    $('stamp').textContent = new Date().toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  } catch (e) {
    document.getElementById('stamp').textContent = 'error: ' + e.message;
  }
}
poll();
setInterval(poll, 3000);
</script>
</body>
</html>
"""


def _make_handler(
    sessions_path: Path,
    prefix_bank_path: Optional[Path],
    negative_bank_path: Optional[Path],
):
    """Closure over the JSONL paths to keep the handler signature simple."""

    class _DashboardHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # quiet stderr spam
            log.debug(fmt, *args)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/" or path == "/index.html":
                self._send(200, _HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/state":
                try:
                    state = _aggregate_state(sessions_path, prefix_bank_path, negative_bank_path)
                    body = json.dumps(state).encode("utf-8")
                    self._send(200, body, "application/json")
                except Exception as e:
                    log.exception("state aggregation failed")
                    body = json.dumps({"error": str(e)}).encode("utf-8")
                    self._send(500, body, "application/json")
                return
            self._send(404, b'{"error":"not found"}', "application/json")

    return _DashboardHandler


def serve(
    *,
    sessions_path: Path,
    prefix_bank_path: Optional[Path] = None,
    negative_bank_path: Optional[Path] = None,
    host: str = "127.0.0.1",
    port: int = 8420,
) -> None:
    """Block on the dashboard server. Ctrl-C to stop."""
    handler_cls = _make_handler(sessions_path, prefix_bank_path, negative_bank_path)
    server = ThreadingHTTPServer((host, port), handler_cls)
    log.info("dashboard listening on http://%s:%d/  (Ctrl-C to stop)", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
