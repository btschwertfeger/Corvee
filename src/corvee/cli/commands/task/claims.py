#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#
import sqlite3
from typing import Any

import click

from corvee.cli.scope import fetch_merged
from corvee.constants import SCOPE_FILTERS, Scope, narrow_scope_filter
from corvee.db.stats import claims_summary
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
See which actors currently hold live claims, oldest claim first:
  corvee task claims --json
Check only the global backlog:
  corvee task claims --scope global --json
Find one actor's claim count:
  corvee task claims --json | jq '.[] | select(.actor == "agent:claude")'
"""


def _fetch(conn: sqlite3.Connection, scope: Scope) -> list[dict[str, Any]]:
    return [{"scope": scope, **row} for row in claims_summary(conn)]


@click.command(name="claims", epilog=EPILOG)
@click.option("--scope", "-s", "scope_filter", type=click.Choice(SCOPE_FILTERS), default="all")
@click.option("--json", "-j", "as_json", is_flag=True)
def claims(scope_filter: str, as_json: bool) -> None:
    """Actors currently holding live task claims, with a count and the oldest claimed_at."""
    rows = fetch_merged(narrow_scope_filter(scope_filter), _fetch)
    rows.sort(key=lambda r: str(r["oldest_claimed_at"]))
    emit_tasks(rows, as_json=as_json, fields=("actor", "scope", "count", "oldest_claimed_at"))
