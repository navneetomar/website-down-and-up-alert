#!/usr/bin/env python3
"""Web UI for eLibrary Sansad uptime alerts on http://localhost:3000"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from watcher import is_running, load_state, read_logs, start_watcher, stop_watcher

PORT = 3000

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <title>eLibrary Sansad Alert</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #1e293b;
      --card: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --green: #4ade80;
      --red: #f87171;
      --amber: #fbbf24;
      --blue: #38bdf8;
      --changed: #fb923c;
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
    .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
    .card { background: var(--panel); border-radius: 12px; padding: 16px 18px; }
    .label { color: var(--muted); font-size: 13px; margin-bottom: 6px; }
    .count { font-size: 40px; font-weight: 700; line-height: 1.1; }
    .status { display: flex; align-items: center; gap: 8px; font-size: 16px; }
    .dot { width: 12px; height: 12px; border-radius: 50%; background: var(--muted); }
    .dot.on { background: var(--green); box-shadow: 0 0 10px var(--green); }
    .dot.off { background: var(--red); }
    .up { color: var(--green); }
    .down { color: var(--red); }
    .actions { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
    button {
      border: 0; border-radius: 8px; padding: 10px 22px; font-size: 15px;
      font-weight: 600; cursor: pointer; color: white;
    }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .start { background: #15803d; }
    .stop { background: #b91c1c; }
    .msg { color: var(--amber); font-size: 14px; }
    .logs {
      background: #0b1220; border-radius: 12px; padding: 14px 16px;
      min-height: 360px; max-height: 62vh; overflow: auto;
      font-family: ui-monospace, Menlo, monospace; font-size: 13px; line-height: 1.45;
      white-space: pre-wrap; word-break: break-word;
    }
    .changed { color: var(--changed); }
    .error { color: var(--red); }
    .info { color: var(--blue); }
    .ok { color: var(--muted); }
    @media (max-width: 800px) {
      .cards { grid-template-columns: 1fr; }
      .count { font-size: 32px; }
      .wrap { padding: 16px 14px 24px; }
      h1 { font-size: 22px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>eLibrary Sansad Alert</h1>
    <div class="sub"><a href="https://elibrary.sansad.in" target="_blank" rel="noreferrer">elibrary.sansad.in</a> · check every 15 seconds</div>
    <div class="cards">
      <div class="card">
        <div class="label">Watcher</div>
        <div class="status"><span id="dot" class="dot"></span><span id="status">Checking…</span></div>
      </div>
      <div class="card">
        <div class="label">Website</div>
        <div class="count" id="siteStatus">—</div>
      </div>
      <div class="card">
        <div class="label">Last event</div>
        <div id="siteDetail">—</div>
      </div>
    </div>
    <div class="actions">
      <button class="start" id="startBtn" onclick="control('start')">Start</button>
      <button class="stop" id="stopBtn" onclick="control('stop')">Stop</button>
      <span class="msg" id="msg"></span>
    </div>
    <div class="label" style="margin-bottom:8px">Live logs</div>
    <div class="logs" id="logs">Loading logs…</div>
  </div>
  <script>
    async function refresh() {
      const res = await fetch('/api/status');
      const data = await res.json();
      const running = data.running;
      document.getElementById('dot').className = 'dot ' + (running ? 'on' : 'off');
      document.getElementById('status').textContent = running ? 'Running' : 'Stopped';
      const siteEl = document.getElementById('siteStatus');
      if (data.site_up === true) {
        siteEl.textContent = 'UP';
        siteEl.className = 'count up';
      } else if (data.site_up === false) {
        siteEl.textContent = 'DOWN';
        siteEl.className = 'count down';
      } else {
        siteEl.textContent = '—';
        siteEl.className = 'count';
      }
      document.getElementById('siteDetail').textContent = data.site_last_event || data.site_error || 'Watching';
      document.getElementById('startBtn').disabled = running;
      document.getElementById('stopBtn').disabled = !running;
      const logs = data.logs || '';
      const box = document.getElementById('logs');
      const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
      box.innerHTML = logs.split('\\n').map(line => {
        let cls = 'ok';
        if (line.includes('SITE RECOVERED')) cls = 'changed';
        else if (line.includes('ERROR') || line.includes('SITE DOWN')) cls = 'error';
        else if (line.toLowerCase().includes('baseline')) cls = 'info';
        return '<span class="' + cls + '">' + escapeHtml(line) + '</span>';
      }).join('\\n');
      if (nearBottom) box.scrollTop = box.scrollHeight;
    }
    function escapeHtml(s) {
      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
    async function control(action) {
      const res = await fetch('/api/' + action, { method: 'POST' });
      const data = await res.json();
      document.getElementById('msg').textContent = data.message || '';
      refresh();
    }
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            state = load_state()
            self._json(
                {
                    "running": is_running(),
                    "site_up": state.get("site_up"),
                    "site_status": state.get("site_status"),
                    "site_error": state.get("site_error"),
                    "site_last_event": state.get("site_last_event"),
                    "site_checked_at": state.get("site_checked_at"),
                    "logs": read_logs(),
                }
            )
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/start":
            err = start_watcher()
            self._json({"ok": not err, "message": err or "Watcher started (every 15 seconds)"})
            return
        if path == "/api/stop":
            err = stop_watcher()
            self._json({"ok": not err, "message": err or "Watcher stopped"})
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"eLibrary Sansad Alert: http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
