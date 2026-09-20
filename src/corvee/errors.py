#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from typing import Any


class CorveeError(Exception):
    """Base for every error that maps to a documented exit code.

    `code` is the raise site's machine-stable slug (e.g. "invalid_transition"),
    distinct from `exit_code`, which is the coarser, fixed-per-subclass exit
    status. `extra` carries whatever detail lets the caller recover without a
    second query (e.g. `claimed_by`, `blocking_ids`).
    """

    exit_code: int = 1

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_json(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}


class UsageError(CorveeError):
    """Bad flag, unknown --fields name, invalid state, etc. (exit 2)."""

    exit_code = 2


class NotFoundError(CorveeError):
    """Task not found (exit 3)."""

    exit_code = 3


class ClaimConflictError(CorveeError):
    """Task held by another actor (exit 4)."""

    exit_code = 4


class GuardViolationError(CorveeError):
    """Open children, parent_of cycle, rejected transition, etc. (exit 5)."""

    exit_code = 5


class ConfigError(CorveeError):
    """No or unreadable .corvee/config.toml, a database file that cannot be
    opened or written, schema newer than binary (exit 6).
    """

    exit_code = 6
