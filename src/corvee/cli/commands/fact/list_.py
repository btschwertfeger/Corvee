#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from datetime import UTC, datetime

import click

from corvee.cli.scope import fetch_merged, sort_facts
from corvee.constants import (
    DEFAULT_STALE_DURATION,
    FACT_LIST_FIELDS,
    FACT_STATUSES,
    SCOPE_FILTERS,
    narrow_fact_status,
    narrow_scope_filter,
)
from corvee.db.facts import FactFilter, list_facts
from corvee.guards.fields import validate_fields
from corvee.output import emit_facts
from corvee.timeutil import parse_duration, timestamp

EPILOG = """\
\b
Examples:
List every non-retracted fact, newest first:
  corvee fact list --json
Narrow to facts currently verified:
  corvee fact list --status verified --json
Include retracted facts too, trimmed to a few fields:
  corvee fact list --all --json --fields id,claim,status
List only the facts filed with --global:
  corvee fact list --scope global --json
See everything that changed while you were away:
  corvee fact list --since 7d --all --json
Check what a specific actor has verified:
  corvee fact list --verified-by agent:claude --json
Find verified facts whose proof hasn't been rechecked in a while:
  corvee fact list --stale --json
Use a longer cutoff than the default:
  corvee fact list --stale 30d --json
"""


@click.command(name="list", epilog=EPILOG)
@click.option("--status", "-S", type=click.Choice(FACT_STATUSES), default=None)
@click.option("--since", "-d", "since_duration", help="Only facts updated within this duration.")
@click.option("--verified-by", "-v", "verified_by")
@click.option(
    "--stale",
    "-i",
    "stale_duration",
    is_flag=False,
    flag_value=DEFAULT_STALE_DURATION,
    default=None,
)
@click.option("--all", "-a", "include_all", is_flag=True)
@click.option("--scope", "-s", "scope_filter", type=click.Choice(SCOPE_FILTERS), default="all")
@click.option("--limit", "-n", type=click.IntRange(min=1))
@click.option("--fields", "-f", "fields_csv")
@click.option("--json", "-j", "as_json", is_flag=True)
def list_command(
    status: str | None,
    since_duration: str | None,
    verified_by: str | None,
    stale_duration: str | None,
    include_all: bool,
    scope_filter: str,
    limit: int | None,
    fields_csv: str | None,
    as_json: bool,
) -> None:
    """List facts. Default excludes retracted; --all includes them. Also runs as `ls`."""
    fields = (
        validate_fields(fields_csv.split(","), allowed=FACT_LIST_FIELDS) if fields_csv else None
    )
    updated_since = None
    if since_duration is not None:
        updated_since = timestamp(datetime.now(UTC) - parse_duration(since_duration))
    stale_before = None
    if stale_duration is not None:
        stale_before = timestamp(datetime.now(UTC) - parse_duration(stale_duration))
    filt = FactFilter(
        status=narrow_fact_status(status) if status else None,
        include_all=include_all,
        updated_since=updated_since,
        verified_by=verified_by,
        stale_before=stale_before,
        # --limit applies after the merge, never per scope.
    )
    facts = sort_facts(
        fetch_merged(
            narrow_scope_filter(scope_filter), lambda conn, s: list_facts(conn, filt, scope=s)
        )
    )
    if limit is not None:
        facts = facts[:limit]
    emit_facts([f.to_dict() for f in facts], as_json=as_json, fields=fields)
