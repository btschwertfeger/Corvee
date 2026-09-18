#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio
import json
import os
import sys
from collections.abc import Callable
from typing import TypeVar

from mcp.types import CallToolResult, TextContent

from corvee.errors import ConfigError, CorveeError
from corvee.mcp.worker import DbWorker

T = TypeVar("T")

_SCHEMA_TOO_NEW = "schema_too_new"
_CLAIM_CONFLICT = "claim_conflict"
_CLAIM_CONFLICT_HINT = "call task_claim(force=true) on this ref to steal the claim, then retry"


def _schedule_exit(err: ConfigError) -> None:
    """Terminate the process shortly after the in-flight call's response is
    sent, rather than staying up to repeat the same `isError` for every
    subsequent call for the rest of the process's life (spec §10.1): once a
    newer binary has migrated the schema out from under this still-running
    server, nothing this process does will ever succeed again, and a
    restart (which most MCP hosts already do on a crashed stdio server)
    picks up the current binary and proceeds normally. `call_later` rather
    than exiting immediately gives the SDK a moment to finish writing this
    call's own response to stdout first.

    Prints `err.message` to stderr before scheduling the exit, not after:
    the in-flight tool call's own `isError` result already names this to
    whichever caller made that one call, but a host that is slow to drain
    the response, or that never surfaces a tool result's error body to
    whoever is watching the process, would otherwise see the process die
    100ms later with nothing in its own logs explaining why.
    """
    print(f"corvee mcp serve: {err.message}; restart the server", file=sys.stderr)
    asyncio.get_running_loop().call_later(0.1, os._exit, err.exit_code)


def _error_result(err: CorveeError) -> CallToolResult:
    """Build a clean, prefix-free `isError` tool result from a `CorveeError`.

    Raising `mcp.server.mcpserver.exceptions.ToolError` instead would work
    for `is_error=True`, but the SDK prefixes its message with
    "Error executing tool <name>: ", contaminating a JSON body a caller
    wants to parse directly. Returning a `CallToolResult` from the tool
    function itself is passed through unchanged by the SDK's own result
    conversion (`FuncMetadata.convert_result`), which is what this relies
    on instead.

    The body is `err.to_json()` plus one field it does not carry today:
    `exit_code`. The CLI signals severity through the process's own exit
    status; an MCP tool result has no equivalent, so this is the one
    addition needed for a caller to tell a claim conflict (4) from a guard
    violation (5) without string-matching `code` (spec §10.2).

    A `claim_conflict` also gets a second addition, `hint`: `err.message`
    is the one shared string `db/tasks.py::_claim_conflict` builds for
    every caller, CLI included, and says "use --force to steal the claim"
    -- a CLI flag, meaningless to an MCP caller and not something this
    function changes, since doing so would change CLI output nobody asked
    to change. `hint` says the same thing in MCP's own terms instead,
    additive rather than a replacement.
    """
    body = err.to_json()
    body["error"]["exit_code"] = err.exit_code
    if err.code == _CLAIM_CONFLICT:
        body["error"]["hint"] = _CLAIM_CONFLICT_HINT
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(body))],
        structured_content=body,
        is_error=True,
    )


async def run_tool(worker: DbWorker, fn: Callable[[], T]) -> T:
    """Run `fn` (a tool handler's DB work) on the dedicated worker thread and
    map any failure into a clean `isError` result.

    A `CorveeError` maps to its documented shape (`_error_result`). Anything
    else is a genuine crash: caught here rather than left to escape as a raw
    exception, and reported the same way `CorveeGroup.main()` already
    reports an unexpected error to the CLI -- the exception's own message,
    never a traceback, under `internal_error`/exit code 1.

    A successful call's return value passes through unchanged, for the
    SDK's own auto-conversion to build the tool result from.

    Declared to return `T`, matching every tool function's own declared
    return type (e.g. `-> dict[str, Any]` in `mcp/tools_write.py`/
    `tools_fact.py`/`tools_read.py`), even though the two `except` branches
    below actually return a `CallToolResult`. The SDK's result conversion
    passes a returned `CallToolResult` through unchanged regardless of the
    function's declared type (`FuncMetadata.convert_result`), which is what
    every tool handler relies on for a clean, prefix-free `isError` result
    (spec §10.2) -- but the SDK's own schema generation rejects
    `CallToolResult` inside a declared return-type union, so no type in
    this codebase can honestly say "`T` or `CallToolResult`" the way the
    two `# ty: ignore[invalid-return-type]` markers below silently paper
    over. Centralized here, once, rather than a `cast(T, ...)` at every one
    of the sixteen call sites: the annotation mismatch is real, but it is
    cosmetic, not a runtime risk, and this is the one place that needs to
    say so.
    """
    try:
        return await worker.run(fn)
    except CorveeError as err:
        if isinstance(err, ConfigError) and err.code == _SCHEMA_TOO_NEW:
            _schedule_exit(err)
        return _error_result(err)  # ty: ignore[invalid-return-type]
    except Exception as exc:
        return _error_result(
            CorveeError("internal_error", str(exc))
        )  # ty: ignore[invalid-return-type]
