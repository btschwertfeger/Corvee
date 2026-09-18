#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from typing import Any

from corvee.timeutil import timestamp


def record_field_change(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    field: str,
    old_value: str | None,
    new_value: str | None,
    actor: str,
    session_id: str | None,
) -> None:
    """Write a field_change event and advance tasks.updated_at together."""
    now = timestamp()
    conn.execute(
        "INSERT INTO task_events"
        " (task_id, kind, field, old_value, new_value, body, actor, session_id, created_at)"
        " VALUES (?, 'field_change', ?, ?, ?, NULL, ?, ?, ?)",
        (task_id, field, old_value, new_value, actor, session_id, now),
    )
    conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (now, task_id))


def record_comment(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    body: str,
    actor: str,
    session_id: str | None,
) -> None:
    now = timestamp()
    conn.execute(
        "INSERT INTO task_events"
        " (task_id, kind, field, old_value, new_value, body, actor, session_id, created_at)"
        " VALUES (?, 'comment', NULL, NULL, NULL, ?, ?, ?, ?)",
        (task_id, body, actor, session_id, now),
    )
    conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (now, task_id))


def record_created(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    title: str,
    actor: str,
    session_id: str | None,
) -> None:
    """Write the task's own `created` event -- the task equivalent of
    `record_fact_event`'s `kind="created"` case, which facts have always
    gotten but tasks did not until now (TASK-29).
    """
    now = timestamp()
    conn.execute(
        "INSERT INTO task_events"
        " (task_id, kind, field, old_value, new_value, body, actor, session_id, created_at)"
        " VALUES (?, 'created', NULL, NULL, ?, NULL, ?, ?, ?)",
        (task_id, title, actor, session_id, now),
    )
    conn.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (now, task_id))


def get_last_comment(conn: sqlite3.Connection, task_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT body, actor, session_id, created_at FROM task_events"
        " WHERE task_id = ? AND kind = 'comment' ORDER BY created_at DESC, id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_task_events(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    since: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """The merged, time-ordered event timeline for a task.

    Returns (kept_events, omitted_count) so a trimmed response can always
    report how many events were left out rather than silently truncating.
    """
    rows = conn.execute(
        "SELECT kind, field, old_value, new_value, body, actor, session_id, created_at"
        " FROM task_events WHERE task_id = ? ORDER BY created_at ASC, id ASC",
        (task_id,),
    ).fetchall()
    events = [dict(row) for row in rows]
    if since is None:
        return events, 0
    kept = [event for event in events if event["created_at"] >= since]
    return kept, len(events) - len(kept)


def record_fact_event(
    conn: sqlite3.Connection,
    *,
    fact_id: int,
    kind: str,
    old_value: str | None = None,
    new_value: str | None = None,
    proof: str | None = None,
    note: str | None = None,
    actor: str,
    session_id: str | None,
) -> None:
    """Write a fact_events row and advance facts.updated_at together."""
    now = timestamp()
    conn.execute(
        "INSERT INTO fact_events"
        " (fact_id, kind, old_value, new_value, proof, note, actor, session_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (fact_id, kind, old_value, new_value, proof, note, actor, session_id, now),
    )
    conn.execute("UPDATE facts SET updated_at = ? WHERE id = ?", (now, fact_id))


def get_fact_events(conn: sqlite3.Connection, fact_id: int) -> list[dict[str, Any]]:
    """The full revision timeline for a fact, oldest first.

    Unlike task_events, this has no `since`/omitted-count trimming — a
    fact's history is small by construction (one row per lifecycle action),
    so `fact show` always returns it in full.
    """
    rows = conn.execute(
        "SELECT kind, old_value, new_value, proof, note, actor, session_id, created_at"
        " FROM fact_events WHERE fact_id = ? ORDER BY created_at ASC, id ASC",
        (fact_id,),
    ).fetchall()
    return [dict(row) for row in rows]
