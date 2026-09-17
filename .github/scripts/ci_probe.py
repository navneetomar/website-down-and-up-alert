#!/usr/bin/env python3
"""Probe the site from CI and hand the result to the workflow."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from check_uptime import SITE_URL, probe_site

# A single failure is usually a blip, so confirm before alerting.
ATTEMPTS = 3
RETRY_DELAY_SEC = 20


def clean(detail: str) -> str:
    return " ".join(detail.split())[:200]


def main() -> int:
    up = False
    detail = ""
    for attempt in range(1, ATTEMPTS + 1):
        up, status, error = probe_site()
        detail = clean(error or f"HTTP {status}")
        print(f"attempt {attempt}/{ATTEMPTS}: {'UP' if up else 'DOWN'} ({detail})")
        if up:
            break
        if attempt < ATTEMPTS:
            time.sleep(RETRY_DELAY_SEC)

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"up={'true' if up else 'false'}\n")
            fh.write(f"detail={detail}\n")
            fh.write(f"url={SITE_URL}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
