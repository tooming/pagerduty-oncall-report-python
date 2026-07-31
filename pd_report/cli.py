from __future__ import annotations

import sys

import click

from pd_report.api import PagerDutyAPIError, PagerDutyClient
from pd_report.config import ConfigError, load_config
from pd_report.engine import PagerDutyReportGenerator, ReportError
from pd_report.reportgen import ConsoleReport, CsvReport, PDFReport


@click.group()
@click.option("--config", "config_path", default=None, help="configuration file (default is ~/.pd-report-config.yml)")
@click.pass_context
def main(ctx: click.Context, config_path: str | None) -> None:
    """Generate on-call rotation reports automatically from your PagerDuty account."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


def _load(ctx: click.Context):
    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as exc:
        raise click.ClickException(str(exc))
    try:
        client = PagerDutyClient(config.pd_auth_token)
    except PagerDutyAPIError as exc:
        raise click.ClickException(str(exc))
    return config, client


@main.command("schedules")
@click.pass_context
def list_schedules(ctx: click.Context) -> None:
    """list schedules on PagerDuty"""
    _, client = _load(ctx)
    try:
        schedules = client.list_schedules()
    except PagerDutyAPIError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"==== Found {len(schedules)} schedule(s) ====")
    for schedule in schedules:
        click.echo(f"[{schedule.id}] {schedule.name:<20}, Timezone: {schedule.time_zone}")


@main.command("services")
@click.argument("team_id")
@click.pass_context
def list_services(ctx: click.Context, team_id: str) -> None:
    """list services on PagerDuty"""
    _, client = _load(ctx)
    try:
        services = client.list_services(team_id)
    except PagerDutyAPIError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"==== Found {len(services)} service(s) for the team {team_id} ====")
    for service in services:
        click.echo(f"[{service.id}] {service.name:<20}")


@main.command("teams")
@click.pass_context
def list_teams(ctx: click.Context) -> None:
    """list teams on PagerDuty"""
    _, client = _load(ctx)
    try:
        teams = client.list_teams()
    except PagerDutyAPIError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"==== Found {len(teams)} team(s) ====")
    for team in teams:
        click.echo(f"[{team.id}] {team.name:<20}")


@main.command("users")
@click.pass_context
def list_users(ctx: click.Context) -> None:
    """List users on PagerDuty"""
    _, client = _load(ctx)
    try:
        users = client.list_users()
    except PagerDutyAPIError as exc:
        raise click.ClickException(f"failed to fetch user list: {exc}")

    click.echo(f"==== Found {len(users)} user(s) ====")
    for user in users:
        user_teams = "".join(f"{team.id} " for team in user.teams)
        click.echo(f"[{user.id}] {user.name:<30} <{user.email}>{'':<38} in teams: {user_teams}")


@main.command("report")
@click.option(
    "-s",
    "--schedules",
    "raw_schedules",
    default="all",
    help="schedule ids to report (comma-separated with no spaces), or 'all'",
)
@click.option("-o", "--output-format", default="console", help="pdf, console, csv")
@click.option("-d", "--output", "directory", default=None, help="output path (default is $HOME)")
@click.pass_context
def generate_report(ctx: click.Context, raw_schedules: str, output_format: str, directory: str | None) -> None:
    """generates the report(s) for the given schedule(s) id(s)"""
    config, client = _load(ctx)
    generator = PagerDutyReportGenerator(client, config)

    schedule_ids = raw_schedules.split(",")

    try:
        printable_data, output_format, directory = generator.generate_report(schedule_ids, output_format, directory)
    except (ReportError, PagerDutyAPIError, ConfigError) as exc:
        raise click.ClickException(str(exc))

    if output_format == "pdf":
        writer = PDFReport(config.rotation_prices.currency, directory)
    elif output_format == "csv":
        writer = CsvReport(config.rotation_prices.currency, directory)
    else:
        writer = ConsoleReport(config.rotation_prices.currency)

    try:
        message = writer.generate_report(printable_data)
    except OSError as exc:
        raise click.ClickException(str(exc))

    if message:
        click.echo(message, err=True)


if __name__ == "__main__":
    main()
