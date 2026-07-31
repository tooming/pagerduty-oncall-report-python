import datetime as dt

from pd_report import calendars


def test_load_calendars_finds_uk_2024_new_year():
    calendars.load_calendars(2024)
    cal = calendars.bank_holidays_calendars["uk-2024"]
    assert cal.is_date_bank_holiday(dt.date(2024, 1, 1))
    assert not cal.is_date_bank_holiday(dt.date(2024, 1, 2))


def test_is_weekend():
    saturday = dt.date(2024, 1, 6)
    sunday = dt.date(2024, 1, 7)
    monday = dt.date(2024, 1, 8)
    assert calendars.BHCalendar.is_weekend(saturday)
    assert calendars.BHCalendar.is_weekend(sunday)
    assert not calendars.BHCalendar.is_weekend(monday)


def test_load_calendars_is_idempotent_and_merges_years():
    calendars.load_calendars(2024)
    calendars.load_calendars(2025)
    assert "uk-2024" in calendars.bank_holidays_calendars
    assert "uk-2025" in calendars.bank_holidays_calendars
