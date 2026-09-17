#!/usr/bin/env python3
"""Render the public status page from the latest probe result."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

SITE_DIR = Path(os.environ.get("STATUS_DIR", "site"))
HISTORY_PATH = SITE_DIR / "history.json"
STATUS_PATH = SITE_DIR / "status.json"
INDEX_PATH = SITE_DIR / "index.html"
MAX_HISTORY = 288

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="refresh" content="300" />
  <title>eLibrary Sansad Status</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #1e293b;
      --text: #f8fafc;
      --muted: #94a3b8;
      --green: #4ade80;
      --red: #f87171;
      --blue: #38bdf8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .wrap { max-width: 960px; margin: 0 auto; padding: 24px 20px 32px; }
    h1 { margin: 0 0 4px; font-size: 28px; }
    .sub { color: var(--muted); margin-bottom: 20px; }
    .sub a { color: var(--blue); text-decoration: none; }
    .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
    .card { background: var(--panel); border-radius: 12px; padding: 16px 18px; }
    .label { color: var(--muted); font-size: 13px; margin-bottom: 6px; }
    .count { font-size: 40px; font-weight: 700; line-height: 1.1; }
    .up { color: var(--green); }
    .down { color: var(--red); }
    .bars { display: flex; gap: 3px; align-items: flex-end; height: 56px; margin-bottom: 8px; }
    .bar { flex: 1; min-width: 2px; height: 100%; border-radius: 2px; background: var(--green); }
    .bar.off { background: var(--red); }
    .legend { color: var(--muted); font-size: 12px; display: flex; justify-content: space-between; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th { text-align: left; color: var(--muted); font-weight: 500; padding: 8px 10px; }
    td { padding: 8px 10px; border-top: 1px solid #334155; }
    .mono { font-family: ui-monospace, Menlo, monospace; font-size: 13px; }
    @media (max-width: 800px) {
      .cards { grid-template-columns: 1fr; }
      .wrap { padding: 16px 14px 24px; }
      h1 { font-size: 22px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>eLibrary Sansad Status</h1>
    <div class="sub"><a id="siteLink" href="#" target="_blank" rel="noreferrer"></a> · checked every 5 minutes by GitHub Actions</div>
    <div class="cards">
      <div class="card">
        <div class="label">Current status</div>
        <div class="count" id="current">—</div>
      </div>
      <div class="card">
        <div class="label">Uptime (last <span id="window">0</span> checks)</div>
        <div class="count" id="uptime">—</div>
      </div>
      <div class="card">
        <div class="label">Last checked</div>
        <div id="checked">—</div>
        <div class="label mono" id="detail" style="margin-top:6px"></div>
      </div>
    </div>
    <div class="label">Recent checks</div>
    <div class="bars" id="bars"></div>
    <div class="legend"><span id="oldest"></span><span id="newest"></span></div>
    <div class="label" style="margin:22px 0 4px">Status changes</div>
    <table>
      <thead><tr><th>When</th><th>Status</th><th>Detail</th></tr></thead>
      <tbody id="events"><tr><td colspan="3">No changes recorded yet.</td></tr></tbody>
    </table>
  </div>
  <script id="data" type="application/json">__DATA__</script>
  <script>
    const data = JSON.parse(document.getElementById('data').textContent);
    const history = data.history || [];
    const fmt = iso => new Date(iso).toLocaleString();

    const link = document.getElementById('siteLink');
    link.href = data.site_url;
    link.textContent = (data.site_url || '').replace(/^https?:\\/\\//, '');

    const current = document.getElementById('current');
    if (data.up === true) { current.textContent = 'UP'; current.className = 'count up'; }
    else if (data.up === false) { current.textContent = 'DOWN'; current.className = 'count down'; }

    document.getElementById('window').textContent = history.length;
    if (history.length) {
      const ups = history.filter(h => h.up).length;
      document.getElementById('uptime').textContent = (ups / history.length * 100).toFixed(1) + '%';
      document.getElementById('oldest').textContent = fmt(history[0].at);
      document.getElementById('newest').textContent = fmt(history[history.length - 1].at);
    }
    if (data.checked_at) document.getElementById('checked').textContent = fmt(data.checked_at);
    document.getElementById('detail').textContent = data.detail || '';

    const bars = document.getElementById('bars');
    history.forEach(h => {
      const bar = document.createElement('div');
      bar.className = 'bar' + (h.up ? '' : ' off');
      bar.title = fmt(h.at) + ' — ' + (h.up ? 'UP' : 'DOWN') + ' (' + h.detail + ')';
      bars.appendChild(bar);
    });

    const changes = history.filter((h, i) => i > 0 && h.up !== history[i - 1].up).reverse();
    if (changes.length) {
      document.getElementById('events').innerHTML = changes.map(h =>
        '<tr><td>' + fmt(h.at) + '</td><td class="' + (h.up ? 'up' : 'down') + '">' +
        (h.up ? 'Recovered' : 'Went down') + '</td><td class="mono">' + h.detail + '</td></tr>'
      ).join('');
    }
  </script>
</body>
</html>
"""


def load_history() -> list[dict]:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def main() -> int:
    site_url = os.environ.get("SITE", "")
    up = os.environ.get("UP", "") == "true"
    detail = os.environ.get("DETAIL", "")
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    history = load_history()
    history.append({"at": checked_at, "up": up, "detail": detail})
    history = history[-MAX_HISTORY:]

    status = {
        "site_url": site_url,
        "up": up,
        "detail": detail,
        "checked_at": checked_at,
        "checks": len(history),
        "history": history,
    }

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    STATUS_PATH.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    INDEX_PATH.write_text(
        TEMPLATE.replace("__DATA__", json.dumps(status).replace("</", "<\\/")),
        encoding="utf-8",
    )
    print(f"status page updated: {'UP' if up else 'DOWN'} ({detail}), {len(history)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
