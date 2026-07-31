#!/usr/bin/env python3
"""Sum PagerDuty on-call hours per engineer, across one or more schedules.

Standalone, stdlib-only (no pip install needed). Requires PD_AUTH_TOKEN in
the environment; set PD_API_BASE_URL too if your account is EU-hosted
(https://api.eu.pagerduty.com).

Usage:
    python3 oncall_hours.py --since 2026-07-01 --until 2026-08-01
    python3 oncall_hours.py -s PSCHED1,PSCHED2 --since 2026-07-01 --until 2026-08-01
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

API_BASE_URL = os.environ.get("PD_API_BASE_URL", "https://api.pagerduty.com").rstrip("/")


def api_get(path: str, token: str, params: dict | None = None) -> dict:
    url = f"{API_BASE_URL}{path}"
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


def list_schedule_ids(token: str) -> list[str]:
    schedule_ids = []
    offset = 0
    while True:
        payload = api_get("/schedules", token, {"limit": 100, "offset": offset})
        schedule_ids.extend(s["id"] for s in payload["schedules"])
        if not payload.get("more"):
            break
        offset += payload.get("limit", 100)
    return schedule_ids


def get_rendered_entries(schedule_id: str, since: str, until: str, token: str) -> list[dict]:
    payload = api_get(f"/schedules/{schedule_id}", token, {"since": since, "until": until})
    final_schedule = payload["schedule"].get("final_schedule") or {}
    return final_schedule.get("rendered_schedule_entries", [])


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-s", "--schedules", default="all", help="comma-separated schedule IDs, or 'all' (default)")
    parser.add_argument("--since", help="range start, e.g. 2026-07-01 (default: 1st of last calendar month)")
    parser.add_argument("--until", help="range end, e.g. 2026-08-01 (default: 1st of this calendar month)")
    args = parser.parse_args()

    token = os.environ.get("PD_AUTH_TOKEN")
    if not token:
        sys.exit("PD_AUTH_TOKEN environment variable is not set")

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
        schedule_ids = list_schedule_ids(token)
    else:
        schedule_ids = [s.strip() for s in args.schedules.split(",")]

    totals: dict[str, float] = {}
    for schedule_id in schedule_ids:
        for entry in get_rendered_entries(schedule_id, since, until, token):
            start = dt.datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
            end = dt.datetime.fromisoformat(entry["end"].replace("Z", "+00:00"))
            hours = (end - start).total_seconds() / 3600
            name = entry["user"]["summary"]
            totals[name] = totals.get(name, 0.0) + hours

    print(f"On-call hours from {since} to {until}", file=sys.stderr)
    for name in sorted(totals):
        print(f"{name}\t{totals[name]:.2f}")


if __name__ == "__main__":
    main()
