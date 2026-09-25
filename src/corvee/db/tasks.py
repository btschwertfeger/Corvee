#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from corvee.constants import (
    DEFAULT_PRIORITY,
    DEFAULT_STATE,
    DEFAULT_TASK_TYPE,
    OPEN_STATES,
    TERMINAL_STATES,
    Priority,
    Scope,
    State,
    TaskType,
    narrow_state,
)
from corvee.db.events import record_comment, record_created, record_field_change
from corvee.db.like import escape_like
from corvee.errors import ClaimConflictError, GuardViolationError, NotFoundError
from corvee.guards.parent_child import assert_no_open_children
from corvee.guards.transitions import validate_transition
from corvee.models import TaskRow, task_ref
from corvee.timeutil import timestamp

# Priority descending, then id descending (newest first) — the fixed total order.
_ORDER_BY = """
ORDER BY CASE priority
    WHEN 'critical' THEN 0
    WHEN 'high' THEN 1
    WHEN 'medium' THEN 2
    WHEN 'low' THEN 3
    ELSE 4
END, created_at DESC, id DESC
"""


def insert_task(
    conn: sqlite3.Connection,
    *,
    title: str,
    description: str = "",
    type_: TaskType = DEFAULT_TASK_TYPE,
    priority: Priority = DEFAULT_PRIORITY,
    scope: Scope = "local",
    actor: str | None = None,
    session_id: str | None = None,
) -> TaskRow:
    """`actor`, given, records a `created` event the same way `insert_fact`
    always does (TASK-29) -- optional, unlike `insert_fact`'s required
    `actor`, only so the ~200 existing test call sites that create a task
    without caring about attribution stay unaffected; every production
    caller (the CLI's own `task add`, the MCP `task_add` tool) passes it.
    """
    now = timestamp()
    cursor = conn.execute(
        "INSERT INTO tasks (title, description, type, priority, state, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, description, type_, priority, DEFAULT_STATE, now, now),
    )
    task_id = cursor.lastrowid
    if task_id is None:
        raise RuntimeError("INSERT into tasks did not produce a rowid")
    if actor is not None:
        record_created(conn, task_id=task_id, title=title, actor=actor, session_id=session_id)
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return TaskRow.from_row(row, scope=scope)


def get_task(conn: sqlite3.Connection, task_id: int, *, scope: Scope = "local") -> TaskRow | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return TaskRow.from_row(row, scope=scope) if row else None


def require_task(conn: sqlite3.Connection, task_id: int, *, scope: Scope = "local") -> TaskRow:
    task = get_task(conn, task_id, scope=scope)
    if task is None:
        raise NotFoundError(
            "task_not_found",
            f"no such task: {task_ref(task_id, scope)}",
            task_id=task_ref(task_id, scope),
        )
    return task


def require_tasks(
    conn: sqlite3.Connection, task_ids: Sequence[int], *, scope: Scope = "local"
) -> list[TaskRow]:
    """Fetch tasks in the given id order (`show`'s ordering rule)."""
    return [require_task(conn, task_id, scope=scope) for task_id in task_ids]


@dataclass(frozen=True)
class TaskFilter:
    states: Sequence[State] | None = None
    include_all: bool = False
    type: TaskType | None = None
    priority: Priority | None = None
    labels: Sequence[str] = ()
    parent_id: int | None = None
    blocks_id: int | None = None
    blocked_by_id: int | None = None
    relates_to_id: int | None = None
    claimed_by: str | None = None
    unclaimed: bool = False
    assigned_to: str | None = None
    stale_before: str | None = None
    updated_since: str | None = None
    limit: int | None = None


def list_tasks(
    conn: sqlite3.Connection, filt: TaskFilter, *, scope: Scope = "local"
) -> list[TaskRow]:
    conditions: list[str] = []
    params: list[Any] = []

    if filt.states is not None:
        conditions.append(f"state IN ({','.join('?' for _ in filt.states)})")
        params.extend(filt.states)
    elif not filt.include_all:
        # "Open" is any state other than done/cancelled — the default filter.
        conditions.append(f"state IN ({','.join('?' for _ in OPEN_STATES)})")
        params.extend(OPEN_STATES)

    if filt.type is not None:
        conditions.append("type = ?")
        params.append(filt.type)
    if filt.priority is not None:
        conditions.append("priority = ?")
        params.append(filt.priority)
    if filt.claimed_by is not None:
        conditions.append("claimed_by = ?")
        params.append(filt.claimed_by)
    if filt.unclaimed:
        conditions.append("claimed_by IS NULL")
    if filt.assigned_to is not None:
        conditions.append("assigned_to = ?")
        params.append(filt.assigned_to)
    if filt.stale_before is not None:
        conditions.append("claimed_at IS NOT NULL AND claimed_at < ?")
        params.append(filt.stale_before)
    if filt.updated_since is not None:
        conditions.append("updated_at >= ?")
        params.append(filt.updated_since)
    if filt.parent_id is not None:
        # --parent matches direct children only.
        conditions.append(
            "id IN (SELECT target_id FROM task_links"
            " WHERE source_id = ? AND relation = 'parent_of')",
        )
        params.append(filt.parent_id)
    if filt.blocks_id is not None:
        # --blocks <id>: tasks that <id> blocks (id is the source of the blocks edge).
        conditions.append(
            "id IN (SELECT target_id FROM task_links"
            " WHERE source_id = ? AND relation = 'blocks')",
        )
        params.append(filt.blocks_id)
    if filt.blocked_by_id is not None:
        # --blocked-by <id>: tasks that block <id> (id is the target of the blocks edge).
        conditions.append(
            "id IN (SELECT source_id FROM task_links"
            " WHERE target_id = ? AND relation = 'blocks')",
        )
        params.append(filt.blocked_by_id)
    if filt.relates_to_id is not None:
        # relates_to is symmetric and normalized to source_id < target_id (§4.3),
        # so <id> can appear on either side of the stored row.
        conditions.append(
            "id IN (SELECT target_id FROM task_links"
            " WHERE source_id = ? AND relation = 'relates_to'"
            " UNION SELECT source_id FROM task_links"
            " WHERE target_id = ? AND relation = 'relates_to')",
        )
        params.extend([filt.relates_to_id, filt.relates_to_id])
    for label in filt.labels:
        # Repeating --label is AND, not OR — one condition per label.
        conditions.append(
            "id IN (SELECT tl.task_id FROM task_labels tl"
            " JOIN labels l ON l.id = tl.label_id WHERE l.name = ?)",
        )
        params.append(label)

    sql = "SELECT * FROM tasks"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += _ORDER_BY
    if filt.limit is not None:
        sql += " LIMIT ?"
        params.append(filt.limit)

    rows = conn.execute(sql, params).fetchall()
    return [TaskRow.from_row(row, scope=scope) for row in rows]


def _claim_conflict(task_id: int, claimed_by: str, scope: Scope) -> ClaimConflictError:
    return ClaimConflictError(
        "claim_conflict",
        f"{task_ref(task_id, scope)} is claimed by {claimed_by}; use --force to steal the claim",
        claimed_by=claimed_by,
        task_id=task_ref(task_id, scope),
    )


def claim_task(
    conn: sqlite3.Connection,
    task_id: int,
    actor: str,
    *,
    force: bool = False,
    session_id: str | None = None,
    scope: Scope = "local",
) -> TaskRow:
    """Atomically claim `task_id` for `actor`, or refresh a claim already held."""
    task = require_task(conn, task_id, scope=scope)
    if task.state in TERMINAL_STATES:
        raise GuardViolationError(
            "task_terminal",
            f"{task_ref(task_id, scope)} is {task.state}; a finished task cannot be claimed",
            task_id=task_ref(task_id, scope),
            state=task.state,
        )
    now = timestamp()

    if task.claimed_by is None:
        cursor = conn.execute(
            "UPDATE tasks SET claimed_by = ?, claimed_at = ? WHERE id = ? AND claimed_by IS NULL",
            (actor, now, task_id),
        )
        if cursor.rowcount == 1:
            record_field_change(
                conn,
                task_id=task_id,
                field="claimed_by",
                old_value=None,
                new_value=actor,
                actor=actor,
                session_id=session_id,
            )
            return require_task(conn, task_id, scope=scope)
        # Someone else claimed it between the read above and this UPDATE; the
        # conditional UPDATE is the actual concurrency-safety mechanism — re-fetch
        # and fall through to the "already claimed" handling below.
        task = require_task(conn, task_id, scope=scope)

    if task.claimed_by == actor:
        # Repeat claim by the current claimant: the explicit heartbeat.
        conn.execute("UPDATE tasks SET claimed_at = ? WHERE id = ?", (now, task_id))
        record_field_change(
            conn,
            task_id=task_id,
            field="claimed_at",
            old_value=task.claimed_at,
            new_value=now,
            actor=actor,
            session_id=session_id,
        )
        return require_task(conn, task_id, scope=scope)

    if task.claimed_by is None:
        raise RuntimeError("claimed_by became None unexpectedly mid-claim")
    if not force:
        raise _claim_conflict(task_id, task.claimed_by, scope)

    previous = task.claimed_by
    conn.execute(
        "UPDATE tasks SET claimed_by = ?, claimed_at = ? WHERE id = ?", (actor, now, task_id)
    )
    record_field_change(
        conn,
        task_id=task_id,
        field="claimed_by",
        old_value=previous,
        new_value=actor,
        actor=actor,
        session_id=session_id,
    )
    return require_task(conn, task_id, scope=scope)


def unclaim_task(
    conn: sqlite3.Connection,
    task_id: int,
    actor: str,
    *,
    force: bool = False,
    session_id: str | None = None,
    scope: Scope = "local",
) -> TaskRow:
    """Release a claim. A no-op success if already unclaimed."""
    task = require_task(conn, task_id, scope=scope)
    if task.claimed_by is None:
        return task
    if task.claimed_by != actor and not force:
        raise _claim_conflict(task_id, task.claimed_by, scope)

    previous = task.claimed_by
    conn.execute("UPDATE tasks SET claimed_by = NULL, claimed_at = NULL WHERE id = ?", (task_id,))
    record_field_change(
        conn,
        task_id=task_id,
        field="claimed_by",
        old_value=previous,
        new_value=None,
        actor=actor,
        session_id=session_id,
    )
    return require_task(conn, task_id, scope=scope)


def assign_task(
    conn: sqlite3.Connection,
    task_id: int,
    target: str,
    actor: str,
    *,
    session_id: str | None = None,
    scope: Scope = "local",
) -> TaskRow:
    """Route `task_id` to `target`, advisory only: not claim-gated, and does
    not itself claim the task (§4.4). A no-op if already assigned to `target`.
    """
    task = require_task(conn, task_id, scope=scope)
    if task.assigned_to == target:
        return task
    conn.execute("UPDATE tasks SET assigned_to = ? WHERE id = ?", (target, task_id))
    record_field_change(
        conn,
        task_id=task_id,
        field="assigned_to",
        old_value=task.assigned_to,
        new_value=target,
        actor=actor,
        session_id=session_id,
    )
    return require_task(conn, task_id, scope=scope)


def unassign_task(
    conn: sqlite3.Connection,
    task_id: int,
    actor: str,
    *,
    session_id: str | None = None,
    scope: Scope = "local",
) -> TaskRow:
    """Clear `task_id`'s assignment. A no-op success if already unassigned."""
    task = require_task(conn, task_id, scope=scope)
    if task.assigned_to is None:
        return task
    conn.execute("UPDATE tasks SET assigned_to = NULL WHERE id = ?", (task_id,))
    record_field_change(
        conn,
        task_id=task_id,
        field="assigned_to",
        old_value=task.assigned_to,
        new_value=None,
        actor=actor,
        session_id=session_id,
    )
    return require_task(conn, task_id, scope=scope)


def purge_task(conn: sqlite3.Connection, task_id: int, *, scope: Scope = "local") -> TaskRow:
    """Permanently remove a cancelled, unlinked task and its entire task_events
    history: the task analogue of `fact delete` (§4.6), and the one exception
    to "no delete" for tasks (§2).

    Only works when the task's current state is 'cancelled' and it carries no
    `task_links` in either direction. Cancel is always the reversible first
    step, and refusing while a link exists means removing this row never
    silently orphans a parent/child/blocks/relates_to reference on the other
    end. Returns the task's last state, since no row is left to describe
    after this call.
    """
    task = require_task(conn, task_id, scope=scope)
    if task.state != "cancelled":
        raise GuardViolationError(
            "task_not_cancelled",
            f"{task_ref(task_id, scope)} is not cancelled; run"
            " `corvee task update --state cancelled` first",
            task_id=task_ref(task_id, scope),
            state=task.state,
        )
    linked = conn.execute(
        "SELECT 1 FROM task_links WHERE source_id = ? OR target_id = ?", (task_id, task_id)
    ).fetchone()
    if linked is not None:
        raise GuardViolationError(
            "task_has_links",
            f"{task_ref(task_id, scope)} still has links; run `corvee task unlink` first",
            task_id=task_ref(task_id, scope),
        )
    conn.execute("DELETE FROM task_labels WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM task_events WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return task


def _open_children(conn: sqlite3.Connection, task_id: int) -> list[tuple[int, State]]:
    rows = conn.execute(
        "SELECT t.id, t.state FROM task_links l JOIN tasks t ON t.id = l.target_id"
        " WHERE l.source_id = ? AND l.relation = 'parent_of'",
        (task_id,),
    ).fetchall()
    return [(row[0], narrow_state(row[1])) for row in rows]


def _parent(conn: sqlite3.Connection, task_id: int) -> tuple[int, State] | None:
    """The direct `parent_of` parent of `task_id`, as (id, state), or None."""
    row = conn.execute(
        "SELECT t.id, t.state FROM task_links l JOIN tasks t ON t.id = l.source_id"
        " WHERE l.target_id = ? AND l.relation = 'parent_of'",
        (task_id,),
    ).fetchone()
    return (row[0], narrow_state(row[1])) if row is not None else None


def cascade_cancel_descendants(
    conn: sqlite3.Connection,
    task_id: int,
    actor: str,
    session_id: str | None,
    *,
    force: bool = False,
    scope: Scope = "local",
) -> list[int]:
    """Cancel every non-done/cancelled descendant of `task_id` (--cascade).

    Walks the whole subtree regardless of intermediate done nodes — a
    finished piece of work under an abandoned effort still needs its own
    open siblings/children reached and cancelled. A descendant actively
    claimed by another actor blocks the cascade the same way a claim
    conflict on the named task does, unless `force` is set: --cascade
    authorizes touching unclaimed descendants structurally, not stealing a
    live foreign claim.

    Tracks a `visited` set, the same pattern `guards/ancestry.py:is_reachable`
    uses, so a `parent_of` cycle already present in the data (corvee's own
    insert-time cycle guard normally prevents this, but a hand-edited
    database is not bound by it) terminates the walk instead of hanging it.
    """
    touched: list[int] = []
    visited: set[int] = set()
    stack = [
        row[0]
        for row in conn.execute(
            "SELECT target_id FROM task_links WHERE source_id = ? AND relation = 'parent_of'",
            (task_id,),
        ).fetchall()
    ]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        row = conn.execute(
            "SELECT state, claimed_by FROM tasks WHERE id = ?", (current,)
        ).fetchone()
        if row["state"] not in TERMINAL_STATES:
            if row["claimed_by"] is not None and row["claimed_by"] != actor and not force:
                raise _claim_conflict(current, row["claimed_by"], scope)
            conn.execute("UPDATE tasks SET state = 'cancelled' WHERE id = ?", (current,))
            record_field_change(
                conn,
                task_id=current,
                field="state",
                old_value=row["state"],
                new_value="cancelled",
                actor=actor,
                session_id=session_id,
            )
            if row["claimed_by"] is not None:
                conn.execute(
                    "UPDATE tasks SET claimed_by = NULL, claimed_at = NULL WHERE id = ?",
                    (current,),
                )
                record_field_change(
                    conn,
                    task_id=current,
                    field="claimed_by",
                    old_value=row["claimed_by"],
                    new_value=None,
                    actor=actor,
                    session_id=session_id,
                )
            touched.append(current)
        stack.extend(
            child[0]
            for child in conn.execute(
                "SELECT target_id FROM task_links WHERE source_id = ? AND relation = 'parent_of'",
                (current,),
            ).fetchall()
        )
    return touched


def apply_update(
    conn: sqlite3.Connection,
    task_id: int,
    actor: str,
    *,
    session_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    type_: TaskType | None = None,
    priority: Priority | None = None,
    state: State | None = None,
    force: bool = False,
    cascade: bool = False,
    scope: Scope = "local",
) -> list[TaskRow]:
    """Apply an update to one task, per the claim/transient-claim rules.

    Returns the updated task first, followed by any tasks cascade-cancelled
    as a side effect. A transient call (the caller does not already hold
    the claim) that would not actually change state or any field is a
    genuine no-op — no claim taken, no events written — the same way
    `revise_fact`/`add_label`/`remove_label` already short-circuit a
    no-effect call. Without this, a call that lands on an already-current
    state (e.g. an id a `--cascade` side effect already reached, also named
    explicitly in the same multi-id batch) would still take and release a
    claim it never needed, leaving a misleading "claimed then immediately
    released" pair in `task_events` for an actor that never actually
    claimed the task for anything.
    """
    task = require_task(conn, task_id, scope=scope)

    if task.claimed_by is not None and task.claimed_by != actor and not force:
        raise _claim_conflict(task_id, task.claimed_by, scope)

    transient = task.claimed_by != actor
    if transient and (state is None or state == task.state):
        no_field_changes = all(
            new is None or new == old
            for old, new in (
                (task.title, title),
                (task.description, description),
                (task.type, type_),
                (task.priority, priority),
            )
        )
        if no_field_changes:
            return [task]

    # Transient: this call is what's holding the claim, taken either because
    # the task was unclaimed or force-stolen — released at the end unless
    # the resulting state is in_progress.
    now = timestamp()

    if transient:
        conn.execute(
            "UPDATE tasks SET claimed_by = ?, claimed_at = ? WHERE id = ?", (actor, now, task_id)
        )
        record_field_change(
            conn,
            task_id=task_id,
            field="claimed_by",
            old_value=task.claimed_by,
            new_value=actor,
            actor=actor,
            session_id=session_id,
        )
    else:
        # A corvee update by the current claimant refreshes claimed_at.
        conn.execute("UPDATE tasks SET claimed_at = ? WHERE id = ?", (now, task_id))
        record_field_change(
            conn,
            task_id=task_id,
            field="claimed_at",
            old_value=task.claimed_at,
            new_value=now,
            actor=actor,
            session_id=session_id,
        )

    cascaded: list[int] = []
    if state is not None and state != task.state:
        validate_transition(task.state, state)
        if state in TERMINAL_STATES:
            if state == "cancelled" and cascade:
                cascaded = cascade_cancel_descendants(
                    conn, task_id, actor, session_id, force=force, scope=scope
                )
            else:
                assert_no_open_children(_open_children(conn, task_id), scope=scope)
        conn.execute("UPDATE tasks SET state = ? WHERE id = ?", (state, task_id))
        record_field_change(
            conn,
            task_id=task_id,
            field="state",
            old_value=task.state,
            new_value=state,
            actor=actor,
            session_id=session_id,
        )

    warnings: list[str] = []
    if state is not None and task.state in TERMINAL_STATES and state not in TERMINAL_STATES:
        parent = _parent(conn, task_id)
        if parent is not None and parent[1] == "done":
            warnings.append(f"parent {task_ref(parent[0], scope)} is done while this task reopened")

    for field, old, new in (
        ("title", task.title, title),
        ("description", task.description, description),
        ("type", task.type, type_),
        ("priority", task.priority, priority),
    ):
        if new is not None and new != old:
            conn.execute(f"UPDATE tasks SET {field} = ? WHERE id = ?", (new, task_id))
            record_field_change(
                conn,
                task_id=task_id,
                field=field,
                old_value=old,
                new_value=new,
                actor=actor,
                session_id=session_id,
            )

    final_state = state if state is not None else task.state
    if final_state in TERMINAL_STATES or (transient and state != "in_progress"):
        current = require_task(conn, task_id, scope=scope)
        if current.claimed_by is not None:
            conn.execute(
                "UPDATE tasks SET claimed_by = NULL, claimed_at = NULL WHERE id = ?", (task_id,)
            )
            record_field_change(
                conn,
                task_id=task_id,
                field="claimed_by",
                old_value=current.claimed_by,
                new_value=None,
                actor=actor,
                session_id=session_id,
            )

    updated = require_task(conn, task_id, scope=scope)
    if warnings:
        updated = replace(updated, warnings=tuple(warnings))
    return [updated, *require_tasks(conn, cascaded, scope=scope)]


def ready_tasks(
    conn: sqlite3.Connection,
    *,
    labels: Sequence[str] = (),
    scope: Scope = "local",
) -> list[TaskRow]:
    """Unclaimed open tasks with no open `blocks` predecessor.

    Excludes claimed tasks unconditionally — a task another actor holds is by
    definition already being worked on, so there is no --unclaimed flag here.
    """
    conditions = [
        "claimed_by IS NULL",
        "state NOT IN ('done', 'cancelled', 'blocked')",
        "NOT EXISTS ("
        "SELECT 1 FROM task_links l JOIN tasks blocker ON blocker.id = l.source_id"
        " WHERE l.target_id = tasks.id AND l.relation = 'blocks'"
        " AND blocker.state NOT IN ('done', 'cancelled')"
        ")",
    ]
    params: list[Any] = []
    for label in labels:
        conditions.append(
            "id IN (SELECT tl.task_id FROM task_labels tl"
            " JOIN labels l ON l.id = tl.label_id WHERE l.name = ?)",
        )
        params.append(label)

    sql = "SELECT * FROM tasks WHERE " + " AND ".join(conditions) + _ORDER_BY
    rows = conn.execute(sql, params).fetchall()
    return [TaskRow.from_row(row, scope=scope) for row in rows]


def search_tasks(
    conn: sqlite3.Connection,
    text: str,
    *,
    include_all: bool = False,
    include_comments: bool = False,
    scope: Scope = "local",
) -> list[TaskRow]:
    """Case-insensitive substring match over title/description.

    `include_comments` extends the match to comment bodies in `task_events`
    (`kind = 'comment'`) — off by default so the common title/description
    query stays as cheap as it is now.
    """
    pattern = f"%{escape_like(text)}%"
    match = "(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\'"
    params: list[Any] = [pattern, pattern]
    if include_comments:
        match += (
            " OR id IN (SELECT task_id FROM task_events"
            " WHERE kind = 'comment' AND body LIKE ? ESCAPE '\\')"
        )
        params.append(pattern)
    conditions = [match + ")"]
    if not include_all:
        conditions.append(f"state IN ({','.join('?' for _ in OPEN_STATES)})")
        params.extend(OPEN_STATES)

    sql = "SELECT * FROM tasks WHERE " + " AND ".join(conditions) + _ORDER_BY
    rows = conn.execute(sql, params).fetchall()
    return [TaskRow.from_row(row, scope=scope) for row in rows]


def mine_tasks(conn: sqlite3.Connection, actor: str, *, scope: Scope = "local") -> list[TaskRow]:
    """Open tasks claimed by `actor`, plus open tasks assigned to `actor` that
    nobody has claimed yet (advisory routing, §4.4), most recently claimed
    first (assigned-but-unclaimed rows, with no `claimed_at`, sort last).
    """
    open_states = ",".join("?" for _ in OPEN_STATES)
    sql = (
        "SELECT * FROM tasks"
        f" WHERE (claimed_by = ? OR (assigned_to = ? AND claimed_by IS NULL))"
        f" AND state IN ({open_states})"
        " ORDER BY claimed_at DESC, id DESC"
    )
    params: list[Any] = [actor, actor, *OPEN_STATES]
    rows = conn.execute(sql, params).fetchall()
    return [TaskRow.from_row(row, scope=scope) for row in rows]


def add_comment(
    conn: sqlite3.Connection,
    task_id: int,
    body: str,
    actor: str,
    session_id: str | None,
    *,
    scope: Scope = "local",
) -> TaskRow:
    task = require_task(conn, task_id, scope=scope)
    record_comment(conn, task_id=task_id, body=body, actor=actor, session_id=session_id)
    if task.claimed_by == actor:
        # A comment from the current claimant refreshes claimed_at; from
        # anyone else it's no evidence the claimant is still alive.
        conn.execute("UPDATE tasks SET claimed_at = ? WHERE id = ?", (timestamp(), task_id))
    return require_task(conn, task_id, scope=scope)
