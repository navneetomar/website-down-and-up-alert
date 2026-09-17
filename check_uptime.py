#!/usr/bin/env python3
"""Watch https://elibrary.sansad.in and alert when it goes down or comes back."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SITE_URL = "https://elibrary.sansad.in"
TIMEOUT_SEC = 10
# Alert only on the 3rd consecutive down (skip first two 15s checks).
DOWN_ALERT_AFTER = 3
INTERNET_CHECK_URLS = (
    "https://www.google.com/generate_204",
    "https://1.1.1.1",
    "https://www.cloudflare.com/cdn-cgi/trace",
)
INTERNET_CHECK_TIMEOUT = 4

DIR = Path(__file__).resolve().parent
STATE_PATH = DIR / "state.json"
LOG_PATH = DIR / "alert.log"

MAX_LOG_LINES = 30
# Routine UP lines are dropped once the log grows; these stay forever.
KEEP_MARKERS = ("DOWN", "SKIP", "ERROR", "RECOVERED", "baseline")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def is_prunable(line: str) -> bool:
    return not any(marker in line for marker in KEEP_MARKERS)


def prune_lines(lines: list[str]) -> list[str]:
    excess = len(lines) - MAX_LOG_LINES
    if excess <= 0:
        return lines
    drop = min(excess, sum(1 for line in lines if is_prunable(line)))
    kept = []
    for line in lines:
        if drop and is_prunable(line):
            drop -= 1
            continue
        kept.append(line)
    return kept


def trim_log() -> None:
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    kept = prune_lines(lines)
    if len(kept) == len(lines):
        return
    try:
        LOG_PATH.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError:
        pass


def log(message: str) -> None:
    line = f"{now_iso()}  {message}"
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    trim_log()


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    merged = load_state()
    merged.update(state)
    STATE_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


def _applescript_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _is_ios() -> bool:
    if sys.platform == "ios":
        return True
    home = os.environ.get("HOME", "")
    return "Containers/Data/Application" in home or "/var/mobile/" in home or bool(
        os.environ.get("APPDIR")
    )


def notify(title: str, body: str, spoken: str | None = None) -> None:
    title = title.replace("→", "->")
    body = body.replace("→", "->")
    spoken = spoken or "E library sansad alert"
    if _is_ios() or not Path("/usr/bin/osascript").exists():
        if shutil.which("shortcuts"):
            subprocess.run(
                ["shortcuts", "run", "ELibraryAlert"],
                input=f"{title}\n{body}",
                capture_output=True,
                text=True,
            )
        say = shutil.which("say") or "say"
        subprocess.run(
            [say, spoken],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    script = (
        f"display notification {_applescript_quote(body)} "
        f"with title {_applescript_quote(title)} "
        f'sound name "Sosumi"'
    )
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log(f"ERROR notification failed: {result.stderr.strip() or result.stdout.strip()}")
    subprocess.run(
        ["/usr/bin/afplay", "/System/Library/Sounds/Sosumi.aiff"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["/usr/bin/say", "-v", "Samantha", spoken],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def has_internet() -> bool:
    """True if this Mac/phone can reach the public internet (not the target site)."""
    for url in INTERNET_CHECK_URLS:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AlertUptime/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=INTERNET_CHECK_TIMEOUT) as resp:
                resp.read(64)
                code = int(getattr(resp, "status", resp.getcode()))
                if 200 <= code < 500:
                    return True
        except Exception:
            continue
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2000", host],
                capture_output=True,
                timeout=4,
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False


def probe_site() -> tuple[bool, int | None, str | None]:
    req = urllib.request.Request(
        SITE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AlertUptime/1.0",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            status = int(getattr(resp, "status", resp.getcode()))
            resp.read(256)
            if 200 <= status < 400:
                return True, status, None
            return False, status, f"HTTP {status}"
    except urllib.error.HTTPError as exc:
        return False, int(exc.code), f"HTTP {exc.code}"
    except Exception as exc:
        return False, None, str(exc)


def main() -> int:
    if not has_internet():
        save_state({"internet_ok": False, "site_checked_at": now_iso()})
        log("SKIP no local internet — site status unchanged, no alert")
        return 0

    up, status, error = probe_site()
    state = load_state()
    previous = state.get("site_up")
    streak = int(state.get("site_down_streak") or 0)
    already_alerted = bool(state.get("site_down_alerted"))
    payload = {
        "site_url": SITE_URL,
        "site_up": up,
        "site_status": "UP" if up else "DOWN",
        "site_http": status,
        "site_error": error,
        "site_checked_at": now_iso(),
        "site_baseline": False,
        "internet_ok": True,
    }

    if up:
        payload["site_down_streak"] = 0
        payload["site_down_alerted"] = False
        if previous is False:
            if already_alerted:
                message = f"SITE RECOVERED {SITE_URL} (HTTP {status})"
                payload["site_last_event"] = message
                save_state(payload)
                log(message)
                notify(
                    "eLibrary Sansad is back",
                    f"{SITE_URL} is online again (HTTP {status}).",
                    spoken="E library sansad is back online",
                )
            else:
                save_state(payload)
                log(f"UP again {SITE_URL} (HTTP {status}) — brief dip, no alert")
            return 0
        if previous is None:
            save_state({**payload, "site_baseline": True})
            log(f"SITE baseline {SITE_URL} is UP")
            return 0
        save_state(payload)
        log(f"UP {SITE_URL} (HTTP {status})")
        return 0

    streak = 1 if previous is not False else streak + 1
    payload["site_down_streak"] = streak
    payload["site_down_alerted"] = already_alerted
    detail = error or f"HTTP {status}"

    if previous is None:
        save_state({**payload, "site_baseline": True})
        log(
            f"SITE baseline {SITE_URL} is DOWN ({detail}) "
            f"— waiting for confirm {streak}/{DOWN_ALERT_AFTER}"
        )
        return 1

    if streak < DOWN_ALERT_AFTER:
        save_state(payload)
        log(f"DOWN {SITE_URL} ({detail}) — confirm {streak}/{DOWN_ALERT_AFTER}, no alert")
        return 1

    if already_alerted:
        save_state(payload)
        log(f"STILL DOWN {SITE_URL} ({detail})")
        return 1

    message = f"SITE DOWN {SITE_URL} ({detail})"
    payload["site_down_alerted"] = True
    payload["site_last_event"] = message
    save_state(payload)
    log(f"{message} — confirmed {streak}/{DOWN_ALERT_AFTER}")
    notify(
        "eLibrary Sansad is DOWN",
        f"{SITE_URL} is down: {detail}",
        spoken="E library sansad is down",
    )
    return 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        notify(
            "eLibrary test alert",
            "Notifications are working. You will be alerted if the site goes down.",
            spoken="E library sansad test alert",
        )
        print("Test notification sent.")
        sys.exit(0)
    if "--loop" in sys.argv:
        idx = sys.argv.index("--loop")
        interval = 15
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            interval = int(sys.argv[idx + 1])
        while True:
            main()
            time.sleep(interval)
    sys.exit(main())
