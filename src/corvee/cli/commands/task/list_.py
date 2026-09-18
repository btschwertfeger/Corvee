#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

import click

from corvee.cli.completion import complete_labels, complete_task_ids
from corvee.cli.scope import fetch_merged, paginate_after, resolve_cursor, sort_tasks
from corvee.constants import (
    DEFAULT_STALE_DURATION,
    PRIORITIES,
    SCOPE_FILTERS,
    STATES,
    TASK_TYPES,
    Priority,
    Scope,
    ScopeFilter,
    State,
    TaskType,
)
from corvee.db.tasks import TaskFilter, list_tasks
from corvee.guards.fields import validate_fields
from corvee.models import TaskRow, parse_task_ref
from corvee.output import emit_tasks
from corvee.timeutil import parse_duration, timestamp

EPILOG = """\
\b
Examples:
List every open task, newest first:
  corvee task list --json
Narrow to one actor's tasks carrying a label, trimmed to a couple of fields:
  corvee task list --label api --claimed-by agent:claude --json --fields id,title
Find what's been routed to a specific actor but not yet claimed:
  corvee task list --assigned-to agent:claude --unclaimed --json
Find claims that have gone quiet:
  corvee task list --stale --json
List only the tasks filed with --global:
  corvee task list --scope global --json
Find what blocks TASK-9:
  corvee task list --blocked-by TASK-9 --json
Find what TASK-9 blocks:
  corvee task list --blocks TASK-9 --json
See everything that changed while you were away:
  corvee task list --since 7d --all --json
Page through a large backlog, 50 rows at a time:
  corvee task list --limit 50 --json
Then fetch the next page, starting after the last id seen:
  corvee task list --after TASK-233 --limit 50 --json
"""


@click.command(name="list", epilog=EPILOG)
@click.option("--state", "-S", type=click.Choice(STATES))
@click.option("--type", "-t", "type_", type=click.Choice(TASK_TYPES))
@click.option("--priority", "-p", type=click.Choice(PRIORITIES))
@click.option("--label", "-l", "labels", multiple=True, shell_complete=complete_labels)
@click.option("--parent", "-P", "parent_ref", shell_complete=complete_task_ids)
@click.option(
    "--blocks",
    "-b",
    "blocks_ref",
    help="Tasks that <id> blocks.",
    shell_complete=complete_task_ids,
)
@click.option(
    "--blocked-by",
    "-B",
    "blocked_by_ref",
    help="Tasks that block <id>.",
    shell_complete=complete_task_ids,
)
@click.option(
    "--relates-to",
    "-r",
    "relates_to_ref",
    help="Tasks related to <id> (symmetric).",
    shell_complete=complete_task_ids,
)
@click.option("--claimed-by", "-c", "claimed_by")
@click.option("--unclaimed", "-u", is_flag=True)
@click.option("--assigned-to", "-A", "assigned_to")
@click.option(
    "--stale",
    "-i",
    "stale_duration",
    is_flag=False,
    flag_value=DEFAULT_STALE_DURATION,
    default=None,
)
@click.option("--since", "-d", "since_duration", help="Only tasks updated within this duration.")
@click.option("--all", "-a", "include_all", is_flag=True)
@click.option("--scope", "-s", "scope_filter", type=click.Choice(SCOPE_FILTERS), default="all")
@click.option(
    "--after",
    "-k",
    "after_ref",
    help="Cursor: only tasks after this id in the fixed order.",
    shell_complete=complete_task_ids,
)
@click.option("--limit", "-n", type=click.IntRange(min=1))
@click.option("--fields", "-f", "fields_csv")
@click.option("--json", "-j", "as_json", is_flag=True)
def list_command(
    state: str | None,
    type_: str | None,
    priority: str | None,
    labels: tuple[str, ...],
    parent_ref: str | None,
    blocks_ref: str | None,
    blocked_by_ref: str | None,
    relates_to_ref: str | None,
    claimed_by: str | None,
    unclaimed: bool,
    assigned_to: str | None,
    stale_duration: str | None,
    since_duration: str | None,
    include_all: bool,
    scope_filter: str,
    after_ref: str | None,
    limit: int | None,
    fields_csv: str | None,
    as_json: bool,
) -> None:
    """List tasks with full filtering and column projection. Also runs as `ls`."""
    fields = validate_fields(fields_csv.split(",")) if fields_csv else None
    parent = parse_task_ref(parent_ref) if parent_ref else None
    blocks = parse_task_ref(blocks_ref) if blocks_ref else None
    blocked_by = parse_task_ref(blocked_by_ref) if blocked_by_ref else None
    relates_to = parse_task_ref(relates_to_ref) if relates_to_ref else None
    ref_scopes = [ref.scope for ref in (parent, blocks, blocked_by, relates_to) if ref is not None]
    stale_before = None
    if stale_duration is not None:
        cutoff = datetime.now(UTC) - parse_duration(stale_duration)
        stale_before = timestamp(cutoff)
    updated_since = None
    if since_duration is not None:
        updated_since = timestamp(datetime.now(UTC) - parse_duration(since_duration))
    filt = TaskFilter(
        states=(cast(State, state),) if state else None,
        include_all=include_all,
        type=cast(TaskType, type_) if type_ else None,
        priority=cast(Priority, priority) if priority else None,
        labels=labels,
        parent_id=parent.id if parent else None,
        blocks_id=blocks.id if blocks else None,
        blocked_by_id=blocked_by.id if blocked_by else None,
        relates_to_id=relates_to.id if relates_to else None,
        claimed_by=claimed_by,
        unclaimed=unclaimed,
        assigned_to=assigned_to,
        stale_before=stale_before,
        updated_since=updated_since,
        # --limit applies after the merge, never per scope.
    )

    def fetch(conn: sqlite3.Connection, s: Scope) -> Sequence[TaskRow]:
        # A --parent/--blocks/--blocked-by/--relates-to ref is scoped to the
        # database it was parsed from; a cross-scope parent_of/blocks/relates_to
        # link is impossible (guards/scope.py:assert_same_scope), so querying a
        # scope other than the ref's own can only ever mean zero rows. Skipping
        # it here is what keeps the bare int id from spuriously matching an
        # unrelated task that happens to share the same id in the other scope's
        # independent id sequence (§3.3/§4.2).
        if any(ref_scope != s for ref_scope in ref_scopes):
            return []
        return list_tasks(conn, filt, scope=s)

    tasks = sort_tasks(fetch_merged(cast(ScopeFilter, scope_filter), fetch))
    if after_ref is not None:
        tasks = paginate_after(tasks, resolve_cursor(after_ref))
    if limit is not None:
        tasks = tasks[:limit]
    emit_tasks([t.to_dict() for t in tasks], as_json=as_json, fields=fields)
