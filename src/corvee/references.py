#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import re
import sqlite3
from collections.abc import Callable
from typing import Literal

from corvee.constants import Scope
from corvee.db.facts import get_fact
from corvee.db.tasks import get_task
from corvee.models import fact_ref, task_ref

Kind = Literal["task", "fact"]

_MENTION_RE = re.compile(
    r"\b(?:"
    r"TASK-GLOBAL-(?P<task_global>\d+)"
    r"|TASK-(?P<task_local>\d+)"
    r"|FACT-GLOBAL-(?P<fact_global>\d+)"
    r"|FACT-(?P<fact_local>\d+)"
    r")\b",
    re.IGNORECASE,
)


def find_referenced(
    texts: list[str | None],
    *,
    own_kind: Kind,
    own_id: int,
    own_scope: Scope,
    same_scope_conn: sqlite3.Connection,
    other_scope_conn: Callable[[], sqlite3.Connection],
) -> list[str]:
    """Distinct `TASK-<n>`/`TASK-GLOBAL-<n>`/`FACT-<n>`/`FACT-GLOBAL-<n>` mentions
    found in `texts` that resolve to a real row, in order of first appearance.

    A mention is checked against whichever scope its own prefix names — the
    same connection already open for the record being shown if that scope
    matches, or `other_scope_conn()` (called lazily, at most once) if it
    names the other one. A mention that doesn't resolve to a real row, or
    that names the record's own id, is silently dropped, the same tolerant
    spirit `task_events`/`fact_events` already apply to free-text fields.

    Resolution is asymmetric: a bare `TASK-<n>`/`FACT-<n>` mention found in a
    *global* record's own text is dropped unconditionally, never checked
    against the reader's own local project. The global database is shared
    machine-wide and tied to no one local project, so such a mention has no
    fixed target to resolve against — whichever project happens to be the
    caller's cwd is arbitrary, not the project that wrote the mention. A
    `TASK-GLOBAL-<n>`/`FACT-GLOBAL-<n>` mention names the one global
    database unambiguously regardless of scope, so it keeps resolving both
    ways.
    """
    seen: set[tuple[Kind, Scope, int]] = set()
    result: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in _MENTION_RE.finditer(text):
            kind: Kind
            scope: Scope
            if match["task_global"] is not None:
                kind, scope, ref_id = "task", "global", int(match["task_global"])
            elif match["task_local"] is not None:
                kind, scope, ref_id = "task", "local", int(match["task_local"])
            elif match["fact_global"] is not None:
                kind, scope, ref_id = "fact", "global", int(match["fact_global"])
            else:
                kind, scope, ref_id = "fact", "local", int(match["fact_local"])

            if own_scope == "global" and scope == "local":
                continue
            if (kind, scope, ref_id) == (own_kind, own_scope, own_id):
                continue
            key = (kind, scope, ref_id)
            if key in seen:
                continue
            seen.add(key)

            conn = same_scope_conn if scope == own_scope else other_scope_conn()
            if kind == "task":
                exists = get_task(conn, ref_id, scope=scope) is not None
            else:
                exists = get_fact(conn, ref_id, scope=scope) is not None
            if exists:
                external = task_ref(ref_id, scope) if kind == "task" else fact_ref(ref_id, scope)
                result.append(external)
    return result
