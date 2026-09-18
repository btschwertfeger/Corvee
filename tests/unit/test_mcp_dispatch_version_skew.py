#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio

import pytest

pytest.importorskip("mcp")

import corvee.mcp.dispatch as dispatch_module
from corvee.errors import ClaimConflictError, ConfigError
from corvee.mcp.dispatch import _schedule_exit, run_tool
from corvee.mcp.worker import DbWorker


class TestScheduleExitPrintsToStderrFirst:
    def test_prints_the_error_message_and_a_restart_instruction_to_stderr(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A host that is slow to drain the in-flight call's own isError
        result, or that never surfaces a tool result's error body to
        whoever is watching the process, would otherwise see the process
        die 100ms later with nothing in its own logs explaining why.
        """
        monkeypatch.setattr(dispatch_module.os, "_exit", lambda code: None)

        err = ConfigError(
            "schema_too_new",
            "database schema version 5 is newer than this binary supports (version 4)",
            db_schema_version=5,
            binary_schema_version=4,
        )

        async def _call() -> None:
            _schedule_exit(err)
            await asyncio.sleep(0.2)

        asyncio.run(_call())

        captured = capsys.readouterr()
        assert captured.out == ""
        assert err.message in captured.err
        assert "restart" in captured.err


class TestSchemaSkewSchedulesProcessExit:
    def test_schema_too_new_schedules_an_exit_with_the_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A schema-too-new ConfigError (§3.2/§10.1: a newer binary migrated
        the file out from under this still-running server) schedules the
        process to exit, carrying the error itself (not just its exit
        code) so `_schedule_exit` can print `err.message` to stderr before
        the process dies, rather than staying up to repeat the same
        isError for every subsequent call.
        """
        scheduled: list[ConfigError] = []
        monkeypatch.setattr(dispatch_module, "_schedule_exit", scheduled.append)

        def _raise() -> None:
            raise ConfigError(
                "schema_too_new",
                "db schema is newer than this binary supports",
                db_schema_version=5,
                binary_schema_version=4,
            )

        worker = DbWorker()
        try:
            asyncio.run(run_tool(worker, _raise))
        finally:
            worker.close()

        assert len(scheduled) == 1
        assert scheduled[0].code == "schema_too_new"
        assert scheduled[0].exit_code == 6

    def test_other_config_errors_do_not_schedule_an_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the schema-too-new case is fatal -- an ordinary no_project
        ConfigError (a bad --project-root, or a local-scope call in
        global-only mode) is not, and must not kill the server.
        """
        scheduled: list[int] = []
        monkeypatch.setattr(dispatch_module, "_schedule_exit", scheduled.append)

        def _raise() -> None:
            raise ConfigError("no_project", "no project in scope")

        worker = DbWorker()
        try:
            asyncio.run(run_tool(worker, _raise))
        finally:
            worker.close()

        assert scheduled == []

    def test_non_config_corvee_errors_do_not_schedule_an_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scheduled: list[int] = []
        monkeypatch.setattr(dispatch_module, "_schedule_exit", scheduled.append)

        def _raise() -> None:
            raise ClaimConflictError("claim_conflict", "held by someone else")

        worker = DbWorker()
        try:
            asyncio.run(run_tool(worker, _raise))
        finally:
            worker.close()

        assert scheduled == []
