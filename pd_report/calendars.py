from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass, field
from importlib import resources

import yaml

_DATE_FORMAT = "%d/%m/%Y"


@dataclass
class BankHoliday:
    name: str
    date: dt.date


@dataclass
class BHCalendar:
    days: dict[str, BankHoliday] = field(default_factory=dict)

    def is_date_bank_holiday(self, date: dt.date) -> bool:
        return date.strftime(_DATE_FORMAT) in self.days

    @staticmethod
    def is_weekend(date: dt.date) -> bool:
        return date.weekday() in (5, 6)  # Saturday, Sunday


# Populated by load_calendars(); keyed as "<calendar-name>-<year>".
bank_holidays_calendars: dict[str, BHCalendar] = {}

_loaded_years: set[int] = set()


def load_calendars(year: int) -> None:
    """Load bank holiday calendars for the given year, merging into the
    module-level cache so calendars for previously loaded years are kept
    around (reports can span multiple calendar years)."""
    if year in _loaded_years:
        return

    print(f"Loading calendars for year: {year}", file=sys.stderr)

    calendars_dir = resources.files("pd_report.assets") / "calendars"
    found_any = False
    for entry in calendars_dir.iterdir():
        if not entry.name.endswith(".yml"):
            continue

        parts = entry.name.split(".")
        # holidays_calendar.<name>.<year>.yml
        if len(parts) != 4:
            continue
        _, name, year_str, _ext = parts
        try:
            file_year = int(year_str)
        except ValueError:
            continue
        if file_year != year:
            continue

        raw = yaml.safe_load(entry.read_text(encoding="utf-8")) or []
        days: dict[str, BankHoliday] = {}
        for item in raw:
            date = dt.datetime.strptime(item["date"], _DATE_FORMAT).date()
            days[date.strftime(_DATE_FORMAT)] = BankHoliday(name=item.get("title", ""), date=date)

        key = f"{name}-{file_year}"
        bank_holidays_calendars[key] = BHCalendar(days=days)
        found_any = True
        print(f"Loaded calendar: '{key}'", file=sys.stderr)

    _loaded_years.add(year)
    if not found_any:
        print(f"warning: no calendars found for year {year}", file=sys.stderr)
