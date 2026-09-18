#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from corvee.actor import resolve_actor
from corvee.cli.context import corvee_context
from corvee.cli.scope import fetch_merged, sort_tasks
from corvee.config import project_exists
from corvee.constants import (
    DEFAULT_STALE_DURATION,
    LIST_TABLE_DEFAULT_FIELDS,
    SCOPE_FILTERS,
    Scope,
    ScopeFilter,
    narrow_scope_filter,
)
from corvee.db.events import get_last_comment
from corvee.db.labels import list_labels_with_counts
from corvee.db.tasks import TaskFilter, TaskRow, list_tasks, mine_tasks, ready_tasks
from corvee.output import render_table
from corvee.timeutil import parse_duration, timestamp

READY_LIMIT = 5

EPILOG = """\
\b
Examples:
Reorient at the start of a session in one call:
  corvee brief
Get the same snapshot as machine-readable output:
  corvee brief --json
See the machine-wide backlog alongside this project's:
  corvee brief --scope all --json
Check only what's filed in the shared global database:
  corvee brief --scope global --json
"""


def mine_section(
    scope_filter: ScopeFilter,
    *,
    actor: str | None = None,
    project_db_path: Path | None = None,
    local_available: bool | None = None,
) -> list[dict[str, Any]]:
    """Open tasks claimed by (or assigned and unclaimed to) `actor`, each
    with its last comment. `actor`, omitted, resolves ambiently
    (`resolve_actor()`, the CLI's own `$CORVEE_ACTOR`/`--actor`); the MCP
    surface passes its already-resolved `ServerConfig.actor` instead
    (spec §10.1). `project_db_path`/`local_available`, given, thread
    through to `fetch_merged` the same way -- `project_db_path` is the MCP
    surface's own already-resolved project db path, used verbatim instead
    of a fresh `resolve_project` per call (TASK-37).
    """
    resolved_actor = actor or resolve_actor()

    def fetch(conn: sqlite3.Connection, s: Scope) -> list[tuple[TaskRow, dict[str, Any] | None]]:
        tasks = mine_tasks(conn, resolved_actor, scope=s)
        return [(task, get_last_comment(conn, task.id)) for task in tasks]

    pairs = fetch_merged(
        scope_filter,
        fetch,
        actor=resolved_actor,
        project_db_path=project_db_path,
        local_available=local_available,
    )
    pairs.sort(key=lambda p: p[0].id, reverse=True)
    pairs.sort(key=lambda p: p[0].claimed_at or "", reverse=True)
    results = []
    for task, last_comment in pairs:
        detail = task.to_dict()
        detail["last_comment"] = last_comment
        results.append(detail)
    return results


def ready_section(
    scope_filter: ScopeFilter,
    *,
    actor: str | None = None,
    project_db_path: Path | None = None,
    local_available: bool | None = None,
) -> list[dict[str, Any]]:
    """Up to `READY_LIMIT` unclaimed, open, unblocked tasks. See
    `mine_section` for the `actor`/`project_db_path`/`local_available`
    parameters.
    """
    tasks = sort_tasks(
        fetch_merged(
            scope_filter,
            lambda conn, s: ready_tasks(conn, scope=s),
            actor=actor,
            project_db_path=project_db_path,
            local_available=local_available,
        )
    )
    return [t.to_dict() for t in tasks[:READY_LIMIT]]


def stale_section(
    scope_filter: ScopeFilter,
    *,
    actor: str | None = None,
    project_db_path: Path | None = None,
    local_available: bool | None = None,
) -> list[dict[str, Any]]:
    """Tasks whose claim has gone stale. See `mine_section` for the
    `actor`/`project_db_path`/`local_available` parameters.
    """
    cutoff = timestamp(datetime.now(UTC) - parse_duration(DEFAULT_STALE_DURATION))
    filt = TaskFilter(stale_before=cutoff)
    tasks = sort_tasks(
        fetch_merged(
            scope_filter,
            lambda conn, s: list_tasks(conn, filt, scope=s),
            actor=actor,
            project_db_path=project_db_path,
            local_available=local_available,
        )
    )
    return [t.to_dict() for t in tasks]


def labels_section(
    *,
    actor: str | None = None,
    project_db_path: Path | None = None,
    has_project: bool | None = None,
) -> list[dict[str, Any]]:
    """The local project's label vocabulary — never merged across scope,
    the same restriction `task labels` already has (§3.3).

    Empty, not an error, when no local project resolves — `brief`'s other
    three sections already degrade the same way for a purely-global call
    (§3.3), and `labels` is an auxiliary section of that same call, not a
    separate ask for local data the way standalone `task labels` is.
    `has_project`, given, is used verbatim instead of the ambient
    `project_exists()` check, the same override `mine_section` and its
    siblings take as `local_available`. `project_db_path`, given, is
    `corvee_context`'s own override, same as its sibling sections.
    """
    available = project_exists() if has_project is None else has_project
    if not available:
        return []
    with corvee_context(write=False, actor=actor, project_db_path=project_db_path) as ctx:
        rows = list_labels_with_counts(ctx.conn)
    return [{"name": name, "task_count": count} for name, count in rows]


@click.command(epilog=EPILOG)
@click.option("--scope", "-s", "scope_filter", type=click.Choice(SCOPE_FILTERS), default="all")
@click.option("--json", "-j", "as_json", is_flag=True)
def brief(scope_filter: str, as_json: bool) -> None:
    """Session-start snapshot: what's claimed, what's ready, what's gone stale.

    Combines `task mine`, `task ready` and `task list --stale` into one
    read-only call.
    """
    scope = narrow_scope_filter(scope_filter)
    sections = {
        "mine": mine_section(scope),
        "ready": ready_section(scope),
        "stale": stale_section(scope),
        "labels": labels_section(),
    }
    if as_json:
        click.echo(json.dumps(sections))
        return
    blocks = [
        f"{name}:\n{render_table(rows, default_fields=LIST_TABLE_DEFAULT_FIELDS)}"
        for name, rows in sections.items()
        if name != "labels" and rows
    ]
    if sections["labels"]:
        blocks.append(f"labels:\n{render_table(sections['labels'], fields=('name', 'task_count'))}")
    click.echo("\n\n".join(blocks))
