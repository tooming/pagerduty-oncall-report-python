from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ScheduleUser:
    name: str
    email_address: str = ""
    num_work_hours: float = 0.0
    num_work_days: float = 0.0
    total_amount_work_hours: float = 0.0
    num_weekend_hours: float = 0.0
    num_weekend_days: float = 0.0
    total_amount_weekend_hours: float = 0.0
    num_bank_holidays_hours: float = 0.0
    num_bank_holidays_days: float = 0.0
    total_amount_bank_holidays_hours: float = 0.0
    total_amount: float = 0.0


@dataclass
class ScheduleData:
    id: str
    name: str
    start_date: dt.datetime
    end_date: dt.datetime
    rota_users: list[ScheduleUser] = field(default_factory=list)


@dataclass
class PrintableData:
    start: dt.datetime
    end: dt.datetime
    schedules_data: list[ScheduleData] = field(default_factory=list)
    users_schedules_summary: list[ScheduleUser] = field(default_factory=list)


class Writer(Protocol):
    def generate_report(self, data: PrintableData) -> str:
        ...
