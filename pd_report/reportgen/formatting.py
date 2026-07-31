from __future__ import annotations

import datetime as dt


def fmt_long(date: dt.datetime) -> str:
    return date.strftime("%a %b %d %H:%M:%S %Y")


def fmt_rfc822(date: dt.datetime) -> str:
    tzname = date.tzname() or ""
    return date.strftime("%d %b %y %H:%M") + (f" {tzname}" if tzname else "")


def fmt_num(value: float) -> str:
    # mimic Go's "%v" for float32: integers print without a decimal point.
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"
