#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Iterator
from typing import Any

from corvee.constants import FACT_STATUSES, STATES, Scope
from corvee.models import task_ref


def project_stats(conn: sqlite3.Connection, *, stale_before: str | None) -> dict[str, Any]:
    """Project-wide health counts for `corvee doctor`.

    Unlike `task list`/`fact list`, every count here is over the whole
    table regardless of state/status — a health check that silently
    excluded done tasks or retracted facts would be lying about project
    size. `stale_before` is a timestamp cutoff (or None to skip the stale
    count entirely), the same cutoff `task list --stale` computes.
    """
    task_total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    by_state = dict.fromkeys(STATES, 0)
    for row in conn.execute("SELECT state, COUNT(*) FROM tasks GROUP BY state"):
        by_state[row[0]] = row[1]
    claimed = conn.execute("SELECT COUNT(*) FROM tasks WHERE claimed_by IS NOT NULL").fetchone()[0]
    stale = 0
    if stale_before is not None:
        stale = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE claimed_at IS NOT NULL AND claimed_at < ?",
            (stale_before,),
        ).fetchone()[0]

    fact_total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    by_status = dict.fromkeys(FACT_STATUSES, 0)
    for row in conn.execute("SELECT status, COUNT(*) FROM facts GROUP BY status"):
        by_status[row[0]] = row[1]

    label_total = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]

    return {
        "tasks": {
            "total": task_total,
            "by_state": by_state,
            "claimed": claimed,
            "stale": stale,
        },
        "facts": {
            "total": fact_total,
            "by_status": by_status,
        },
        "labels": label_total,
    }


def _cycles_for_relation(conn: sqlite3.Connection, relation: str) -> list[list[int]]:
    """Every cycle among `task_links` edges of `relation`, found by a
    classic white/gray/black DFS (gray = currently on the stack; hitting
    a gray node closes a cycle back to it).

    A cycle should never reach this point through normal use — `link`
    itself is cycle-checked on insert (§4.3) — so this only ever fires
    against a database edited outside corvee. Iterative, with an explicit
    stack of (node, remaining-neighbors) frames instead of a recursive call
    per edge, the same shape `guards/ancestry.py:is_reachable` uses — a
    `parent_of`/`blocks` chain longer than Python's recursion limit is not
    far-fetched for this tool's own "one task per item" guidance, and a
    plain acyclic chain that deep would otherwise raise RecursionError here
    before ever getting the chance to report it found no cycle.
    """
    edges: dict[int, list[int]] = {}
    for source_id, target_id in conn.execute(
        "SELECT source_id, target_id FROM task_links WHERE relation = ?", (relation,)
    ):
        edges.setdefault(source_id, []).append(target_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {}
    cycles: list[list[int]] = []

    for start_node in edges:
        if color.get(start_node, WHITE) != WHITE:
            continue
        path: list[int] = [start_node]
        frames: list[tuple[int, Iterator[int]]] = [(start_node, iter(edges.get(start_node, ())))]
        color[start_node] = GRAY
        while frames:
            node, neighbors = frames[-1]
            for neighbor in neighbors:
                state = color.get(neighbor, WHITE)
                if state == WHITE:
                    color[neighbor] = GRAY
                    path.append(neighbor)
                    frames.append((neighbor, iter(edges.get(neighbor, ()))))
                    break
                if state == GRAY:
                    start = path.index(neighbor)
                    cycles.append([*path[start:], neighbor])
            else:
                frames.pop()
                path.pop()
                color[node] = BLACK
    return cycles


def _shared_actor_session_findings(
    conn: sqlite3.Connection, *, scope: Scope, since: str
) -> list[dict[str, Any]]:
    """Currently-claimed tasks whose claimant's own recent events (§4.4's stale
    window) carry more than one distinct session id — the detectable
    signature of two live sessions sharing one unconfigured actor identity
    (§4.4's `CORVEE_ACTOR` guidance exists to prevent exactly this
    collision, but has no way to *stop* it when skipped, only to surface
    it, the same as claim staleness already does).
    """
    sessions_by_task: dict[int, set[str]] = {}
    for task_id, session_id in conn.execute(
        "SELECT e.task_id, e.session_id FROM task_events e"
        " JOIN tasks t ON t.id = e.task_id"
        " WHERE t.claimed_by IS NOT NULL AND e.actor = t.claimed_by"
        " AND e.session_id IS NOT NULL AND e.created_at >= ?",
        (since,),
    ):
        sessions_by_task.setdefault(task_id, set()).add(session_id)

    findings: list[dict[str, Any]] = []
    for task_id, session_ids in sessions_by_task.items():
        if len(session_ids) < 2:
            continue
        claimed_by = conn.execute(
            "SELECT claimed_by FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()[0]
        findings.append(
            {
                "kind": "shared_actor_sessions",
                "task_id": task_ref(task_id, scope),
                "actor": claimed_by,
                "session_ids": sorted(session_ids),
            }
        )
    return findings


def integrity_findings(
    conn: sqlite3.Connection, *, scope: Scope = "local", stale_before: str | None = None
) -> list[dict[str, Any]]:
    """Problems `project_stats`'s counts can't surface: a `blocks`/`parent_of`
    cycle (which would drop tasks out of `task ready` forever), any
    foreign-key row a non-corvee writer left dangling, and (when
    `stale_before` is given, the same cutoff `task list --stale` computes)
    a currently-claimed task with recent activity from more than one
    session under its claimant's actor string. Empty on a healthy project;
    read-only, like the rest of `doctor`.
    """
    findings: list[dict[str, Any]] = []
    for relation in ("parent_of", "blocks"):
        for cycle in _cycles_for_relation(conn, relation):
            findings.append(
                {
                    "kind": "cycle",
                    "relation": relation,
                    "task_ids": [task_ref(task_id, scope) for task_id in cycle],
                }
            )
    for table, rowid, parent, _fkid in conn.execute("PRAGMA foreign_key_check"):
        findings.append(
            {
                "kind": "dangling_foreign_key",
                "table": table,
                "rowid": rowid,
                "references": parent,
            }
        )
    if stale_before is not None:
        findings.extend(_shared_actor_session_findings(conn, scope=scope, since=stale_before))
    return findings


def claims_summary(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Live claims grouped by actor: count and the oldest claimed_at, oldest first.

    Distinct from `project_stats`'s single `claimed` count — this answers
    "which actors have anything claimed right now, and since when" without
    the caller already knowing every actor string to check individually.
    """
    rows = conn.execute(
        "SELECT claimed_by, COUNT(*), MIN(claimed_at) FROM tasks"
        " WHERE claimed_by IS NOT NULL GROUP BY claimed_by ORDER BY MIN(claimed_at)"
    ).fetchall()
    return [{"actor": row[0], "count": row[1], "oldest_claimed_at": row[2]} for row in rows]
