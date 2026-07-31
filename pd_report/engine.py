from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from pd_report import calendars
from pd_report.api import PagerDutyClient, RenderedScheduleEntry, User
from pd_report.config import Configuration, ConfigError, PricesInfo, parse_rfc822
from pd_report.reportgen.types import PrintableData, ScheduleData, ScheduleUser

VALID_OUTPUT_FORMATS = ("console", "pdf", "csv")


class ReportError(RuntimeError):
    pass


@dataclass
class ScheduleSpec:
    id: str
    start_date: dt.datetime
    end_date: dt.datetime


@dataclass
class UserRotaPeriod:
    start: dt.datetime
    end: dt.datetime


@dataclass
class UserRotaInfo:
    id: str
    name: str
    periods: list[UserRotaPeriod] = field(default_factory=list)


def _parse_rfc3339(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


class PagerDutyReportGenerator:
    def __init__(self, client: PagerDutyClient, config: Configuration):
        self.client = client
        self.config = config
        self._cached_users: list[User] | None = None

    # -- shared listing commands --------------------------------------

    def list_users(self) -> list[User]:
        return self.client.list_users()

    def list_teams(self):
        return self.client.list_teams()

    def list_services(self, team_id: str):
        return self.client.list_services(team_id)

    def list_schedules(self):
        return self.client.list_schedules()

    # -- report generation ----------------------------------------------

    def process_arguments(
        self, raw_schedules: list[str], output_format: str, directory: str | None
    ) -> tuple[list[ScheduleSpec], str, str]:
        if output_format not in VALID_OUTPUT_FORMATS:
            print(f"output format {output_format} not supported. Defaulting to 'console'", file=sys.stderr)
            output_format = "console"

        if not directory:
            directory = str(Path.home())

        now = dt.datetime.now(dt.timezone.utc)
        config = self.config
        if config.report_time_range.start:
            default_start_date = parse_rfc822(config.report_time_range.start)
        else:
            first_of_last_month = _add_months(now.replace(day=1), -1)
            default_start_date = dt.datetime(
                first_of_last_month.year, first_of_last_month.month, 1, tzinfo=dt.timezone.utc
            )

        if config.report_time_range.end:
            default_end_date = parse_rfc822(config.report_time_range.end)
        else:
            default_end_date = _add_months(default_start_date, 1)
            default_end_date = default_end_date + dt.timedelta(hours=config.rotation_info.daily_rotation_starts_at)

        start_overrides: dict[str, dt.datetime] = {}
        end_overrides: dict[str, dt.datetime] = {}
        for override in config.schedule_time_range_overrides:
            start_overrides[override.id] = parse_rfc822(override.start)
            end_overrides[override.id] = parse_rfc822(override.end)

        schedules: list[ScheduleSpec] = []
        if len(raw_schedules) == 1 and raw_schedules[0] == "all":
            schedule_list = self.client.list_schedules()
            for schedule in schedule_list:
                if config.is_schedule_id_to_ignore(schedule.id):
                    print(f"Ignoring schedule '{schedule.id}'", file=sys.stderr)
                    continue

                this_start_date = start_overrides.get(schedule.id, default_start_date)

                is_overridden = schedule.id in end_overrides
                this_end_date = end_overrides.get(schedule.id, default_end_date)

                # Ignore this schedule if it's overridden and the dates are not in our report range
                if not is_overridden or not default_start_date > this_end_date:
                    schedules.append(ScheduleSpec(id=schedule.id, start_date=this_start_date, end_date=this_end_date))

                print(
                    f"[{schedule.id}] defaultStartDate: {this_start_date}, defaultEndDate: {this_end_date}",
                    file=sys.stderr,
                )
        else:
            for schedule_id in raw_schedules:
                if config.is_schedule_id_to_ignore(schedule_id):
                    raise ReportError("Configuration explicitly ignores schedule passed as parameter - check your config.")

                this_start_date = start_overrides.get(schedule_id, default_start_date)
                this_end_date = end_overrides.get(schedule_id, default_end_date)
                schedules.append(ScheduleSpec(id=schedule_id, start_date=this_start_date, end_date=this_end_date))
                print(
                    f"[{schedule_id}] defaultStartDate: {this_start_date}, defaultEndDate: {this_end_date}",
                    file=sys.stderr,
                )

        return schedules, output_format, directory

    def generate_report(
        self, raw_schedules: list[str], output_format: str, directory: str | None
    ) -> tuple[PrintableData, str, str]:
        schedules, output_format, directory = self.process_arguments(raw_schedules, output_format, directory)

        first_start_date = dt.datetime.now(dt.timezone.utc)
        last_end_date = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        for schedule in schedules:
            if schedule.start_date < first_start_date:
                first_start_date = schedule.start_date
            if schedule.end_date > last_end_date:
                last_end_date = schedule.end_date

        for year in range(first_start_date.year, last_end_date.year + 1):
            calendars.load_calendars(year)

        printable_data = PrintableData(start=first_start_date, end=last_end_date)

        prices_info = self.config.get_prices_info()
        print(
            f"Hourly prices (in {self.config.rotation_prices.currency}) - "
            f"Week day: {prices_info.week_day_hourly_price} ({prices_info.hours_week_day}h), "
            f"Weekend day: {prices_info.weekend_day_hourly_price} ({prices_info.hours_weekend_day}h), "
            f"Bank holiday: {prices_info.bh_day_hourly_price} ({prices_info.hours_bh_day}h)",
            file=sys.stderr,
        )

        for schedule in schedules:
            print(f"Loading information for the schedule '{schedule.id}'", file=sys.stderr)
            schedule_id, schedule_name, location, final_entries = self._get_schedule_information(
                schedule.id, schedule.start_date, schedule.end_date
            )

            users_rotation_data = self._get_users_rotation_data(final_entries, location)

            schedule_data = self._generate_schedule_data(
                schedule_id, schedule_name, users_rotation_data, prices_info, schedule
            )
            printable_data.schedules_data.append(schedule_data)

        printable_data.users_schedules_summary = self._calculate_summary_data(
            printable_data.schedules_data, prices_info
        )

        return printable_data, output_format, directory

    # -- internal helpers -------------------------------------------------

    def _get_schedule_information(
        self, schedule_id: str, start_date: dt.datetime, end_date: dt.datetime
    ) -> tuple[str, str, ZoneInfo, list[RenderedScheduleEntry]]:
        schedule = self.client.get_schedule(
            schedule_id,
            since=start_date.strftime("%Y-%m-%dT%H:%M:%S"),
            until=end_date.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        try:
            location = ZoneInfo(schedule.time_zone)
        except Exception:
            location = dt.timezone.utc
        return schedule.id, schedule.name, location, schedule.rendered_schedule_entries

    def _get_users_rotation_data(
        self, entries: list[RenderedScheduleEntry], location: ZoneInfo
    ) -> dict[str, UserRotaInfo]:
        users_info: dict[str, UserRotaInfo] = {}
        for entry in entries:
            start_date = _parse_rfc3339(entry.start).astimezone(location)
            end_date = _parse_rfc3339(entry.end).astimezone(location)

            user_rota_info = users_info.get(entry.user_id)
            if user_rota_info is None:
                user_rota_info = UserRotaInfo(id=entry.user_id, name=entry.user_summary)
                users_info[entry.user_id] = user_rota_info

            user_rota_info.periods.append(UserRotaPeriod(start=start_date, end=end_date))

        return users_info

    def _generate_schedule_data(
        self,
        schedule_id: str,
        schedule_name: str,
        users_rotation_data: dict[str, UserRotaInfo],
        prices_info: PricesInfo,
        schedule: ScheduleSpec,
    ) -> ScheduleData:
        schedule_data = ScheduleData(
            id=schedule_id, name=schedule_name, start_date=schedule.start_date, end_date=schedule.end_date
        )

        for user_id, user_rota_info in users_rotation_data.items():
            try:
                rotation_user_config = self.config.find_rotation_user_info_by_id(user_id)
            except ConfigError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                continue

            try:
                user_email_address = self._get_user_email(user_rota_info.id)
            except ReportError as exc:
                raise ReportError(f"aborted due to failed to get user's email address: {exc}") from exc

            schedule_user_data = ScheduleUser(name=user_rota_info.name, email_address=user_email_address)

            for period in user_rota_info.periods:
                current_month = period.start.month
                current_local_date = self._convert_to_user_local_timezone(period.start, user_rota_info.id)

                hour_increment = self.config.rotation_info.check_rotation_change_every / 60.0
                interval = dt.timedelta(minutes=self.config.rotation_info.check_rotation_change_every)

                while current_local_date < period.end:
                    calendar_name = f"{rotation_user_config.holidays_calendar}-{current_local_date.year}"
                    user_calendar = calendars.bank_holidays_calendars.get(calendar_name)
                    if user_calendar is None:
                        raise ReportError(
                            f"aborted due to calendar '{calendar_name}' not found for user '{user_id}' "
                            f"at date {current_local_date.strftime('%Y-%m-%d')}"
                        )

                    _update_data_for_date(
                        user_calendar, schedule_user_data, current_month, current_local_date, hour_increment, self.config
                    )
                    current_local_date = current_local_date + interval

            # Round accumulated hours to 2 decimal places to eliminate floating-point
            # noise from non-integer minute intervals (e.g. 5 min = 0.0833h per check)
            schedule_user_data.num_work_hours = round(schedule_user_data.num_work_hours, 2)
            schedule_user_data.num_weekend_hours = round(schedule_user_data.num_weekend_hours, 2)
            schedule_user_data.num_bank_holidays_hours = round(schedule_user_data.num_bank_holidays_hours, 2)

            schedule_user_data.num_work_days = schedule_user_data.num_work_hours / prices_info.hours_week_day
            schedule_user_data.num_weekend_days = schedule_user_data.num_weekend_hours / prices_info.hours_weekend_day
            schedule_user_data.num_bank_holidays_days = (
                schedule_user_data.num_bank_holidays_hours / prices_info.hours_bh_day
            )
            schedule_user_data.total_amount_work_hours = (
                schedule_user_data.num_work_hours * prices_info.week_day_hourly_price
            )
            schedule_user_data.total_amount_weekend_hours = (
                schedule_user_data.num_weekend_hours * prices_info.weekend_day_hourly_price
            )
            schedule_user_data.total_amount_bank_holidays_hours = (
                schedule_user_data.num_bank_holidays_hours * prices_info.bh_day_hourly_price
            )
            schedule_user_data.total_amount = (
                schedule_user_data.total_amount_work_hours
                + schedule_user_data.total_amount_weekend_hours
                + schedule_user_data.total_amount_bank_holidays_hours
            )
            schedule_data.rota_users.append(schedule_user_data)

        return schedule_data

    def _convert_to_user_local_timezone(self, schedule_date: dt.datetime, user_id: str) -> dt.datetime:
        timezone_name = self._get_user_timezone(user_id)
        try:
            location = ZoneInfo(timezone_name)
        except Exception as exc:
            raise ReportError(f"failed to load location by timezone: {exc}") from exc
        return schedule_date.astimezone(location)

    def _load_users_in_memory_cache(self) -> None:
        try:
            self._cached_users = self.client.list_users()
        except Exception as exc:
            raise ReportError(f"failed to load users in memory: {exc}") from exc

    def _get_user_timezone(self, user_id: str) -> str:
        if not self._cached_users:
            self._load_users_in_memory_cache()

        timezone_name = ""
        for user in self._cached_users or []:
            if user.id == user_id:
                timezone_name = user.timezone

        if not timezone_name:
            timezone_name = self.config.default_user_timezone

        return timezone_name

    def _get_user_email(self, user_id: str) -> str:
        if not self._cached_users:
            self._load_users_in_memory_cache()

        for user in self._cached_users or []:
            if user.id == user_id:
                return user.email

        return ""

    def _calculate_summary_data(
        self, schedules_data: list[ScheduleData], prices_info: PricesInfo
    ) -> list[ScheduleUser]:
        users_summary: dict[str, ScheduleUser] = {}

        for sched_data in schedules_data:
            for sched_user in sched_data.rota_users:
                user_summary = users_summary.get(sched_user.name)
                if user_summary is None:
                    user_summary = ScheduleUser(name=sched_user.name, email_address=sched_user.email_address)
                    users_summary[sched_user.name] = user_summary

                user_summary.num_work_hours += sched_user.num_work_hours
                user_summary.num_weekend_hours += sched_user.num_weekend_hours
                user_summary.num_bank_holidays_hours += sched_user.num_bank_holidays_hours
                user_summary.total_amount_work_hours += sched_user.total_amount_work_hours
                user_summary.total_amount_weekend_hours += sched_user.total_amount_weekend_hours
                user_summary.total_amount_bank_holidays_hours += sched_user.total_amount_bank_holidays_hours
                user_summary.total_amount += sched_user.total_amount

        result = list(users_summary.values())
        for user_summary in result:
            user_summary.num_work_days = user_summary.num_work_hours / prices_info.hours_week_day
            user_summary.num_weekend_days = user_summary.num_weekend_hours / prices_info.hours_weekend_day
            user_summary.num_bank_holidays_days = user_summary.num_bank_holidays_hours / prices_info.hours_bh_day

        return result


def _add_months(date: dt.datetime, months: int) -> dt.datetime:
    month_index = date.month - 1 + months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    return date.replace(year=year, month=month)


def _update_data_for_date(
    calendar: calendars.BHCalendar,
    data: ScheduleUser,
    current_month: int,
    date: dt.datetime,
    hour_increment: float,
    config: Configuration,
) -> None:
    if date.hour < config.rotation_info.daily_rotation_starts_at:
        # move to yesterday night to determine which kind of day it was
        new_date = date - dt.timedelta(hours=date.hour + 1)
        # if yesterday night was last month, ignore the date
        if new_date.month == current_month:
            _update_data_for_date(calendar, data, current_month, new_date, hour_increment, config)
        return

    if calendar.is_date_bank_holiday(date.date()):
        excluded_hours = config.find_rotation_excluded_hours_by_day("bankholiday")
        if excluded_hours is None:
            data.num_bank_holidays_hours += hour_increment
            return
        if date.hour < excluded_hours.excluded_starts_at or date.hour >= excluded_hours.excluded_ends_at:
            data.num_bank_holidays_hours += hour_increment
    elif calendar.is_weekend(date.date()):
        excluded_hours = config.find_rotation_excluded_hours_by_day("weekend")
        if excluded_hours is None:
            data.num_weekend_hours += hour_increment
            return
        if date.hour < excluded_hours.excluded_starts_at or date.hour >= excluded_hours.excluded_ends_at:
            data.num_weekend_hours += hour_increment
    else:
        excluded_hours = config.find_rotation_excluded_hours_by_day("weekday")
        if excluded_hours is None:
            data.num_work_hours += hour_increment
            return
        if date.hour < excluded_hours.excluded_starts_at or date.hour >= excluded_hours.excluded_ends_at:
            data.num_work_hours += hour_increment
