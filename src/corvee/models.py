#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import re
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from corvee.constants import FactStatus, Priority, Scope, State, TaskType
from corvee.errors import UsageError

TASK_REF_PREFIX = "TASK-"
FACT_REF_PREFIX = "FACT-"
TASK_GLOBAL_REF_PREFIX = "TASK-GLOBAL-"
FACT_GLOBAL_REF_PREFIX = "FACT-GLOBAL-"
_TASK_REF_RE = re.compile(rf"^{TASK_REF_PREFIX}(\d+)$", re.IGNORECASE)
_FACT_REF_RE = re.compile(rf"^{FACT_REF_PREFIX}(\d+)$", re.IGNORECASE)
_TASK_GLOBAL_REF_RE = re.compile(rf"^{TASK_GLOBAL_REF_PREFIX}(\d+)$", re.IGNORECASE)
_FACT_GLOBAL_REF_RE = re.compile(rf"^{FACT_GLOBAL_REF_PREFIX}(\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedRef:
    """A task/fact id normalized to its integer form and the database it belongs to."""

    id: int
    scope: Scope


def task_ref(task_id: int, scope: Scope = "local") -> str:
    """The external reference form, e.g. TASK-14, or TASK-GLOBAL-14."""
    prefix = TASK_GLOBAL_REF_PREFIX if scope == "global" else TASK_REF_PREFIX
    return f"{prefix}{task_id}"


def fact_ref(fact_id: int, scope: Scope = "local") -> str:
    """The external reference form, e.g. FACT-7, or FACT-GLOBAL-7."""
    prefix = FACT_GLOBAL_REF_PREFIX if scope == "global" else FACT_REF_PREFIX
    return f"{prefix}{fact_id}"


def parse_task_ref(value: str) -> ParsedRef:
    """Accept "TASK-14", "TASK-GLOBAL-14", or bare "14" and normalize."""
    match = _TASK_GLOBAL_REF_RE.match(value)
    if match:
        return ParsedRef(int(match.group(1)), "global")
    match = _TASK_REF_RE.match(value)
    if match:
        return ParsedRef(int(match.group(1)), "local")
    if _FACT_GLOBAL_REF_RE.match(value) or _FACT_REF_RE.match(value):
        # Both id parsers otherwise accept a bare integer, so the two id
        # spaces would be silently ambiguous without this guard.
        raise UsageError(
            "wrong_id_namespace",
            f"{value!r} is a fact id, not a task id; use `corvee fact show` instead",
            value=value,
        )
    if value.isdigit():
        return ParsedRef(int(value), "local")
    raise UsageError(
        "invalid_task_id",
        f"invalid task id {value!r}: expected TASK-<n>, TASK-GLOBAL-<n>, or a bare integer",
        value=value,
    )


def parse_fact_ref(value: str) -> ParsedRef:
    """Accept "FACT-7", "FACT-GLOBAL-7", or bare "7" and normalize."""
    match = _FACT_GLOBAL_REF_RE.match(value)
    if match:
        return ParsedRef(int(match.group(1)), "global")
    match = _FACT_REF_RE.match(value)
    if match:
        return ParsedRef(int(match.group(1)), "local")
    if _TASK_GLOBAL_REF_RE.match(value) or _TASK_REF_RE.match(value):
        raise UsageError(
            "wrong_id_namespace",
            f"{value!r} is a task id, not a fact id; use `corvee task show` instead",
            value=value,
        )
    if value.isdigit():
        return ParsedRef(int(value), "local")
    raise UsageError(
        "invalid_fact_id",
        f"invalid fact id {value!r}: expected FACT-<n>, FACT-GLOBAL-<n>, or a bare integer",
        value=value,
    )


def _parse_refs(
    values: Sequence[str], parse_one: Callable[[str], ParsedRef]
) -> tuple[list[int], Scope]:
    """Parse multiple refs, requiring they share one scope.

    Deduplicates while preserving first-seen order — a caller listing the
    same id twice almost certainly means "operate on it once," not "give me
    it back twice."
    """
    parsed = [parse_one(value) for value in values]
    scopes = {p.scope for p in parsed}
    if len(scopes) > 1:
        raise UsageError(
            "mixed_scope",
            "all ids in one call must share one scope, local or global",
            values=list(values),
        )
    seen: set[int] = set()
    ids: list[int] = []
    for p in parsed:
        if p.id not in seen:
            seen.add(p.id)
            ids.append(p.id)
    return ids, parsed[0].scope


def parse_task_refs(values: Sequence[str]) -> tuple[list[int], Scope]:
    """Parse multiple task refs, requiring they share one scope."""
    return _parse_refs(values, parse_task_ref)


def parse_fact_refs(values: Sequence[str]) -> tuple[list[int], Scope]:
    """Parse multiple fact refs, requiring they share one scope."""
    return _parse_refs(values, parse_fact_ref)


@dataclass(frozen=True)
class TaskRow:
    id: int
    title: str
    description: str
    type: TaskType
    priority: Priority
    state: State
    claimed_by: str | None
    claimed_at: str | None
    created_at: str
    updated_at: str
    assigned_to: str | None = None
    scope: Scope = "local"
    # Advisory-only, never persisted: attached by the db layer to flag a
    # spec-called-out oddity (e.g. reopening a child of a done parent)
    # without rejecting the write. Omitted from to_dict() when empty so it
    # never appears on ordinary list/show output.
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_row(cls, row: sqlite3.Row, scope: Scope = "local") -> "TaskRow":
        return cls(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            type=cast(TaskType, row["type"]),
            priority=cast(Priority, row["priority"]),
            state=cast(State, row["state"]),
            claimed_by=row["claimed_by"],
            claimed_at=row["claimed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            assigned_to=row["assigned_to"],
            scope=scope,
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": task_ref(self.id, self.scope),
            "title": self.title,
            "description": self.description,
            "type": self.type,
            "priority": self.priority,
            "state": self.state,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at,
            "assigned_to": self.assigned_to,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scope": self.scope,
        }
        if self.warnings:
            result["warnings"] = list(self.warnings)
        return result


@dataclass(frozen=True)
class FactRow:
    id: int
    claim: str
    status: FactStatus
    verified_at: str | None
    verified_by: str | None
    proof: str | None
    created_at: str
    updated_at: str
    scope: Scope = "local"

    @classmethod
    def from_row(cls, row: sqlite3.Row, scope: Scope = "local") -> "FactRow":
        return cls(
            id=row["id"],
            claim=row["claim"],
            status=cast(FactStatus, row["status"]),
            verified_at=row["verified_at"],
            verified_by=row["verified_by"],
            proof=row["proof"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            scope=scope,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": fact_ref(self.id, self.scope),
            "claim": self.claim,
            "status": self.status,
            "verified_at": self.verified_at,
            "verified_by": self.verified_by,
            "proof": self.proof,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scope": self.scope,
        }
