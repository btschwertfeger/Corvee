#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from corvee import __version__
from corvee.actor import resolve_session_id
from corvee.config import ProjectConfig, resolve_project
from corvee.errors import ConfigError
from corvee.mcp.server_config import ServerConfig
from corvee.mcp.worker import DbWorker

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

_BASE_INSTRUCTIONS = (
    "corvee is a single-machine, non-git-tracked, persistent, "
    "multi-agent-aware CLI task tracker and fact store. Use task_show/"
    "task_search/brief/fact_search to orient, task_add to file new work, "
    "then task_claim/task_start/task_comment/task_done/task_review/"
    "task_cancel/task_block to work a task, releasing it with task_unclaim "
    "if you cannot finish it. task_block requires a comment explaining why. "
    "Check an existing fact with fact_show before re-deriving it; record "
    "new or updated ones with fact_add/fact_verify."
)


def resolve_server_session_id(session_id: str | None) -> str:
    """Resolve the server's own default `session_id`, used by any write
    tool call that omits its own per-call argument.

    Given, `session_id` is used verbatim. Omitted, falls back to
    `resolve_session_id()` -- the same `--session-id`/`$CORVEE_SESSION_ID`
    resolution the CLI's own global flag already uses. If that resolves to
    nothing either, mints one `uuid4` for the process's whole lifetime,
    since spec §10.1 already expects one server process per conversation:
    a per-process id is a truthful "which run touched this" answer even
    when nothing configured one explicitly, and it is what makes
    `session_id` safe to leave optional on every write tool (rather than
    every omitted call defaulting to `None` and defeating `doctor`'s
    multi-session-claim detector the same way an unconfigured `$CORVEE_ACTOR`
    does for actor, per §4.4).
    """
    return session_id or resolve_session_id() or str(uuid.uuid4())


def _global_only_explanation(config: ServerConfig) -> str:
    return (
        "No local project found: this server is in global-only mode. Only "
        "*-GLOBAL-<n> ids resolve, and task_add/fact_add need "
        f"is_global: true to write anything (actor: {config.actor})."
    )


def build_instructions(config: ServerConfig) -> str:
    """The `instructions` string handed to the MCP client, resolved per
    server instance rather than a static constant: a caller landing in
    global-only mode (no project resolved at startup) needs to know that
    up front, the same way `brief`'s otherwise-indistinguishable empty
    result does not tell it on its own (spec §10.1).
    """
    if config.project is not None:
        project_root = config.project.root
        return f"{_BASE_INSTRUCTIONS} Serving the project at {project_root}."
    return f"{_BASE_INSTRUCTIONS} {_global_only_explanation(config)}"


def startup_message(config: ServerConfig) -> str:
    """One line describing the resolved mode, printed to stderr at startup
    (never stdout -- §10.2's stdio-framing constraint) so a host's own
    logs name the project or global-only mode without needing a first
    `brief` call to find out.
    """
    if config.project is not None:
        return f"corvee mcp serve: project {config.project.root} (actor: {config.actor})"
    return f"corvee mcp serve: {_global_only_explanation(config)}"


def resolve_server_project(project_root: Path | None) -> ProjectConfig | None:
    """Resolve the project a server launched with `project_root` should serve.

    Given, `project_root` is an explicit override: resolved via
    `resolve_project(project_root)`, propagating `ConfigError` if it does
    not resolve. An explicit path that turns out wrong is a real usage
    error -- the server refuses to start rather than silently falling back
    to global-only mode.

    Omitted, this auto-detects exactly like the CLI's own default:
    `resolve_project()`, cwd-based. If that raises (no project anywhere
    above cwd), the result is `None` -- global-only mode -- rather than
    propagating, the same graceful degrade `cli/scope.py::scopes_for`
    already applies for a merged CLI read with no local project, not a new
    behavior invented for MCP.
    """
    if project_root is not None:
        return resolve_project(project_root)
    try:
        return resolve_project()
    except ConfigError:
        return None


def build_server(config: ServerConfig) -> tuple[MCPServer, DbWorker]:
    """Construct the MCPServer instance for this process, plus the one
    dedicated `DbWorker` thread every tool handler this server registers
    runs its DB work on for the process's whole lifetime (§10.1).

    Returns both so the caller (`corvee mcp serve`) can shut the worker
    thread down once `app.run()` returns, whether that's a clean exit or an
    exception -- `build_server` itself does not know when the server stops.

    Import of the `mcp` package itself is deferred to the caller (the
    `corvee mcp serve` command), which turns a missing `corvee[mcp]` extra
    into a clean, exit-6-shaped error instead of a raw ImportError -- this
    module is only ever reached once that check has already passed.
    """
    from mcp.server.mcpserver import MCPServer

    from corvee.mcp.tools_fact import register_fact_tools
    from corvee.mcp.tools_read import register_read_tools
    from corvee.mcp.tools_write import register_write_tools

    print(startup_message(config), file=sys.stderr)
    app: MCPServer = MCPServer(
        name="corvee",
        version=__version__,
        instructions=build_instructions(config),
    )
    worker = DbWorker()
    register_read_tools(app, config, worker)
    register_write_tools(app, config, worker)
    register_fact_tools(app, config, worker)
    return app, worker
