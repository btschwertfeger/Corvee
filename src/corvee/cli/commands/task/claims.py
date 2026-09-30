#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#
import sqlite3
from typing import Any

import click

from corvee.cli.params import output_option
from corvee.cli.scope import fetch_merged
from corvee.constants import SCOPE_FILTERS, Scope, narrow_output_format, narrow_scope_filter
from corvee.db.stats import claims_summary
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
See which actors currently hold live claims, oldest claim first:
  corvee task claims -o json
Check only the global backlog:
  corvee task claims --scope global -o json
Find one actor's claim count:
  corvee task claims -o json | jq '.[] | select(.actor == "agent:claude")'
"""


def _fetch(conn: sqlite3.Connection, scope: Scope) -> list[dict[str, Any]]:
    return [{"scope": scope, **row} for row in claims_summary(conn)]


def _oldest_claimed_at(row: dict[str, Any]) -> str:
    value = row["oldest_claimed_at"]
    if not isinstance(value, str):
        raise AssertionError(f"unexpected oldest_claimed_at: {value!r}")
    return value


@click.command(name="claims", epilog=EPILOG)
@click.option("--scope", "-s", "scope_filter", type=click.Choice(SCOPE_FILTERS), default="all")
@output_option()
def claims(scope_filter: str, output_format: str) -> None:
    """Actors currently holding live task claims, with a count and the oldest claimed_at."""
    rows = fetch_merged(narrow_scope_filter(scope_filter), _fetch)
    rows.sort(key=_oldest_claimed_at)
    emit_tasks(
        rows,
        output=narrow_output_format(output_format),
        fields=("actor", "scope", "count", "oldest_claimed_at"),
    )
