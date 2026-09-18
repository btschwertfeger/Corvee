#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3

from corvee.db.events import record_field_change


def _get_or_create_label(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM labels WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return int(row[0])
    cursor = conn.execute("INSERT INTO labels (name) VALUES (?)", (name,))
    if cursor.lastrowid is None:
        raise RuntimeError("INSERT into labels did not produce a rowid")
    return cursor.lastrowid


def add_label(
    conn: sqlite3.Connection,
    task_id: int,
    name: str,
    actor: str,
    session_id: str | None,
) -> None:
    """Attach `name` to `task_id`. A no-op success if already attached."""
    label_id = _get_or_create_label(conn, name)
    existing = conn.execute(
        "SELECT 1 FROM task_labels WHERE task_id = ? AND label_id = ?",
        (task_id, label_id),
    ).fetchone()
    if existing is not None:
        return
    conn.execute("INSERT INTO task_labels (task_id, label_id) VALUES (?, ?)", (task_id, label_id))
    record_field_change(
        conn,
        task_id=task_id,
        field="label",
        old_value=None,
        new_value=name,
        actor=actor,
        session_id=session_id,
    )


def remove_label(
    conn: sqlite3.Connection,
    task_id: int,
    name: str,
    actor: str,
    session_id: str | None,
) -> None:
    """Detach `name` from `task_id`. A no-op success if not attached."""
    row = conn.execute("SELECT id FROM labels WHERE name = ?", (name,)).fetchone()
    if row is None:
        return
    cursor = conn.execute(
        "DELETE FROM task_labels WHERE task_id = ? AND label_id = ?",
        (task_id, row[0]),
    )
    if cursor.rowcount == 0:
        return
    record_field_change(
        conn,
        task_id=task_id,
        field="label",
        old_value=name,
        new_value=None,
        actor=actor,
        session_id=session_id,
    )


def list_task_labels(conn: sqlite3.Connection, task_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT l.name FROM task_labels tl"
        " JOIN labels l ON l.id = tl.label_id"
        " WHERE tl.task_id = ? ORDER BY l.name",
        (task_id,),
    ).fetchall()
    return [row[0] for row in rows]


def list_labels_with_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT l.name, COUNT(tl.task_id) FROM labels l"
        " LEFT JOIN task_labels tl ON tl.label_id = l.id"
        " GROUP BY l.id ORDER BY l.name",
    ).fetchall()
    return [(row[0], row[1]) for row in rows]
