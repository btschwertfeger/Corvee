#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio
import json
import threading
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp.types import CallToolResult, TextContent

from corvee.errors import ClaimConflictError, GuardViolationError
from corvee.mcp.dispatch import UNCLAIM_CONFLICT_HINT, run_tool
from corvee.mcp.worker import DbWorker


def _run_and_expect_error(fn: Any) -> CallToolResult:
    """Run `fn` through `run_tool` and narrow the result to a `CallToolResult`,
    which every test in this module expects since it only ever calls
    error-raising `fn`s -- keeps the narrowing assertion in one place instead
    of repeated in every test.
    """
    worker = DbWorker()
    try:
        result = asyncio.run(run_tool(worker, fn))
    finally:
        worker.close()
    assert isinstance(result, CallToolResult)
    return result


def _text(result: CallToolResult) -> str:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


class TestRunToolSuccess:
    def test_returns_the_fn_result_unchanged(self) -> None:
        """A successful call's return value passes through untouched, letting
        the SDK's own auto-conversion build the tool result -- run_tool only
        ever intervenes on the error path.
        """
        worker = DbWorker()
        try:
            result = asyncio.run(run_tool(worker, lambda: {"id": "TASK-1"}))
        finally:
            worker.close()
        assert result == {"id": "TASK-1"}

    def test_runs_fn_on_the_worker_thread(self) -> None:
        """fn actually executes off the caller's thread -- run_tool doesn't
        bypass DbWorker's off-loop guarantee.
        """
        worker = DbWorker()
        try:
            caller_thread = threading.get_ident()
            worker_thread = asyncio.run(run_tool(worker, threading.get_ident))
        finally:
            worker.close()
        assert worker_thread != caller_thread


class TestRunToolCorveeError:
    def test_claim_conflict_becomes_an_is_error_result_with_exit_code_and_hint(self) -> None:
        """A CorveeError raised inside fn becomes a CallToolResult with
        is_error=True, exit_code added to the error body, and the same
        content in both structured_content and the text content block. A
        claim_conflict also carries an MCP-phrased `hint` in addition to
        (not instead of) the shared CLI-facing `message` -- see
        `_error_result`'s own docstring for why the message itself is
        never rewritten.
        """

        def _raise() -> None:
            raise ClaimConflictError("claim_conflict", "TASK-14 is claimed by agent:other")

        result = _run_and_expect_error(_raise)

        assert result.is_error is True
        assert result.structured_content == {
            "error": {
                "code": "claim_conflict",
                "message": "TASK-14 is claimed by agent:other",
                "exit_code": 4,
                "hint": "call task_claim(force=true) on this ref to steal the claim, then retry",
            }
        }
        assert len(result.content) == 1
        assert json.loads(_text(result)) == result.structured_content

    def test_claim_conflict_hint_can_be_overridden(self) -> None:
        """A caller (`task_unclaim`) can pass its own `claim_conflict_hint`
        instead of the default `task_claim(force=true)` one, since stealing
        the claim there would reassign it to the caller instead of
        releasing it.
        """

        def _raise() -> None:
            raise ClaimConflictError("claim_conflict", "TASK-14 is claimed by agent:other")

        worker = DbWorker()
        try:
            result = asyncio.run(
                run_tool(worker, _raise, claim_conflict_hint=UNCLAIM_CONFLICT_HINT)
            )
        finally:
            worker.close()

        assert isinstance(result, CallToolResult)
        assert result.structured_content is not None
        assert result.structured_content["error"]["hint"] == UNCLAIM_CONFLICT_HINT

    def test_guard_violation_carries_its_extra_fields(self) -> None:
        """A CorveeError's **extra kwargs survive into the error body, exactly
        like `to_json()` already preserves them for the CLI.
        """

        def _raise() -> None:
            raise GuardViolationError(
                "invalid_transition", "cannot move done -> blocked", allowed=["open", "in_progress"]
            )

        result = _run_and_expect_error(_raise)

        assert result.structured_content is not None
        assert result.structured_content["error"]["allowed"] == ["open", "in_progress"]
        assert result.structured_content["error"]["exit_code"] == 5
        assert "hint" not in result.structured_content["error"]


class TestRunToolUnexpectedException:
    def test_unexpected_exception_becomes_internal_error_exit_code_one(self) -> None:
        """Anything that isn't a CorveeError still comes back as a clean
        isError result, never an unhandled exception reaching the caller.
        """

        def _raise() -> None:
            raise ValueError("boom")

        result = _run_and_expect_error(_raise)

        assert result.is_error is True
        assert result.structured_content is not None
        assert result.structured_content["error"]["code"] == "internal_error"
        assert result.structured_content["error"]["exit_code"] == 1
        assert "boom" in result.structured_content["error"]["message"]

    def test_never_leaks_a_raw_traceback(self) -> None:
        """The error body's message never contains traceback text -- only the
        exception's own message, matching the CLI's own internal_error shape.
        """

        def _raise() -> None:
            raise ValueError("boom")

        result = _run_and_expect_error(_raise)

        text = _text(result)
        assert "Traceback" not in text
        assert "test_mcp_dispatch.py" not in text
