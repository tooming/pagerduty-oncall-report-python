#!/usr/bin/env python3
"""Sum PagerDuty on-call hours per engineer, across one or more schedules.

Reports total hours per engineer, plus how many of those hours fell on an
Estonian public holiday.

Standalone, stdlib-only (no pip install needed). Requires PD_AUTH_TOKEN in
the environment.

Bank-holiday hours are computed against each schedule's own timezone (not
per-user), since that's what the API gives us without extra lookups. Fine
as long as everyone on the schedule is roughly in that timezone.

Usage:
    python3 oncall_hours.py --since 2026-07-01 --until 2026-08-01
    python3 oncall_hours.py -s PSCHED1,PSCHED2 --since 2026-07-01 --until 2026-08-01
    python3 oncall_hours.py --api-base-url https://api.eu.pagerduty.com
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

DEFAULT_API_BASE_URL = "https://api.pagerduty.com"

# Estonian public holidays, sourced from https://publicholidays.ee — same
# dates as pd_report/assets/calendars/holidays_calendar.ee.*.yml in this
# repo's full package. Add a year here (and to the .yml file, to keep them
# in sync) when it's missing; a date outside this range is a hard error
# rather than being silently skipped.
ESTONIAN_PUBLIC_HOLIDAYS: dict[int, set[str]] = {
    2023: {
        "2023-01-01", "2023-02-24", "2023-04-07", "2023-04-09", "2023-05-01",
        "2023-05-28", "2023-06-23", "2023-06-24", "2023-08-20", "2023-12-24",
        "2023-12-25", "2023-12-26",
    },
    2024: {
        "2024-01-01", "2024-02-24", "2024-03-29", "2024-03-31", "2024-05-01",
        "2024-05-19", "2024-06-23", "2024-06-24", "2024-08-20", "2024-12-24",
        "2024-12-25", "2024-12-26",
    },
    2025: {
        "2025-01-01", "2025-02-24", "2025-04-18", "2025-04-20", "2025-05-01",
        "2025-06-08", "2025-06-23", "2025-06-24", "2025-08-20", "2025-12-24",
        "2025-12-25", "2025-12-26",
    },
    2026: {
        "2026-01-01", "2026-02-24", "2026-04-03", "2026-04-05", "2026-05-01",
        "2026-05-24", "2026-06-23", "2026-06-24", "2026-08-20", "2026-12-24",
        "2026-12-25", "2026-12-26",
    },
}


def is_bank_holiday(day: dt.date) -> bool:
    if day.year not in ESTONIAN_PUBLIC_HOLIDAYS:
        sys.exit(
            f"no Estonian public holiday data for {day.year} in this script "
            f"(have {sorted(ESTONIAN_PUBLIC_HOLIDAYS)}) - add it to ESTONIAN_PUBLIC_HOLIDAYS"
        )
    return day.isoformat() in ESTONIAN_PUBLIC_HOLIDAYS[day.year]


def api_get(base_url: str, path: str, token: str, params: dict | None = None) -> dict:
    url = f"{base_url}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Token token={token}",
            "Accept": "application/vnd.pagerduty+json;version=2",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        sys.exit(f"PagerDuty API request to {path} failed: {exc.code} {body}")


def list_schedule_ids(base_url: str, token: str) -> list[str]:
    schedule_ids = []
    offset = 0
    while True:
        payload = api_get(base_url, "/schedules", token, {"limit": 100, "offset": offset})
        schedule_ids.extend(s["id"] for s in payload["schedules"])
        if not payload.get("more"):
            break
        offset += payload.get("limit", 100)
    return schedule_ids


def get_schedule_detail(base_url: str, schedule_id: str, since: str, until: str, token: str) -> tuple[str, list[dict]]:
    payload = api_get(base_url, f"/schedules/{schedule_id}", token, {"since": since, "until": until})
    schedule = payload["schedule"]
    final_schedule = schedule.get("final_schedule") or {}
    return schedule.get("time_zone", "UTC"), final_schedule.get("rendered_schedule_entries", [])


def parse_timestamp(value: str) -> dt.datetime:
    # Accept a bare date ("2026-07-01") or a full RFC3339 timestamp.
    if len(value) == 10:
        return dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def default_last_month() -> tuple[dt.datetime, dt.datetime]:
    today = dt.datetime.now(dt.timezone.utc).date()
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month
    last_month_start = (first_of_this_month - dt.timedelta(days=1)).replace(day=1)
    return (
        dt.datetime.combine(last_month_start, dt.time.min, tzinfo=dt.timezone.utc),
        dt.datetime.combine(last_month_end, dt.time.min, tzinfo=dt.timezone.utc),
    )


def bank_holiday_overlap_hours(start: dt.datetime, end: dt.datetime) -> float:
    """Hours of [start, end) that fall on an Estonian public holiday, in start/end's own tzinfo."""
    total = 0.0
    day = start.date()
    while day <= end.date():
        if is_bank_holiday(day):
            day_start = dt.datetime.combine(day, dt.time.min, tzinfo=start.tzinfo)
            day_end = day_start + dt.timedelta(days=1)
            overlap_start = max(start, day_start)
            overlap_end = min(end, day_end)
            if overlap_end > overlap_start:
                total += (overlap_end - overlap_start).total_seconds() / 3600
        day += dt.timedelta(days=1)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-s", "--schedules", default="all", help="comma-separated schedule IDs, or 'all' (default)")
    parser.add_argument("--since", help="range start, e.g. 2026-07-01 (default: 1st of last calendar month)")
    parser.add_argument("--until", help="range end, e.g. 2026-08-01 (default: 1st of this calendar month)")
    parser.add_argument(
        "--api-base-url",
        default=os.environ.get("PD_API_BASE_URL", DEFAULT_API_BASE_URL),
        help=f"PagerDuty API base URL (default: {DEFAULT_API_BASE_URL}; env PD_API_BASE_URL also works; "
        "use https://api.eu.pagerduty.com for EU-hosted accounts)",
    )
    args = parser.parse_args()

    token = os.environ.get("PD_AUTH_TOKEN")
    if not token:
        sys.exit("PD_AUTH_TOKEN environment variable is not set")

    base_url = args.api_base_url.rstrip("/")

    if args.since and args.until:
        since_dt = parse_timestamp(args.since)
        until_dt = parse_timestamp(args.until)
    elif args.since or args.until:
        sys.exit("--since and --until must be given together")
    else:
        since_dt, until_dt = default_last_month()

    since = since_dt.strftime("%Y-%m-%dT%H:%M:%S")
    until = until_dt.strftime("%Y-%m-%dT%H:%M:%S")

    if args.schedules == "all":
        schedule_ids = list_schedule_ids(base_url, token)
    else:
        schedule_ids = [s.strip() for s in args.schedules.split(",")]

    totals: dict[str, float] = {}
    bank_holiday_totals: dict[str, float] = {}
    for schedule_id in schedule_ids:
        time_zone, entries = get_schedule_detail(base_url, schedule_id, since, until, token)
        location = ZoneInfo(time_zone)
        for entry in entries:
            start = dt.datetime.fromisoformat(entry["start"].replace("Z", "+00:00")).astimezone(location)
            end = dt.datetime.fromisoformat(entry["end"].replace("Z", "+00:00")).astimezone(location)
            name = entry["user"]["summary"]

            hours = (end - start).total_seconds() / 3600
            totals[name] = totals.get(name, 0.0) + hours

            bh_hours = bank_holiday_overlap_hours(start, end)
            bank_holiday_totals[name] = bank_holiday_totals.get(name, 0.0) + bh_hours

    print(f"On-call hours from {since} to {until} ({base_url})", file=sys.stderr)
    print(f"{'Name':<25}{'Total Hours':>15}{'Bank Holiday Hours':>22}")
    for name in sorted(totals):
        print(f"{name:<25}{totals[name]:>15.2f}{bank_holiday_totals.get(name, 0.0):>22.2f}")


if __name__ == "__main__":
    main()
