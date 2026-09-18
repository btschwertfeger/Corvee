#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

from corvee.cli.context import corvee_context
from corvee.config import global_db_path, project_exists
from corvee.constants import PRIORITY_ORDER, Scope, ScopeFilter
from corvee.db.tasks import require_task
from corvee.models import FactRow, TaskRow, parse_task_ref

T = TypeVar("T")


def scopes_for(
    scope_filter: ScopeFilter, *, local_available: bool | None = None
) -> tuple[Scope, ...]:
    """Which scopes `--scope <filter>` queries.

    The global database is only ever included once it already exists —
    `--scope all` (the default) and `--scope global` both silently skip it
    if `~/.corvee/corvee.db` is missing, rather than creating it as a side
    effect of a read. The local project gets the same treatment under
    `--scope all`: a missing `.corvee/config.toml` drops out of the merge
    silently rather than raising, so a purely-global call works from any
    directory. `--scope local`, requested explicitly, keeps failing loudly —
    that's a real usage error, not "just show me global" — but not *here*:
    this function still returns `("local",)` unconditionally and leaves the
    actual failure to whichever `corvee_context` call opens that database,
    the CLI's existing lazy-fail behavior.

    `local_available`, given, is used verbatim under `--scope all` instead
    of the ambient, cwd-based `project_exists()` check — the MCP surface's
    own entry point (`mcp/scope.py::scopes_for_config`) passes its already
    -resolved `ServerConfig.project is not None` here, since a worker
    thread has no meaningful cwd of its own to re-derive from (spec
    §10.1). Omitted (`None`, the CLI's own call), this checks ambiently,
    unchanged from before this parameter existed.
    """
    if scope_filter == "local":
        return ("local",)
    global_exists = global_db_path().is_file()
    if scope_filter == "global":
        return ("global",) if global_exists else ()
    scopes: list[Scope] = []
    has_local = project_exists() if local_available is None else local_available
    if has_local:
        scopes.append("local")
    if global_exists:
        scopes.append("global")
    return tuple(scopes)


def fetch_merged(
    scope_filter: ScopeFilter,
    fetch: Callable[[sqlite3.Connection, Scope], Sequence[T]],
    *,
    actor: str | None = None,
    project_db_path: Path | None = None,
    local_available: bool | None = None,
) -> list[T]:
    """Run `fetch` against every scope `--scope <filter>` selects and concatenate.

    Each scope is its own connection and transaction — never a
    cross-database transaction. Callers own sorting and `--limit`, applied
    *after* this merge, never per scope: asking each database for
    `--limit` rows first could drop a row that belonged in the merged top
    `n` merely because it came from whichever database was queried second.

    `actor`/`project_db_path`/`local_available`, given, thread straight
    through to `corvee_context`/`scopes_for` instead of the CLI's own
    ambient defaults (click's context, cwd) — the MCP surface's own entry
    point (`mcp/scope.py::fetch_merged_for_config`) passes all three from
    its already-resolved `ServerConfig`, for the same worker-thread reason
    `scopes_for` documents. `project_db_path` only ever applies to the
    `"local"` scope in one merge — a `"global"` connection never takes it.
    It is `corvee_context`'s own same-named override: the already-resolved
    project's db path used verbatim, skipping a fresh `resolve_project`
    per scope (TASK-37).
    """
    results: list[T] = []
    for scope in scopes_for(scope_filter, local_available=local_available):
        with corvee_context(
            write=False,
            scope=scope,
            actor=actor,
            project_db_path=project_db_path if scope == "local" else None,
        ) as ctx:
            results.extend(fetch(ctx.conn, scope))
    return results


def sort_tasks(tasks: list[TaskRow]) -> list[TaskRow]:
    """The task order (priority desc, created_at desc, id desc), safe across a
    local/global merge where `id` alone is not comparable.

    Three stable passes, least significant key first, rather than one
    composite key — `id`/`created_at` sort naturally descending, but
    priority must sort *ascending* on `PRIORITY_ORDER` (0 is "critical") to
    land in priority-descending order, and Python's sort has no per-key
    direction within a single tuple key.
    """
    tasks.sort(key=lambda t: t.id, reverse=True)
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    tasks.sort(key=lambda t: PRIORITY_ORDER[t.priority])
    return tasks


def sort_facts(facts: list[FactRow]) -> list[FactRow]:
    """The fact order (created_at desc, id desc), safe across a local/global
    merge the same way `sort_tasks` is.
    """
    facts.sort(key=lambda f: f.id, reverse=True)
    facts.sort(key=lambda f: f.created_at, reverse=True)
    return facts


def paginate_after(tasks: list[TaskRow], cursor: TaskRow) -> list[TaskRow]:
    """Drop every task at or before `cursor`'s position in the fixed task
    order (priority desc, created_at desc, id desc), the keyset-pagination
    counterpart to `--limit` for paging through a large, `--scope all`-merged
    backlog: an offset alone is meaningless once results interleave two
    independent id sequences (§3.3), but this order's own key compares fine
    across them (§5.1.1). `cursor` does not need to appear in `tasks` itself
    (it may not satisfy the same filters) — only its priority/created_at/id
    place it in the order.
    """

    def _after(task: TaskRow) -> bool:
        task_rank = PRIORITY_ORDER[task.priority]
        cursor_rank = PRIORITY_ORDER[cursor.priority]
        if task_rank != cursor_rank:
            return task_rank > cursor_rank
        if task.created_at != cursor.created_at:
            return task.created_at < cursor.created_at
        return task.id < cursor.id

    return [task for task in tasks if _after(task)]


def resolve_cursor(after_ref: str) -> TaskRow:
    """The `--after <ref>` task, fetched from its own database regardless of
    the current `--scope` filter — a global cursor still orders a merged
    `--scope all` query correctly (§5.1.1), since `created_at` is comparable
    across scopes even though `id` alone is not.
    """
    ref = parse_task_ref(after_ref)
    with corvee_context(write=False, scope=ref.scope) as ctx:
        return require_task(ctx.conn, ref.id, scope=ref.scope)
