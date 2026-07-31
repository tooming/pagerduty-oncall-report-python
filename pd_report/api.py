from __future__ import annotations

from dataclasses import dataclass, field

import requests

API_BASE_URL = "https://api.pagerduty.com"


class PagerDutyAPIError(RuntimeError):
    pass


@dataclass
class Team:
    id: str
    name: str


@dataclass
class User:
    id: str
    summary: str = ""
    name: str = ""
    email: str = ""
    timezone: str = ""
    teams: list[Team] = field(default_factory=list)


@dataclass
class Service:
    id: str
    name: str


@dataclass
class Schedule:
    id: str
    name: str
    time_zone: str = ""


@dataclass
class RenderedScheduleEntry:
    start: str
    end: str
    user_id: str
    user_summary: str


@dataclass
class ScheduleDetail:
    id: str
    name: str
    time_zone: str
    rendered_schedule_entries: list[RenderedScheduleEntry] = field(default_factory=list)


class PagerDutyClient:
    """Thin wrapper around the PagerDuty REST API (v2)."""

    def __init__(self, auth_token: str, base_url: str = API_BASE_URL, timeout: float = 30.0):
        if not auth_token:
            raise PagerDutyAPIError("PagerDuty auth token is not set (PD_AUTH_TOKEN)")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token token={auth_token}",
                "Accept": "application/vnd.pagerduty+json;version=2",
                "Content-Type": "application/json",
            }
        )

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        if not response.ok:
            raise PagerDutyAPIError(
                f"PagerDuty API request to {path} failed: {response.status_code} {response.text}"
            )
        return response.json()

    def _paginate(self, path: str, key: str, params: dict | None = None) -> list[dict]:
        params = dict(params or {})
        params.setdefault("limit", 100)
        offset = 0
        results: list[dict] = []
        while True:
            params["offset"] = offset
            payload = self._get(path, params=params)
            items = payload.get(key, [])
            results.extend(items)
            if not payload.get("more"):
                break
            offset += payload.get("limit", len(items) or 100)
        return results

    def list_users(self) -> list[User]:
        raw_users = self._paginate("/users", "users")
        return [_convert_user(u) for u in raw_users]

    def get_user_by_id(self, user_id: str) -> User:
        payload = self._get(f"/users/{user_id}")
        return _convert_user(payload["user"])

    def list_teams(self) -> list[Team]:
        raw_teams = self._paginate("/teams", "teams")
        return [Team(id=t["id"], name=t["name"]) for t in raw_teams]

    def list_services(self, team_id: str) -> list[Service]:
        raw_services = self._paginate("/services", "services", params={"team_ids[]": team_id})
        return [Service(id=s["id"], name=s["name"]) for s in raw_services]

    def list_schedules(self) -> list[Schedule]:
        raw_schedules = self._paginate("/schedules", "schedules")
        return [Schedule(id=s["id"], name=s["name"], time_zone=s.get("time_zone", "")) for s in raw_schedules]

    def get_schedule(self, schedule_id: str, since: str, until: str) -> ScheduleDetail:
        payload = self._get(f"/schedules/{schedule_id}", params={"since": since, "until": until})
        schedule = payload["schedule"]
        final_schedule = schedule.get("final_schedule", {}) or {}
        entries = [
            RenderedScheduleEntry(
                start=entry["start"],
                end=entry["end"],
                user_id=entry["user"]["id"],
                user_summary=entry["user"].get("summary", ""),
            )
            for entry in final_schedule.get("rendered_schedule_entries", [])
        ]
        return ScheduleDetail(
            id=schedule["id"],
            name=schedule["name"],
            time_zone=schedule.get("time_zone", ""),
            rendered_schedule_entries=entries,
        )


def _convert_user(raw: dict) -> User:
    teams = [Team(id=t["id"], name=t.get("summary", t.get("name", ""))) for t in raw.get("teams", [])]
    return User(
        id=raw["id"],
        summary=raw.get("summary", ""),
        name=raw.get("name", ""),
        email=raw.get("email", ""),
        timezone=raw.get("time_zone", ""),
        teams=teams,
    )
