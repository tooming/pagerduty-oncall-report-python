# pd-report (Python)

A Python port of [go-pagerduty-oncall-report](https://github.com/form3tech-oss/go-pagerduty-oncall-report)
(based on the fixes in [tooming/go-pagerduty-oncall-report](https://github.com/tooming/go-pagerduty-oncall-report)).

Generates a report for on-call rotations using the PagerDuty API: hours/days worked broken down
into weekday, weekend and bank-holiday buckets, with an hourly rate applied to each bucket.

## Just want total on-call hours per engineer?

If you don't need the weekday/weekend/bank-holiday/pricing breakdown — just a per-engineer hours
total across your schedules — use [oncall_hours.py](oncall_hours.py) instead. It's a single
stdlib-only file: no `pip install`, no cloning this repo, no config file.

```bash
export PD_AUTH_TOKEN=<YourSecretTokenHere>
curl -sO https://raw.githubusercontent.com/tooming/pagerduty-oncall-report-python/main/oncall_hours.py
python3 oncall_hours.py --since 2026-07-01 --until 2026-08-01
```

Output:

```
Martin Tooming	185.50
Someone Else	142.00
```

Defaults to last calendar month if `--since`/`--until` are omitted, and to all schedules on the
account if `-s/--schedules` is omitted (comma-separated schedule IDs to scope it). Set
`PD_API_BASE_URL=https://api.eu.pagerduty.com` for EU-hosted accounts. The rest of this README is
about the full `pd-report` package (pricing, CSV/PDF output, bank holiday calendars, etc.) — skip
it if `oncall_hours.py` is all you need.

## Installation

```bash
git clone <this repo>
cd pagerduty-oncall-report-py
python3 -m venv .venv
.venv/bin/pip install -e .
```

This installs a `pd-report` console script into `.venv/bin/`.

## Usage

```
Usage: pd-report [OPTIONS] COMMAND [ARGS]...

  Generate on-call rotation reports automatically from your PagerDuty account.

Options:
  --config TEXT  configuration file (default is ~/.pd-report-config.yml)
  --help         Show this message and exit.

Commands:
  report     generates the report(s) for the given schedule(s) id(s)
  schedules  list schedules on PagerDuty
  services   list services on PagerDuty
  teams      list teams on PagerDuty
  users      List users on PagerDuty
```

`report` specific flags:

```
Usage: pd-report report [OPTIONS]

Options:
  -s, --schedules TEXT       schedule ids to report (comma-separated with no
                              spaces), or 'all'  [default: all]
  -o, --output-format TEXT   pdf, console, csv  [default: console]
  -d, --output TEXT          output path (default is $HOME)
```

## Configuration

Set your PagerDuty API token in the environment:

```bash
export PD_AUTH_TOKEN=<YourSecretTokenHere>
```

PagerDuty runs separate US and EU clusters with different API hosts. This defaults to the US/global
cluster (`https://api.pagerduty.com`); EU-hosted accounts need to override it, either in the config file
(`apiBaseUrl: https://api.eu.pagerduty.com`) or via an env var, which takes priority over the config file:

```bash
export PD_API_BASE_URL=https://api.eu.pagerduty.com
```

Configure the application in a YAML file (see [pd-report-config.example.yml](pd-report-config.example.yml)),
passed via `--config` (default `~/.pd-report-config.yml`):

```yml
apiBaseUrl: https://api.pagerduty.com # or https://api.eu.pagerduty.com for EU accounts

reportTimeRange:
  start: 01 Jan 20 00:00 UTC
  end: 01 Feb 20 00:00 UTC

rotationInfo:
  dailyRotationStartsAt: 8
  checkRotationChangeEvery: 30 # minutes

defaultUserTimezone: Europe/London
defaultHolidayCalendar: uk

rotationExcludedHours:
  - day: weekday
    excludedStartsAt: 9
    excludedEndsAt: 17

rotationPrices:
  currency: £
  daysInfo:
    - day: weekday
      price: 1
    - day: weekend
      price: 2
    - day: bankholiday
      price: 2

rotationUsers:
  - name: "User 1"
    holidaysCalendar: uk
    userId: P11A11B

scheduleTimeRangeOverrides:
  - id: ABCDEFG
    start: 01 Jan 20 00:00 UTC
    end: 21 Jan 20 00:00 UTC

schedulesToIgnore:
  - SCHED_1
```

Bank holiday calendars are bundled under [pd_report/assets/calendars](pd_report/assets/calendars) (ported
directly from the original Go project's `_assets/calendars`).

## Differences from the Go original

- PDF generation uses [fpdf2](https://github.com/py-pdf/fpdf2) instead of gofpdf; core fonts support the
  Latin-1 character set (covers `£`, accented Latin names, etc.) but not arbitrary Unicode.
- Calendars for every year spanned by a report are loaded up front, and the correct calendar year is looked
  up per rotation date rather than once per schedule — matching the fixes in the `tooming` fork.
- The "copyable summary" section at the end of the console report is included, also from that fork.
- The quirk where a period's first calendar day can lose its pre-`dailyRotationStartsAt` hours (because
  there is no earlier day in the same month to attribute them to) is preserved as-is from the original
  implementation, rather than "fixed" — this is a faithful port, not a rewrite of the business logic.

## Development

```bash
.venv/bin/pip install -e . pytest
.venv/bin/pytest
```

## Known limitations

(carried over from the original project)

- `report` command: no way to specify the output filename for the PDF/CSV reports beyond the output directory.
- No support for loading calendars from outside the package.
