import datetime as dt

import pytest

from pd_report.config import Configuration, ConfigError, RotationExcludedHoursDay, RotationPriceDay, RotationPrices, RotationUser, parse_rfc822


def test_parse_rfc822_utc():
    result = parse_rfc822("01 Jan 20 00:00 UTC")
    assert result == dt.datetime(2020, 1, 1, 0, 0, tzinfo=dt.timezone.utc)


def test_find_price_by_day():
    config = Configuration(rotation_prices=RotationPrices(days_info=[RotationPriceDay(day="weekday", price=1)]))
    assert config.find_price_by_day("weekday") == 1


def test_find_price_by_day_missing():
    config = Configuration()
    with pytest.raises(ConfigError):
        config.find_price_by_day("weekday")


def test_find_rotation_user_info_by_id_found():
    config = Configuration(rotation_users=[RotationUser(user_id="U1", holidays_calendar="uk")])
    result = config.find_rotation_user_info_by_id("U1")
    assert result.holidays_calendar == "uk"


def test_find_rotation_user_info_by_id_defaults_to_calendar():
    config = Configuration(default_holiday_calendar="uk")
    result = config.find_rotation_user_info_by_id("UNKNOWN")
    assert result.holidays_calendar == "uk"


def test_find_rotation_user_info_by_id_missing_no_default():
    config = Configuration()
    with pytest.raises(ConfigError):
        config.find_rotation_user_info_by_id("UNKNOWN")


def test_get_prices_info_no_exclusions():
    config = Configuration(
        rotation_prices=RotationPrices(
            days_info=[
                RotationPriceDay(day="weekday", price=1),
                RotationPriceDay(day="weekend", price=2),
                RotationPriceDay(day="bankholiday", price=2),
            ]
        )
    )
    prices = config.get_prices_info()
    assert prices.hours_week_day == 24
    assert prices.week_day_hourly_price == pytest.approx(1 / 24)
    assert prices.hours_weekend_day == 24
    assert prices.hours_bh_day == 24


def test_get_prices_info_with_exclusions():
    config = Configuration(
        rotation_excluded_hours=[RotationExcludedHoursDay(day="weekday", excluded_starts_at=9, excluded_ends_at=17)],
        rotation_prices=RotationPrices(
            days_info=[
                RotationPriceDay(day="weekday", price=1),
                RotationPriceDay(day="weekend", price=2),
                RotationPriceDay(day="bankholiday", price=2),
            ]
        ),
    )
    prices = config.get_prices_info()
    assert prices.hours_week_day == 16
    assert prices.week_day_hourly_price == pytest.approx(1 / 16)
