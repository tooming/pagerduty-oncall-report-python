from __future__ import annotations

import datetime as dt
import os
import sys

from fpdf import FPDF

from pd_report.reportgen.formatting import fmt_num, fmt_rfc822
from pd_report.reportgen.types import PrintableData, ScheduleUser

MATRIX_ROW_FORMAT = "{:<40} {:>8} {:>8} {:>10} {:>8} {:>8} {:>12} {:>10}"


class PDFReport:
    def __init__(self, currency: str, out_path: str):
        self.currency = currency
        self.out_path = out_path

    def generate_report(self, data: PrintableData) -> str:
        print("Generating pdf report...", file=sys.stderr)
        print("  -> Schedules:", file=sys.stderr)
        for item in data.schedules_data:
            print(f"  {item.name}", file=sys.stderr)

        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_top_margin(30)
        pdf.set_auto_page_break(True, margin=15)

        header_text = (
            f"PagerDuty oncall report(s) from {data.start.strftime('%d/%m/%Y')} "
            f"to {(data.end - dt.timedelta(seconds=1)).strftime('%d/%m/%Y')} "
        )

        def header() -> None:
            pdf.set_y(5)
            pdf.set_font("Helvetica", "B", 15)
            pdf.cell(0, 10, header_text, border="R", align="R")
            pdf.ln(20)

        pdf.header = header
        pdf.add_page()

        for schedule_data in data.schedules_data:
            pdf.set_font("Helvetica", "B", 13)
            pdf.cell(0, 5, f"  Schedule name: '{schedule_data.name}'", border="L", align="L")
            pdf.ln(8)
            pdf.cell(0, 5, f"  Schedule ID: {schedule_data.id}", border="L", align="L")
            pdf.ln(8)
            pdf.cell(
                0,
                5,
                f"Time Range: {fmt_rfc822(schedule_data.start_date)} to {fmt_rfc822(schedule_data.end_date)}",
                border="L",
                align="L",
            )
            pdf.ln(8)

            self._print_header(pdf)

            pdf.set_font("Courier", "", 8)
            schedule_data.rota_users.sort(key=lambda u: u.name)
            for user_data in schedule_data.rota_users:
                self._print_user(pdf, user_data)

            pdf.ln(10)

        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 5, "  Users summary", border="L", align="L")
        pdf.ln(8)

        self._print_header(pdf)

        data.users_schedules_summary.sort(key=lambda u: u.name)
        pdf.set_font("Courier", "", 8)
        for user_data in data.users_schedules_summary:
            self._print_user(pdf, user_data)

        filename = os.path.join(self.out_path, f"pagerduty_oncall_report.{data.start.month}-{data.start.year}.pdf")
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass

        pdf.output(filename)

        return f"Report successfully generated: file://{filename}"

    def _print_header(self, pdf: FPDF) -> None:
        pdf.set_font("Courier", "B", 8)
        pdf.cell(
            0,
            5,
            MATRIX_ROW_FORMAT.format("USER", "WEEKDAY", "WEEKEND", "B. HOLIDAY", "WEEKDAY", "WEEKEND", "B. HOLIDAY", "TOTAL"),
            align="L",
        )
        pdf.ln(3)
        pdf.cell(
            0,
            5,
            MATRIX_ROW_FORMAT.format("EMAIL", "HOURS", "HOURS", "HOURS", "AMOUNT", "AMOUNT", "AMOUNT", "AMOUNT"),
            align="L",
        )
        pdf.ln(3)
        pdf.cell(0, 5, MATRIX_ROW_FORMAT.format("", "DAYS", "DAYS", "DAYS", "", "", "", ""), border="B", align="L")
        pdf.ln(5)

    def _print_user(self, pdf: FPDF, user_data: ScheduleUser) -> None:
        pdf.cell(
            0,
            5,
            MATRIX_ROW_FORMAT.format(
                user_data.name,
                f"{fmt_num(user_data.num_work_hours)} h",
                f"{fmt_num(user_data.num_weekend_hours)} h",
                f"{fmt_num(user_data.num_bank_holidays_hours)} h",
                f"{self.currency}{fmt_num(user_data.total_amount_work_hours)}",
                f"{self.currency}{fmt_num(user_data.total_amount_weekend_hours)}",
                f"{self.currency}{fmt_num(user_data.total_amount_bank_holidays_hours)}",
                f"{self.currency}{fmt_num(user_data.total_amount)}",
            ),
            align="L",
        )
        pdf.ln(3)
        pdf.cell(
            0,
            5,
            MATRIX_ROW_FORMAT.format(
                user_data.email_address,
                f"{user_data.num_work_days:.1f} d",
                f"{user_data.num_weekend_days:.1f} d",
                f"{user_data.num_bank_holidays_days:.1f} d",
                "",
                "",
                "",
                "",
            ),
            border="B",
            align="L",
        )
        pdf.ln(5)
