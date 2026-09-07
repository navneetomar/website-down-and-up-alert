#!/usr/bin/env python3
"""Shared start/stop helpers for the eLibrary Sansad watcher."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

DIR = Path(__file__).resolve().parent
LOG_PATH = DIR / "alert.log"
STATE_PATH = DIR / "state.json"
PROJECT_PLIST = DIR / "com.alert.elibrary.plist"
USER_PLIST = Path.home() / "Library/LaunchAgents/com.alert.elibrary.plist"
LABEL = "com.alert.elibrary"
SCRIPT = DIR / "check_uptime.py"
LOOP_INTERVAL = 15

_loop_stop = threading.Event()
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def is_ios() -> bool:
    if sys.platform == "ios":
        return True
    home = os.environ.get("HOME", "")
    if "Containers/Data/Application" in home or "/var/mobile/" in home:
        return True
    return bool(os.environ.get("APPDIR"))


def uses_launchd() -> bool:
    return (
        not is_ios()
        and shutil.which("launchctl") is not None
        and PROJECT_PLIST.exists()
        and sys.platform == "darwin"
    )


def uid() -> int:
    return os.getuid()


def launch_label() -> str:
    return f"gui/{uid()}/{LABEL}"


def _loop_worker() -> None:
    from check_uptime import main as check_site

    while not _loop_stop.is_set():
        try:
            check_site()
        except Exception:
            pass
        _loop_stop.wait(LOOP_INTERVAL)


def _local_running() -> bool:
    thread = _loop_thread
    return thread is not None and thread.is_alive()


def is_running() -> bool:
    if _local_running():
        return True
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"{SCRIPT} --loop"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except OSError:
        return False


def start_watcher() -> str:
    if uses_launchd():
        USER_PLIST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_PLIST, USER_PLIST)
        domain = f"gui/{uid()}"
        subprocess.run(["launchctl", "bootout", launch_label()], capture_output=True)
        result = subprocess.run(
            ["launchctl", "bootstrap", domain, str(USER_PLIST)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and "already loaded" not in (result.stderr or "").lower():
            return result.stderr.strip() or result.stdout.strip() or "Start failed"
        return ""

    global _loop_thread
    with _loop_lock:
        if _local_running():
            return ""
        _loop_stop.clear()
        _loop_thread = threading.Thread(
            target=_loop_worker, name="elibrary-watch", daemon=True
        )
        _loop_thread.start()
    return ""


def stop_watcher() -> str:
    if uses_launchd():
        result = subprocess.run(
            ["launchctl", "bootout", launch_label()],
            capture_output=True,
            text=True,
        )
        subprocess.run(["pkill", "-f", f"{SCRIPT} --loop"], capture_output=True)
        err = (result.stderr or "").strip()
        if result.returncode != 0 and "No such process" not in err and "Could not find" not in err:
            return err or "Stop failed"
        return ""

    global _loop_thread
    with _loop_lock:
        _loop_stop.set()
        thread = _loop_thread
        _loop_thread = None
    if thread is not None:
        thread.join(timeout=2)
    return ""


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_logs(max_lines: int = 400) -> str:
    if not LOG_PATH.exists():
        return ""
    lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])
