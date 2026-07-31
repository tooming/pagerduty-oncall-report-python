import datetime as dt

import pytest

from pd_report import calendars
from pd_report.api import RenderedScheduleEntry, Schedule, ScheduleDetail, User
from pd_report.config import Configuration, RotationInfo, RotationPriceDay, RotationPrices, RotationUser
from pd_report.engine import PagerDutyReportGenerator


class FakeClient:
    """Duck-typed stand-in for PagerDutyClient, no network calls."""

    def __init__(self, schedule_detail: ScheduleDetail, users: list[User]):
        self._schedule_detail = schedule_detail
        self._users = users

    def list_schedules(self):
        return [Schedule(id=self._schedule_detail.id, name=self._schedule_detail.name, time_zone="UTC")]

    def get_schedule(self, schedule_id, since, until):
        return self._schedule_detail

    def list_users(self):
        return self._users


@pytest.fixture(autouse=True)
def _load_2024_calendar():
    calendars.load_calendars(2024)


def _build_config() -> Configuration:
    return Configuration(
        default_user_timezone="UTC",
        default_holiday_calendar="",
        rotation_info=RotationInfo(daily_rotation_starts_at=8, check_rotation_change_every=60),
        rotation_prices=RotationPrices(
            currency="£",
            days_info=[
                RotationPriceDay(day="weekday", price=1),
                RotationPriceDay(day="weekend", price=2),
                RotationPriceDay(day="bankholiday", price=2),
            ],
        ),
        rotation_users=[RotationUser(user_id="U1", name="User One", holidays_calendar="uk")],
    )


def _build_schedule_detail() -> ScheduleDetail:
    return ScheduleDetail(
        id="SCHED1",
        name="Primary",
        time_zone="UTC",
        rendered_schedule_entries=[
            RenderedScheduleEntry(
                start="2024-01-01T00:00:00Z",
                end="2024-01-08T00:00:00Z",
                user_id="U1",
                user_summary="User One",
            )
        ],
    )


def test_generate_report_hour_classification_matches_expected_quirks():
    # Jan 1 2024 is a UK bank holiday (Mon); Jan 6-7 are weekend.
    # The "daily rotation starts at 8" logic attributes hours 00:00-07:59 of
    # each day to the *previous* calendar day, except for the very first
    # calendar day of the period (its early hours have no prior day within
    # the period's start month, so they are dropped) -- this quirk exists
    # in the original Go implementation and is intentionally preserved.
    config = _build_config()
    client = FakeClient(_build_schedule_detail(), users=[User(id="U1", email="user1@example.com", timezone="UTC")])
    generator = PagerDutyReportGenerator(client, config)

    printable_data, output_format, directory = generator.generate_report(["SCHED1"], "console", "/tmp")

    assert output_format == "console"
    schedule_data = printable_data.schedules_data[0]
    assert len(schedule_data.rota_users) == 1
    user_data = schedule_data.rota_users[0]

    assert user_data.num_bank_holidays_hours == pytest.approx(24)
    assert user_data.num_work_hours == pytest.approx(96)
    assert user_data.num_weekend_hours == pytest.approx(40)

    assert user_data.num_work_days == pytest.approx(4.0)
    assert user_data.num_bank_holidays_days == pytest.approx(1.0)
    assert user_data.num_weekend_days == pytest.approx(40 / 24)

    assert user_data.total_amount_work_hours == pytest.approx(96 * (1 / 24))
    assert user_data.total_amount_bank_holidays_hours == pytest.approx(24 * (2 / 24))
    assert user_data.total_amount_weekend_hours == pytest.approx(40 * (2 / 24))
    assert user_data.total_amount == pytest.approx(
        96 * (1 / 24) + 24 * (2 / 24) + 40 * (2 / 24)
    )

    assert user_data.email_address == "user1@example.com"

    # summary should match the single schedule's totals
    summary = printable_data.users_schedules_summary[0]
    assert summary.num_work_hours == pytest.approx(96)
