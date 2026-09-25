#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from corvee.constants import DEFAULT_FACT_STATUS, FactStatus, Scope
from corvee.db.events import record_fact_event
from corvee.db.like import escape_like
from corvee.errors import GuardViolationError, NotFoundError
from corvee.models import FactRow, fact_ref
from corvee.timeutil import timestamp


def insert_fact(
    conn: sqlite3.Connection,
    *,
    claim: str,
    actor: str,
    session_id: str | None = None,
    proof: str | None = None,
    scope: Scope = "local",
) -> FactRow:
    """Create a fact with status=unverified. `proof`, if given, verifies it
    immediately (a `created` event followed by a `verified` event), closing
    the gap of a mandatory two-call "add, then verify" flow.
    """
    now = timestamp()
    cursor = conn.execute(
        "INSERT INTO facts (claim, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (claim, DEFAULT_FACT_STATUS, now, now),
    )
    fact_id = cursor.lastrowid
    if fact_id is None:
        raise RuntimeError("INSERT into facts did not produce a rowid")
    record_fact_event(
        conn,
        fact_id=fact_id,
        kind="created",
        new_value=claim,
        actor=actor,
        session_id=session_id,
    )
    if proof is not None:
        return verify_fact(conn, fact_id, proof, actor, session_id=session_id, scope=scope)
    return require_fact(conn, fact_id, scope=scope)


def get_fact(conn: sqlite3.Connection, fact_id: int, *, scope: Scope = "local") -> FactRow | None:
    row = conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
    return FactRow.from_row(row, scope=scope) if row else None


def require_fact(conn: sqlite3.Connection, fact_id: int, *, scope: Scope = "local") -> FactRow:
    fact = get_fact(conn, fact_id, scope=scope)
    if fact is None:
        raise NotFoundError(
            "fact_not_found",
            f"no such fact: {fact_ref(fact_id, scope)}",
            fact_id=fact_ref(fact_id, scope),
        )
    return fact


def require_facts(
    conn: sqlite3.Connection, fact_ids: Sequence[int], *, scope: Scope = "local"
) -> list[FactRow]:
    """Fetch facts in the given id order (`fact show`'s ordering rule)."""
    return [require_fact(conn, fact_id, scope=scope) for fact_id in fact_ids]


@dataclass(frozen=True)
class FactFilter:
    status: FactStatus | None = None
    include_all: bool = False
    updated_since: str | None = None
    verified_by: str | None = None
    stale_before: str | None = None
    limit: int | None = None


def list_facts(
    conn: sqlite3.Connection, filt: FactFilter, *, scope: Scope = "local"
) -> list[FactRow]:
    conditions: list[str] = []
    params: list[Any] = []

    if filt.status is not None:
        conditions.append("status = ?")
        params.append(filt.status)
    elif not filt.include_all:
        # Default excludes retracted facts only — unlike tasks, an
        # unverified fact is still a live, useful record.
        conditions.append("status <> 'retracted'")
    if filt.updated_since is not None:
        conditions.append("updated_at >= ?")
        params.append(filt.updated_since)
    if filt.verified_by is not None:
        conditions.append("verified_by = ?")
        params.append(filt.verified_by)
    if filt.stale_before is not None:
        conditions.append("verified_at IS NOT NULL AND verified_at < ?")
        params.append(filt.stale_before)

    sql = "SELECT * FROM facts"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC, id DESC"
    if filt.limit is not None:
        sql += " LIMIT ?"
        params.append(filt.limit)

    rows = conn.execute(sql, params).fetchall()
    return [FactRow.from_row(row, scope=scope) for row in rows]


def search_facts(
    conn: sqlite3.Connection,
    text: str,
    *,
    include_all: bool = False,
    include_proof: bool = False,
    verified_by: str | None = None,
    scope: Scope = "local",
) -> list[FactRow]:
    """Case-insensitive substring match over claim text, optionally
    extended to proof text (`--include-proof`).
    """
    pattern = f"%{escape_like(text)}%"
    match = "claim LIKE ? ESCAPE '\\'"
    params: list[Any] = [pattern]
    if include_proof:
        match = f"({match} OR proof LIKE ? ESCAPE '\\')"
        params.append(pattern)
    conditions = [match]
    if not include_all:
        conditions.append("status <> 'retracted'")
    if verified_by is not None:
        conditions.append("verified_by = ?")
        params.append(verified_by)

    sql = (
        "SELECT * FROM facts WHERE "
        + " AND ".join(conditions)
        + " ORDER BY created_at DESC, id DESC"
    )
    rows = conn.execute(sql, params).fetchall()
    return [FactRow.from_row(row, scope=scope) for row in rows]


def revise_fact(
    conn: sqlite3.Connection,
    fact_id: int,
    new_claim: str,
    actor: str,
    *,
    session_id: str | None = None,
    scope: Scope = "local",
) -> FactRow:
    """Change a fact's claim text. A no-op success if `new_claim` is
    identical to the current claim. A genuine change resets a verified or
    retracted fact to unverified: the proof that verified the old text
    says nothing about the new one, and revising a retracted fact's text
    is itself a signal the fact should re-enter the normal flow.
    """
    fact = require_fact(conn, fact_id, scope=scope)
    if new_claim == fact.claim:
        return fact

    conn.execute("UPDATE facts SET claim = ? WHERE id = ?", (new_claim, fact_id))
    record_fact_event(
        conn,
        fact_id=fact_id,
        kind="revised",
        old_value=fact.claim,
        new_value=new_claim,
        actor=actor,
        session_id=session_id,
    )
    if fact.status != DEFAULT_FACT_STATUS:
        conn.execute(
            "UPDATE facts SET status = ?, verified_at = NULL, verified_by = NULL, proof = NULL"
            " WHERE id = ?",
            (DEFAULT_FACT_STATUS, fact_id),
        )
        record_fact_event(
            conn,
            fact_id=fact_id,
            kind="unverified",
            actor=actor,
            session_id=session_id,
        )
    return require_fact(conn, fact_id, scope=scope)


def verify_fact(
    conn: sqlite3.Connection,
    fact_id: int,
    proof: str,
    actor: str,
    *,
    session_id: str | None = None,
    scope: Scope = "local",
) -> FactRow:
    """Mark a fact verified, recording proof and a timestamp. Re-verifying
    an already-verified fact succeeds and refreshes both.
    """
    require_fact(conn, fact_id, scope=scope)
    now = timestamp()
    conn.execute(
        "UPDATE facts SET status = 'verified', verified_at = ?, verified_by = ?, proof = ?"
        " WHERE id = ?",
        (now, actor, proof, fact_id),
    )
    record_fact_event(
        conn,
        fact_id=fact_id,
        kind="verified",
        proof=proof,
        actor=actor,
        session_id=session_id,
    )
    return require_fact(conn, fact_id, scope=scope)


def unverify_fact(
    conn: sqlite3.Connection,
    fact_id: int,
    actor: str,
    *,
    note: str | None = None,
    session_id: str | None = None,
    scope: Scope = "local",
) -> FactRow:
    require_fact(conn, fact_id, scope=scope)
    conn.execute(
        "UPDATE facts SET status = 'unverified', verified_at = NULL, verified_by = NULL,"
        " proof = NULL WHERE id = ?",
        (fact_id,),
    )
    record_fact_event(
        conn,
        fact_id=fact_id,
        kind="unverified",
        note=note,
        actor=actor,
        session_id=session_id,
    )
    return require_fact(conn, fact_id, scope=scope)


def retract_fact(
    conn: sqlite3.Connection,
    fact_id: int,
    actor: str,
    *,
    reason: str | None = None,
    session_id: str | None = None,
    scope: Scope = "local",
) -> FactRow:
    """Withdraw a fact. Excluded from the default `fact list`; `verify`,
    `unverify` and `revise` all still work on it and move it back into
    the normal flow.
    """
    require_fact(conn, fact_id, scope=scope)
    conn.execute(
        "UPDATE facts SET status = 'retracted', verified_at = NULL, verified_by = NULL,"
        " proof = NULL WHERE id = ?",
        (fact_id,),
    )
    record_fact_event(
        conn,
        fact_id=fact_id,
        kind="retracted",
        note=reason,
        actor=actor,
        session_id=session_id,
    )
    return require_fact(conn, fact_id, scope=scope)


def delete_fact(conn: sqlite3.Connection, fact_id: int, *, scope: Scope = "local") -> FactRow:
    """Permanently remove a retracted fact and its entire fact_events history.

    Only works when the fact's current status is 'retracted' — retract is
    always the reversible first step, so nothing is hard-removed without
    first passing through a state where its removal was visible and
    undoable. Returns the fact's last state, since no row is left to
    describe after this call.
    """
    fact = require_fact(conn, fact_id, scope=scope)
    if fact.status != "retracted":
        raise GuardViolationError(
            "fact_not_retracted",
            f"{fact_ref(fact_id, scope)} is not retracted; run `corvee fact retract` first",
            fact_id=fact_ref(fact_id, scope),
            status=fact.status,
        )
    conn.execute("DELETE FROM fact_events WHERE fact_id = ?", (fact_id,))
    conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    return fact
