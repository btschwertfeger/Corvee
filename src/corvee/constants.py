#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import re
from typing import Literal, get_args

State = Literal["open", "in_progress", "blocked", "review", "done", "cancelled"]
Priority = Literal["low", "medium", "high", "critical"]
TaskType = Literal["task", "bug", "feature", "epic", "chore", "spike"]
Relation = Literal["blocks", "relates_to", "duplicates", "parent_of"]
FactStatus = Literal["unverified", "verified", "retracted"]
Scope = Literal["local", "global"]
ScopeFilter = Literal["local", "global", "all"]

STATES: tuple[State, ...] = get_args(State)
PRIORITIES: tuple[Priority, ...] = get_args(Priority)
TASK_TYPES: tuple[TaskType, ...] = get_args(TaskType)
RELATIONS: tuple[Relation, ...] = get_args(Relation)
FACT_STATUSES: tuple[FactStatus, ...] = get_args(FactStatus)
SCOPE_FILTERS: tuple[ScopeFilter, ...] = get_args(ScopeFilter)
SCOPES: tuple[Scope, ...] = get_args(Scope)

DEFAULT_STATE: State = "open"
DEFAULT_PRIORITY: Priority = "medium"
DEFAULT_TASK_TYPE: TaskType = "task"
DEFAULT_FACT_STATUS: FactStatus = "unverified"

# Priority descending: first row of `corvee ready` is the most worth starting.
PRIORITY_ORDER: dict[Priority, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

TERMINAL_STATES: frozenset[State] = frozenset({"done", "cancelled"})
OPEN_STATES: frozenset[State] = frozenset(STATES) - TERMINAL_STATES

# The permitted state transitions, as data rather than branching logic.
TRANSITIONS: dict[State, frozenset[State]] = {
    "open": frozenset({"in_progress", "blocked", "done", "cancelled"}),
    "in_progress": frozenset({"open", "blocked", "review", "done", "cancelled"}),
    "blocked": frozenset({"open", "in_progress", "cancelled"}),
    "review": frozenset({"in_progress", "blocked", "done", "cancelled"}),
    "done": frozenset({"open", "in_progress"}),
    "cancelled": frozenset({"open"}),
}

# Flat columns accepted by --fields on list/ready/search.
LIST_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "description",
    "type",
    "priority",
    "state",
    "claimed_by",
    "claimed_at",
    "assigned_to",
    "created_at",
    "updated_at",
    "scope",
)

# Flat columns accepted by --fields on fact list/search.
FACT_LIST_FIELDS: tuple[str, ...] = (
    "id",
    "claim",
    "status",
    "verified_at",
    "verified_by",
    "proof",
    "created_at",
    "updated_at",
    "scope",
)

# Table columns shown when list/ready/search/mine is run without --fields:
# LIST_FIELDS minus "description", the long free-text column that blows up a
# fixed-width table's row length. --fields can still request it explicitly.
# Does not affect --json, which always returns the full row shape.
LIST_TABLE_DEFAULT_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "type",
    "priority",
    "state",
    "claimed_by",
    "claimed_at",
    "assigned_to",
    "created_at",
    "updated_at",
    "scope",
)

# The fact-group equivalent of LIST_TABLE_DEFAULT_FIELDS: FACT_LIST_FIELDS
# minus "proof".
FACT_LIST_TABLE_DEFAULT_FIELDS: tuple[str, ...] = (
    "id",
    "claim",
    "status",
    "verified_at",
    "verified_by",
    "created_at",
    "updated_at",
    "scope",
)

# Label names are lowercased/trimmed on the way in, [a-z0-9][a-z0-9._/-]{0,49}.
LABEL_PATTERN = re.compile(r"[a-z0-9][a-z0-9._/-]{0,49}")

DEFAULT_STALE_DURATION = "4h"
