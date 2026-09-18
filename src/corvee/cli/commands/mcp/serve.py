#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from pathlib import Path

import click

from corvee.actor import resolve_actor
from corvee.errors import ConfigError


def _mcp_extra_not_installed() -> ConfigError:
    return ConfigError(
        "mcp_extra_not_installed",
        "the 'mcp' package is not installed; run `pip install "
        "'corvee[mcp]'` (or `uv tool install 'corvee[mcp]'`) to use "
        "`corvee mcp serve`",
    )


EPILOG = """\
\b
Examples:
Serve the project at the current directory (or an ancestor of it), auto-detected:
  corvee mcp serve
Identify the server process to every call it makes:
  corvee mcp serve --actor agent:claude
Serve a specific project regardless of the server's own working directory:
  corvee mcp serve --project-root /path/to/project
"""


@click.command(epilog=EPILOG)
@click.option(
    "--project-root",
    "-p",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Explicit project directory to serve, overriding auto-detection. "
    "Omit to auto-detect from the server's own working directory, the "
    "same lookup the CLI uses; falls back to global scope only if "
    "nothing is found there.",
)
@click.option(
    "--actor",
    "-a",
    default=None,
    help="Stable identity for this server process, read once at startup. "
    "Falls back to a leading global --actor flag, then $CORVEE_ACTOR, "
    "then human:$USER.",
)
@click.option(
    "--session-id",
    "-s",
    default=None,
    help="Default per-session token for this server process, used by any "
    "tool call that omits its own session_id argument. Falls back to a "
    "leading global --session-id flag, then $CORVEE_SESSION_ID, then a "
    "generated id unique to this process.",
)
def serve(project_root: Path | None, actor: str | None, session_id: str | None) -> None:
    """Serve corvee's tasks and facts over the Model Context Protocol.

    \b
    A long-lived process, unlike every other corvee command: it keeps
    running until the host closes its stdio pipes, serving one tool call
    at a time on a single dedicated worker thread. Run one server process
    per agent conversation -- a process shared across several conversations
    shares one actor identity for as long as it lives.
    """
    try:
        import mcp  # noqa: F401
    except ImportError as error:
        raise _mcp_extra_not_installed() from error

    from corvee.mcp.server import (
        ServerConfig,
        build_server,
        resolve_server_project,
        resolve_server_session_id,
    )

    resolved_actor = resolve_actor(actor)
    resolved_session_id = resolve_server_session_id(session_id)
    resolved_project = resolve_server_project(project_root)

    config = ServerConfig(
        actor=resolved_actor, project=resolved_project, session_id=resolved_session_id
    )
    try:
        # build_server's own deferred `from mcp.server.mcpserver import
        # MCPServer` (not reached by the bare `import mcp` check above,
        # which only proves the top-level package exists) is the one
        # that would actually break on a future mcp release that moves
        # or removes that submodule -- caught here so that surfaces as
        # the same clean exit 6 instead of an uncaught ImportError
        # falling through to CorveeGroup.main()'s generic exit-1 handler
        # (TASK-36).
        app, worker = build_server(config)
    except ImportError as error:
        raise _mcp_extra_not_installed() from error
    try:
        app.run(transport="stdio")
    finally:
        worker.close()
