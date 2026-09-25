#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from typing import Any

import click

from corvee.actor import resolve_actor
from corvee.cli.scope import fetch_merged
from corvee.constants import SCOPE_FILTERS, Scope, narrow_scope_filter
from corvee.db.events import get_last_comment
from corvee.db.tasks import TaskRow, mine_tasks
from corvee.guards.fields import validate_fields
from corvee.output import emit_tasks

EPILOG = """\
\b
Examples:
See everything the calling actor is already working on:
  corvee task mine --json
Cap it to the five most recent:
  corvee task mine --limit 5 --json
Pull out just the ids:
  corvee task mine --json | jq '.[].id'
Keep the session-start check cheap:
  corvee task mine --fields id,title --json
"""


def _fetch(conn: sqlite3.Connection, scope: Scope) -> list[tuple[TaskRow, dict[str, Any] | None]]:
    tasks = mine_tasks(conn, resolve_actor(), scope=scope)
    return [(task, get_last_comment(conn, task.id)) for task in tasks]


@click.command(epilog=EPILOG)
@click.option("--scope", "-s", "scope_filter", type=click.Choice(SCOPE_FILTERS), default="all")
@click.option("--limit", "-n", type=click.IntRange(min=1))
@click.option("--fields", "-f", "fields_csv")
@click.option("--json", "-j", "as_json", is_flag=True)
def mine(scope_filter: str, limit: int | None, fields_csv: str | None, as_json: bool) -> None:
    """Open tasks claimed by (or assigned and unclaimed to) $CORVEE_ACTOR,
    each with its last comment.

    The session-resume query.
    """
    fields = validate_fields(fields_csv.split(",")) if fields_csv else None
    pairs = fetch_merged(narrow_scope_filter(scope_filter), _fetch)
    # claimed_at desc, id as the final tiebreak — --limit applies after the
    # merge, never per scope.
    pairs.sort(key=lambda p: p[0].id, reverse=True)
    pairs.sort(key=lambda p: p[0].claimed_at or "", reverse=True)
    if limit is not None:
        pairs = pairs[:limit]

    results = []
    for task, last_comment in pairs:
        detail = task.to_dict()
        detail["last_comment"] = last_comment
        results.append(detail)
    emit_tasks(results, as_json=as_json, fields=fields)
