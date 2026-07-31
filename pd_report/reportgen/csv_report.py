from __future__ import annotations

import csv
import datetime as dt
import os
import sys

from pd_report.reportgen.formatting import fmt_long as _fmt_long
from pd_report.reportgen.formatting import fmt_num as _num
from pd_report.reportgen.formatting import fmt_rfc822 as _fmt_rfc822
from pd_report.reportgen.types import PrintableData, ScheduleData, ScheduleUser

SEPARATOR = " " + "-" * 140


class CsvReport:
    def __init__(self, currency: str, out_path: str):
        self.currency = currency.strip()
        self.out_path = out_path

    def generate_report(self, data: PrintableData) -> str:
        print(SEPARATOR)
        print(
            f"| Generating report(s) from '{_fmt_long(data.start)}' to "
            f"'{_fmt_long(data.end - dt.timedelta(seconds=1))}'"
        )
        print(SEPARATOR)

        header = [
            "User",
            "Email",
            "Weekday Hours",
            "Weekday Days",
            "Weekend Hours",
            "Weekend Days",
            "Bank Holiday Hours",
            "Bank Holiday Days",
            f"Total Weekday Amount ({self.currency})",
            f"Total Weekend Amount ({self.currency})",
            f"Total Bank Holiday Amount ({self.currency})",
            f"Total  Amount ({self.currency})",
        ]

        for schedule_data in data.schedules_data:
            self._write_single_rotation(schedule_data, data, header)

        filename = os.path.join(
            self.out_path, f"pagerduty_oncall_report.{data.start.month}-{data.start.year}-Summary.csv"
        )
        _remove_if_exists(filename)

        data.users_schedules_summary.sort(key=lambda u: u.name)
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for user_data in data.users_schedules_summary:
                _write_user(user_data, writer)

        return f"Report successfully generated: file://{filename}"

    def _write_single_rotation(self, schedule_data: ScheduleData, data: PrintableData, header: list[str]) -> None:
        print(SEPARATOR)
        print(f"| Writing Schedule: '{schedule_data.name}' ({schedule_data.id})")
        print(
            f"| Time Range: {_fmt_rfc822(schedule_data.start_date)} to "
            f"{_fmt_rfc822(schedule_data.end_date)}"
        )
        print(SEPARATOR)

        no_space_name = schedule_data.name.replace(" ", "_")
        filename = os.path.join(
            self.out_path,
            f"pagerduty_oncall_report.{data.start.month}-{data.start.year}-{no_space_name}-{schedule_data.id}.csv",
        )
        _remove_if_exists(filename)

        schedule_data.rota_users.sort(key=lambda u: u.name)
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for user_data in schedule_data.rota_users:
                _write_user(user_data, writer)

        print(f"Report successfully generated: file://{filename}", file=sys.stderr)


def _remove_if_exists(filename: str) -> None:
    try:
        os.remove(filename)
    except FileNotFoundError:
        pass


def _write_user(user_data: ScheduleUser, writer: "csv._writer") -> None:
    writer.writerow(
        [
            user_data.name,
            user_data.email_address,
            _num(user_data.num_work_hours),
            f"{user_data.num_work_days:.1f}",
            _num(user_data.num_weekend_hours),
            f"{user_data.num_weekend_days:.1f}",
            _num(user_data.num_bank_holidays_hours),
            f"{user_data.num_bank_holidays_days:.1f}",
            _num(user_data.total_amount_work_hours),
            _num(user_data.total_amount_weekend_hours),
            _num(user_data.total_amount_bank_holidays_hours),
            _num(user_data.total_amount),
        ]
    )
