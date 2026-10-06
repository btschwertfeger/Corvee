#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Callable, Sequence
from typing import TypeVar

from corvee.cli.scope import fetch_merged
from corvee.constants import Scope, ScopeFilter
from corvee.errors import ConfigError
from corvee.mcp.server_config import ServerConfig

T = TypeVar("T")


def require_scope_available(config: ServerConfig, scope: str) -> None:
    """Raise `no_project` (exit 6) if `scope == "local"` and this server has
    no resolved project (global-only mode, §10.1). The one check every
    ref-taking tool, plus every scope-filter-driven one (`brief`,
    `fact_search`, `task_search` via `fetch_merged_for_config` below),
    needs before doing anything else.
    """
    if scope == "local" and config.project is None:
        raise ConfigError(
            "no_project",
            "no project in scope; start the server with --project-root, "
            "from inside a project, or use a *-GLOBAL-<n> id instead",
        )


def fetch_merged_for_config(
    config: ServerConfig,
    scope_filter: ScopeFilter,
    fetch: Callable[[sqlite3.Connection, Scope], Sequence[T]],
) -> list[T]:
    """The MCP-layer entry point for `cli/scope.py::fetch_merged`: threads
    `config.actor`/the already-resolved project's db path explicitly into
    every `corvee_context` call instead of relying on click's
    (thread-local) context or cwd -- the same requirement §10.1 places on
    every other piece of per-call DB work here. Raises via
    `require_scope_available` for `scope_filter="local"` with no project,
    before `fetch_merged` itself ever reaches a `corvee_context` call
    whose ambient cwd fallback would be meaningless from the worker
    thread.

    Passes `project_db_path`, not `project_root`: `config.project` is
    already a fully-resolved `ProjectConfig`, so there is nothing left to
    re-derive from a directory (TASK-37) -- every call here would
    otherwise re-walk the filesystem to `.corvee/config.toml` and
    re-parse it from scratch, the exact cache spec §10.1 claims exists
    made only accidentally true by that re-derivation always landing back
    on the same path.
    """
    if scope_filter == "local":
        require_scope_available(config, "local")
    project_db_path = config.project.db_path if config.project else None
    return fetch_merged(
        scope_filter,
        fetch,
        actor=config.actor,
        project_db_path=project_db_path,
        local_available=config.project is not None,
    )
