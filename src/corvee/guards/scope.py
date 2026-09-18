#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from corvee.constants import Scope
from corvee.errors import GuardViolationError


def assert_same_scope(source_scope: Scope, target_scope: Scope) -> None:
    """Raise GuardViolationError if two refs don't share one database.

    A link, or a new task's `--parent`, points across two ordinary Python
    values here, but each scope is a distinct SQLite file with its own
    foreign keys — there is no cross-database `REFERENCES` to enforce this
    at the schema level, so it is checked explicitly before either side is
    touched.
    """
    if source_scope != target_scope:
        raise GuardViolationError(
            "cross_scope_link",
            "cannot link a local task/fact to a global one, or vice versa",
            source_scope=source_scope,
            target_scope=target_scope,
        )
