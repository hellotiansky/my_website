#!/usr/bin/env python3
"""Daily, low-volume availability checks for the configured websites."""

import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "sites.json"
TIMEOUT = 20


def check(url: str) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "my-website-availability-monitor/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return url, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        # An HTTP response (including 4xx/5xx) confirms the host responded.
        return url, f"HTTP {exc.code}"
    except Exception as exc:
        return url, f"ERROR: {type(exc).__name__}: {exc}"


def main() -> int:
    with CONFIG.open(encoding="utf-8") as file:
        urls = json.load(file).get("urls", [])

    if not urls:
        print("No URLs configured in sites.json")
        return 1

    failures = 0
    print(f"Checking {len(urls)} configured URL(s), one request per URL.")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(check, url) for url in urls]
        for future in as_completed(futures):
            url, result = future.result()
            print(f"{result:35} {url}")
            if result.startswith("ERROR:"):
                failures += 1

    print(f"\nSummary: {len(urls) - failures}/{len(urls)} host(s) responded.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
