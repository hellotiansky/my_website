#!/usr/bin/env python3
"""Check configured websites three times daily and append CSV rows to the daily log."""

import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "sites.json"
LOG = ROOT / "logs" / "daily-access-log.csv"
TIMEOUT = 20

# First daily check starts at 02:17 UTC (11:17 Japan time) on this date.
# The daily start moves forward by 15 minutes; checks repeat every 8 hours.
# The start time wraps naturally every 96 days.
SCHEDULE_ANCHOR = datetime(2026, 11, 23, 2, 17, tzinfo=timezone.utc)
CHECKS_PER_DAY = 3
CHECK_INTERVAL_HOURS = 8


def is_scheduled_check_due(now: datetime) -> bool:
    days_elapsed = (now.date() - SCHEDULE_ANCHOR.date()).days
    if days_elapsed < 0:
        return False
    daily_start_minute = (
        SCHEDULE_ANCHOR.hour * 60 + SCHEDULE_ANCHOR.minute + 15 * days_elapsed
    ) % (24 * 60)
    current_minute = now.hour * 60 + now.minute

    # Three checks per day, spaced eight hours apart from the rotating start.
    # Cron fires every 15 minutes; allow one slot for queue delay.
    for check_index in range(CHECKS_PER_DAY):
        target_minute = (
            daily_start_minute + check_index * CHECK_INTERVAL_HOURS * 60
        ) % (24 * 60)
        if target_minute <= current_minute < target_minute + 15:
            return True
    return False


def check(url: str) -> dict:
    request = Request(
        url,
        headers={"User-Agent": "my-website-availability-monitor/1.0"},
        method="GET",
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            status = response.status
        return {
            "url": url, "outcome": "SUCCESS", "http_status": status,
            "duration_seconds": round(time.monotonic() - started, 3), "error": "",
        }
    except HTTPError as exc:
        # Any HTTP response proves the web server was reached; retain its status.
        return {
            "url": url, "outcome": "SUCCESS", "http_status": exc.code,
            "duration_seconds": round(time.monotonic() - started, 3), "error": "",
        }
    except Exception as exc:
        return {
            "url": url, "outcome": "FAILURE", "http_status": "",
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


def append_log(results: list[dict], checked_at: datetime) -> tuple[int, int]:
    success_count = sum(item["outcome"] == "SUCCESS" for item in results)
    failure_count = len(results) - success_count
    LOG.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "checked_at_utc", "date_utc", "run_id", "url", "outcome",
        "http_status", "duration_seconds", "error",
        "run_success_count", "run_failure_count", "run_total",
    ]
    run_id = os.environ.get("GITHUB_RUN_ID", checked_at.strftime("%Y%m%dT%H%M%SZ"))
    needs_header = not LOG.exists() or LOG.stat().st_size == 0
    with LOG.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if needs_header:
            writer.writeheader()
        for item in results:
            writer.writerow({
                "checked_at_utc": checked_at.isoformat(timespec="seconds"),
                "date_utc": checked_at.date().isoformat(),
                "run_id": run_id,
                **item,
                "run_success_count": success_count,
                "run_failure_count": failure_count,
                "run_total": len(results),
            })
    return success_count, failure_count


def main() -> int:
    if os.environ.get("SCHEDULED_RUN", "").lower() == "true":
        now = datetime.now(timezone.utc)
        if not is_scheduled_check_due(now):
            print("Not today's rotating check time; skipping this 15-minute scheduler tick.")
            return 0

    with CONFIG.open(encoding="utf-8") as file:
        urls = json.load(file).get("urls", [])
    if not urls:
        print("No URLs configured in sites.json", file=sys.stderr)
        return 1

    print(f"Checking {len(urls)} configured URL(s), one request per URL.")
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(check, url) for url in urls]
        for future in as_completed(futures):
            item = future.result()
            results.append(item)
            status = f"HTTP {item['http_status']}" if item["http_status"] else item["error"]
            print(f"[{item['outcome']}] {status:32} {item['url']}")

    checked_at = datetime.now(timezone.utc)
    success_count, failure_count = append_log(results, checked_at)
    print(f"\nSummary: {success_count} successful, {failure_count} failed, {len(results)} total.")
    print(f"Appended {len(results)} row(s) to {LOG.relative_to(ROOT)}")
    return 1 if failure_count else 0


if __name__ == "__main__":
    sys.exit(main())
