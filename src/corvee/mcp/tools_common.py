#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

"""Parameter shapes and helpers shared by `tools_write.py`, `tools_fact.py`,
and `tools_read.py`, split out so none of the three has to import from
either of the other two just to reuse a `Field` annotation or a context
helper.
"""

from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from corvee.cli.context import corvee_context
from corvee.constants import SCOPE_FILTERS, ScopeFilter
from corvee.errors import UsageError
from corvee.mcp.scope import require_scope_available
from corvee.mcp.server import ServerConfig
from corvee.models import parse_task_ref


def _enum_field(description: str, choices: tuple[str, ...]) -> Any:
    """A `str` `Field` whose JSON schema also advertises a closed set of
    valid values (`enum`), without pydantic enforcing it at the argument-
    parsing boundary the way a `Literal` type would. A bad value still
    reaches the tool's own handler and its existing `UsageError` (spec
    §10.2's clean-error contract), rather than surfacing as a raw
    protocol-level validation error the SDK raises before the handler
    ever runs. The `enum` is purely advisory: a well-behaved host can
    validate against it before a round trip.
    """
    return Field(description=description, json_schema_extra={"enum": list(choices)})


# Parameter shapes repeated across several tools, defined once so every tool
# using them stays in sync (DRY) rather than re-typing the same description.
TaskRefArg = Annotated[
    str | int, Field(description="Task id: TASK-<n>, TASK-GLOBAL-<n>, or a bare integer.")
]
FactRefArg = Annotated[
    str | int, Field(description="Fact id: FACT-<n>, FACT-GLOBAL-<n>, or a bare integer.")
]
SessionIdArg = Annotated[
    str | None,
    Field(
        description="Per-conversation session token; defaults to the "
        "server's own session id if omitted."
    ),
]
IsGlobalArg = Annotated[
    bool,
    Field(description="File into the shared global database instead of the local project."),
]
LimitArg = Annotated[
    int,
    Field(
        description="Maximum results, applied to the merged, sorted result "
        "across every scope searched (default 20)."
    ),
]


def scope_filter_field(description: str) -> Any:
    return _enum_field(description, SCOPE_FILTERS)


def project_db_path(config: ServerConfig) -> Path | None:
    """The resolved project's already-known db path, used verbatim by
    `corvee_context(project_db_path=...)` instead of `project_root=...`
    so a tool call never re-walks the filesystem to `.corvee/config.toml`
    and re-parses it -- `config.project` is already a fully-resolved
    `ProjectConfig` (TASK-37).
    """
    return config.project.db_path if config.project else None


def session_id_for(config: ServerConfig, session_id: str | None) -> str:
    """A write tool's own `session_id` argument, if given, else the
    server's default (§10.1) -- never `None`, unlike the CLI's own
    optional `--session-id`. Falling all the way through to `None` here
    would make the argument's own default indistinguishable from a caller
    that genuinely wants no session id, and would defeat the server
    default `resolve_server_session_id` exists to provide.
    """
    return session_id or config.session_id


def validate_scope_filter(scope: str) -> ScopeFilter:
    if scope not in SCOPE_FILTERS:
        raise UsageError(
            "invalid_scope", f"invalid scope {scope!r}: expected one of {SCOPE_FILTERS}"
        )
    return scope


def write_context(config: ServerConfig, ref: str | int) -> tuple[Any, Any]:
    """Parse `ref`, check its scope is available on this server, and return
    (parsed_ref, an un-entered corvee_context(write=True, ...)) for the
    caller to `with`. Kept separate from entering the context so a tool
    that needs to run more than one write against the same transaction
    (`task_block`) can still do so under one `with` block.
    """
    parsed = parse_task_ref(str(ref))
    require_scope_available(config, parsed.scope)
    db_path = project_db_path(config) if parsed.scope == "local" else None
    return parsed, corvee_context(
        write=True, scope=parsed.scope, actor=config.actor, project_db_path=db_path
    )
