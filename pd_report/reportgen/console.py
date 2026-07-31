from __future__ import annotations

import datetime as dt

from pd_report.reportgen.formatting import fmt_long as _fmt_long
from pd_report.reportgen.formatting import fmt_num as _fmt_num
from pd_report.reportgen.formatting import fmt_rfc822 as _fmt_rfc822
from pd_report.reportgen.types import PrintableData, ScheduleUser

SEPARATOR = " " + "-" * 140
ROW_FORMAT = (
    "| {:<35} || {:>7} | {:>7} | {:>12} | {:>13} | {:>13} | {:>18} | {:>9} |"
)


class ConsoleReport:
    def __init__(self, currency: str):
        self.currency = currency

    def generate_report(self, data: PrintableData) -> str:
        print(SEPARATOR)
        print(
            f"| Generating report(s) from '{_fmt_long(data.start)}' to "
            f"'{_fmt_long(data.end - dt.timedelta(seconds=1))}'"
        )
        print(SEPARATOR)

        for schedule_data in data.schedules_data:
            print("")
            print(SEPARATOR)
            print(f"| Schedule: '{schedule_data.name}' ({schedule_data.id})")
            print(
                f"| Time Range: {_fmt_rfc822(schedule_data.start_date)} to "
                f"{_fmt_rfc822(schedule_data.end_date)}"
            )
            print(SEPARATOR)
            self._print_header()

            schedule_data.rota_users.sort(key=lambda u: u.name)
            for user_data in schedule_data.rota_users:
                self._print_user(user_data)

        print("")
        print(SEPARATOR)
        print("| Users summary")
        print(SEPARATOR)
        self._print_header()

        data.users_schedules_summary.sort(key=lambda u: u.name)
        for user_data in data.users_schedules_summary:
            self._print_user(user_data)

        print("")
        print("Copyable Summary (Name - Total Hours):")
        print("")
        for user_data in data.users_schedules_summary:
            total_hours = user_data.num_work_hours + user_data.num_weekend_hours + user_data.num_bank_holidays_hours
            print(f"{user_data.name:<25} {_fmt_num(total_hours)}")

        return ""

    def _print_header(self) -> None:
        print(ROW_FORMAT.format("USER", "WEEKDAY", "WEEKEND", "BANK HOLIDAY", "TOTAL WEEKDAY", "TOTAL WEEKEND", "TOTAL BANK HOLIDAY", "TOTAL"))
        print(ROW_FORMAT.format("EMAIL", "HOURS", "HOURS", "HOURS", "AMOUNT", "AMOUNT", "AMOUNT", "AMOUNT"))
        print(ROW_FORMAT.format("", "DAYS", "DAYS", "DAYS", "", "", "", ""))
        print(SEPARATOR)

    def _print_user(self, user_data: ScheduleUser) -> None:
        print(
            ROW_FORMAT.format(
                user_data.name,
                f"{_fmt_num(user_data.num_work_hours)} h",
                f"{_fmt_num(user_data.num_weekend_hours)} h",
                f"{_fmt_num(user_data.num_bank_holidays_hours)} h",
                f"{self.currency}{_fmt_num(user_data.total_amount_work_hours)}",
                f"{self.currency}{_fmt_num(user_data.total_amount_weekend_hours)}",
                f"{self.currency}{_fmt_num(user_data.total_amount_bank_holidays_hours)}",
                f"{self.currency}{_fmt_num(user_data.total_amount)}",
            )
        )
        print(
            ROW_FORMAT.format(
                user_data.email_address,
                f"{user_data.num_work_days:.1f} d",
                f"{user_data.num_weekend_days:.1f} d",
                f"{user_data.num_bank_holidays_days:.1f} d",
                "_____________",
                "_____________",
                "__________________",
                "_________",
            )
        )
        print(SEPARATOR)
