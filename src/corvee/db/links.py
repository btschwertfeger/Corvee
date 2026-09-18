#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Callable

from corvee.constants import TERMINAL_STATES, Relation
from corvee.db.events import record_field_change
from corvee.db.tasks import require_task
from corvee.errors import GuardViolationError
from corvee.guards.ancestry import creates_cycle
from corvee.models import task_ref


def _adjacency(conn: sqlite3.Connection, relation: Relation) -> Callable[[int], list[int]]:
    def fn(node: int) -> list[int]:
        rows = conn.execute(
            "SELECT target_id FROM task_links WHERE source_id = ? AND relation = ?",
            (node, relation),
        ).fetchall()
        return [row[0] for row in rows]

    return fn


def link_tasks(
    conn: sqlite3.Connection,
    source_id: int,
    target_id: int,
    relation: Relation,
    actor: str,
    session_id: str | None,
) -> dict[int, str]:
    """Link two tasks. Returns {task_id: warning} for advisory oddities (never raised).

    Currently the only such oddity: attaching a non-terminal child to an
    already-`done` parent via `parent_of` — allowed (the parent isn't
    retroactively invalidated), but worth surfacing on the parent's output.
    """
    source_task = require_task(conn, source_id)
    target_task = require_task(conn, target_id)

    if relation == "relates_to" and source_id > target_id:
        # Symmetric: stored normalized so `link A B` and `link B A` collapse
        # to one row.
        source_id, target_id = target_id, source_id

    if relation in ("parent_of", "blocks") and creates_cycle(
        _adjacency(conn, relation), source_id, target_id
    ):
        raise GuardViolationError(
            "link_cycle",
            f"linking {task_ref(source_id)} -> {task_ref(target_id)}"
            f" ({relation}) would create a cycle",
            source_id=task_ref(source_id),
            target_id=task_ref(target_id),
            relation=relation,
        )

    if relation == "parent_of":
        existing_parent = conn.execute(
            "SELECT source_id FROM task_links WHERE target_id = ? AND relation = 'parent_of'",
            (target_id,),
        ).fetchone()
        if existing_parent is not None and existing_parent[0] != source_id:
            raise GuardViolationError(
                "already_has_parent",
                f"{task_ref(target_id)} already has a parent: "
                f"{task_ref(existing_parent[0])}; use `corvee task unlink` first",
                task_id=task_ref(target_id),
                current_parent=task_ref(existing_parent[0]),
            )

    existing = conn.execute(
        "SELECT 1 FROM task_links WHERE source_id = ? AND target_id = ? AND relation = ?",
        (source_id, target_id, relation),
    ).fetchone()
    if existing is not None:
        return {}

    conn.execute(
        "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, ?)",
        (source_id, target_id, relation),
    )
    record_field_change(
        conn,
        task_id=source_id,
        field=f"link:{relation}",
        old_value=None,
        new_value=task_ref(target_id),
        actor=actor,
        session_id=session_id,
    )
    record_field_change(
        conn,
        task_id=target_id,
        field=f"link:{relation}",
        old_value=None,
        new_value=task_ref(source_id),
        actor=actor,
        session_id=session_id,
    )

    if (
        relation == "parent_of"
        and source_task.state == "done"
        and target_task.state not in TERMINAL_STATES
    ):
        return {source_id: f"child {task_ref(target_id)} is open while this parent is done"}
    return {}


def unlink_tasks(
    conn: sqlite3.Connection,
    source_id: int,
    target_id: int,
    relation: Relation,
    actor: str,
    session_id: str | None,
) -> None:
    require_task(conn, source_id)
    require_task(conn, target_id)
    if relation == "relates_to" and source_id > target_id:
        source_id, target_id = target_id, source_id

    cursor = conn.execute(
        "DELETE FROM task_links WHERE source_id = ? AND target_id = ? AND relation = ?",
        (source_id, target_id, relation),
    )
    if cursor.rowcount == 0:
        return

    record_field_change(
        conn,
        task_id=source_id,
        field=f"link:{relation}",
        old_value=task_ref(target_id),
        new_value=None,
        actor=actor,
        session_id=session_id,
    )
    record_field_change(
        conn,
        task_id=target_id,
        field=f"link:{relation}",
        old_value=task_ref(source_id),
        new_value=None,
        actor=actor,
        session_id=session_id,
    )


def get_task_links(conn: sqlite3.Connection, task_id: int) -> list[dict[str, str]]:
    """Every link touching `task_id`, from either end (for `corvee show`)."""
    rows = conn.execute(
        "SELECT source_id, target_id, relation FROM task_links"
        " WHERE source_id = ? OR target_id = ?",
        (task_id, task_id),
    ).fetchall()
    results = []
    for row in rows:
        is_source = row["source_id"] == task_id
        other = row["target_id"] if is_source else row["source_id"]
        results.append(
            {
                "relation": row["relation"],
                "task_id": task_ref(other),
                "direction": "outgoing" if is_source else "incoming",
            },
        )
    return results


def get_children(conn: sqlite3.Connection, task_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT target_id FROM task_links WHERE source_id = ? AND relation = 'parent_of'",
        (task_id,),
    ).fetchall()
    return [row[0] for row in rows]
