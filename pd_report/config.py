from __future__ import annotations

import datetime as dt
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".pd-report-config.yml"

# Fallback for timezone abbreviations that aren't valid IANA zone names
# (Go's time.RFC822 format encodes a zone abbreviation, e.g. "UTC", "MST").
_FIXED_OFFSET_ZONES = {
    "UTC": 0,
    "GMT": 0,
    "BST": 1,
    "CET": 1,
    "CEST": 2,
    "EST": -5,
    "EDT": -4,
    "CST": -6,
    "CDT": -5,
    "MST": -7,
    "MDT": -6,
    "PST": -8,
    "PDT": -7,
}


class ConfigError(RuntimeError):
    pass


def parse_rfc822(value: str) -> dt.datetime:
    """Parse Go's time.RFC822 layout: '02 Jan 06 15:04 MST'."""
    parts = value.strip().rsplit(" ", 1)
    if len(parts) != 2:
        raise ConfigError(f"cannot parse time '{value}' (expected RFC822 format, e.g. '01 Jan 20 00:00 UTC')")
    naive_part, zone_name = parts
    try:
        naive = dt.datetime.strptime(naive_part, "%d %b %y %H:%M")
    except ValueError as exc:
        raise ConfigError(f"cannot parse time '{value}': {exc}") from exc

    try:
        tzinfo = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        offset_hours = _FIXED_OFFSET_ZONES.get(zone_name.upper())
        if offset_hours is None:
            raise ConfigError(f"unknown timezone '{zone_name}' in '{value}'")
        tzinfo = dt.timezone(dt.timedelta(hours=offset_hours))

    return naive.replace(tzinfo=tzinfo)


@dataclass
class RotationUser:
    user_id: str
    name: str = ""
    holidays_calendar: str = ""


@dataclass
class RotationPriceDay:
    day: str
    price: int


@dataclass
class RotationExcludedHoursDay:
    day: str
    excluded_starts_at: int
    excluded_ends_at: int


@dataclass
class RotationInfo:
    daily_rotation_starts_at: int = 8
    check_rotation_change_every: int = 30


@dataclass
class ReportTimeRange:
    start: str = ""
    end: str = ""


@dataclass
class ScheduleTimeRange:
    id: str
    start: str
    end: str


@dataclass
class RotationPrices:
    currency: str = "£"
    days_info: list[RotationPriceDay] = field(default_factory=list)


@dataclass
class PricesInfo:
    week_day_hourly_price: float
    hours_week_day: int
    weekend_day_hourly_price: float
    hours_weekend_day: int
    bh_day_hourly_price: float
    hours_bh_day: int


@dataclass
class Configuration:
    pd_auth_token: str = ""
    default_holiday_calendar: str = ""
    default_user_timezone: str = ""
    report_time_range: ReportTimeRange = field(default_factory=ReportTimeRange)
    rotation_info: RotationInfo = field(default_factory=RotationInfo)
    rotation_excluded_hours: list[RotationExcludedHoursDay] = field(default_factory=list)
    rotation_prices: RotationPrices = field(default_factory=RotationPrices)
    rotation_users: list[RotationUser] = field(default_factory=list)
    schedule_time_range_overrides: list[ScheduleTimeRange] = field(default_factory=list)
    schedules_to_ignore: list[str] = field(default_factory=list)

    _rotation_users_cache: dict[str, RotationUser] = field(default_factory=dict, repr=False)
    _rotation_prices_cache: dict[str, int] = field(default_factory=dict, repr=False)
    _excluded_by_day_cache: dict[str, RotationExcludedHoursDay | None] = field(default_factory=dict, repr=False)

    def find_price_by_day(self, day_type: str) -> int:
        if day_type in self._rotation_prices_cache:
            return self._rotation_prices_cache[day_type]

        for entry in self.rotation_prices.days_info:
            if entry.day == day_type:
                self._rotation_prices_cache[day_type] = entry.price
                return entry.price

        raise ConfigError(f"day type {day_type} not found")

    def find_rotation_excluded_hours_by_day(self, day_type: str) -> RotationExcludedHoursDay | None:
        if day_type in self._excluded_by_day_cache:
            return self._excluded_by_day_cache[day_type]

        for entry in self.rotation_excluded_hours:
            if entry.day == day_type:
                self._excluded_by_day_cache[day_type] = entry
                return entry

        self._excluded_by_day_cache[day_type] = None
        return None

    def find_rotation_user_info_by_id(self, user_id: str) -> RotationUser:
        if user_id in self._rotation_users_cache:
            return self._rotation_users_cache[user_id]

        for entry in self.rotation_users:
            if entry.user_id == user_id:
                self._rotation_users_cache[user_id] = entry
                return entry

        if not self.default_holiday_calendar:
            raise ConfigError(f"user id {user_id} not found")

        rotation_user = RotationUser(user_id=user_id, holidays_calendar=self.default_holiday_calendar)
        self._rotation_users_cache[user_id] = rotation_user
        print(f"defaulting user with id: {user_id} to {self.default_holiday_calendar}", file=sys.stderr)
        return rotation_user

    def is_schedule_id_to_ignore(self, schedule_id: str) -> bool:
        return schedule_id in self.schedules_to_ignore

    def get_prices_info(self) -> PricesInfo:
        week_day_price = self.find_price_by_day("weekday")
        excluded = self.find_rotation_excluded_hours_by_day("weekday")
        excluded_week_day_hours = (excluded.excluded_ends_at - excluded.excluded_starts_at) if excluded else 0
        week_day_working_hours = 24 - excluded_week_day_hours

        weekend_day_price = self.find_price_by_day("weekend")
        excluded = self.find_rotation_excluded_hours_by_day("weekend")
        excluded_weekend_day_hours = (excluded.excluded_ends_at - excluded.excluded_starts_at) if excluded else 0
        weekend_day_working_hours = 24 - excluded_weekend_day_hours

        bh_day_price = self.find_price_by_day("bankholiday")
        excluded = self.find_rotation_excluded_hours_by_day("bankholiday")
        excluded_bh_day_hours = (excluded.excluded_ends_at - excluded.excluded_starts_at) if excluded else 0
        bh_working_hours = 24 - excluded_bh_day_hours

        return PricesInfo(
            week_day_hourly_price=week_day_price / week_day_working_hours,
            hours_week_day=week_day_working_hours,
            weekend_day_hourly_price=weekend_day_price / weekend_day_working_hours,
            hours_weekend_day=weekend_day_working_hours,
            bh_day_hourly_price=bh_day_price / bh_working_hours,
            hours_bh_day=bh_working_hours,
        )


def load_config(config_path: str | None) -> Configuration:
    if config_path:
        path = Path(config_path)
    else:
        path = DEFAULT_CONFIG_PATH

    print(f"Reading configuration file: {path}", file=sys.stderr)
    try:
        raw_text = path.read_text()
    except OSError as exc:
        raise ConfigError(f"Can't read config: {exc}") from exc

    raw = yaml.safe_load(raw_text) or {}

    config = Configuration()
    config.default_holiday_calendar = raw.get("defaultHolidayCalendar", "")
    config.default_user_timezone = raw.get("defaultUserTimezone", "")

    rtr = raw.get("reportTimeRange") or {}
    config.report_time_range = ReportTimeRange(start=rtr.get("start", ""), end=rtr.get("end", ""))

    ri = raw.get("rotationInfo") or {}
    config.rotation_info = RotationInfo(
        daily_rotation_starts_at=int(ri.get("dailyRotationStartsAt", 8)),
        check_rotation_change_every=int(ri.get("checkRotationChangeEvery", 30)),
    )

    config.rotation_excluded_hours = [
        RotationExcludedHoursDay(
            day=entry["day"],
            excluded_starts_at=int(entry["excludedStartsAt"]),
            excluded_ends_at=int(entry["excludedEndsAt"]),
        )
        for entry in raw.get("rotationExcludedHours") or []
    ]

    rp = raw.get("rotationPrices") or {}
    config.rotation_prices = RotationPrices(
        currency=rp.get("currency", "£"),
        days_info=[
            RotationPriceDay(day=entry["day"], price=int(entry["price"]))
            for entry in rp.get("daysInfo") or []
        ],
    )

    config.rotation_users = [
        RotationUser(
            user_id=entry["userId"],
            name=entry.get("name", ""),
            holidays_calendar=entry.get("holidaysCalendar", ""),
        )
        for entry in raw.get("rotationUsers") or []
    ]

    config.schedule_time_range_overrides = [
        ScheduleTimeRange(id=entry["id"], start=entry["start"], end=entry["end"])
        for entry in raw.get("scheduleTimeRangeOverrides") or []
    ]

    config.schedules_to_ignore = list(raw.get("schedulesToIgnore") or [])

    config.pd_auth_token = os.environ.get("PD_AUTH_TOKEN", "")
    if not config.pd_auth_token:
        raise ConfigError("PD_AUTH_TOKEN environment variable is not set")

    return config
