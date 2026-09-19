#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
import threading
from pathlib import Path

import pytest

from corvee.cli.context import corvee_context
from corvee.config import ProjectConfig
from corvee.db.connection import open_connection


class TestCorveeContextActorSessionOverrides:
    def test_actor_override_wins_over_env(
        self, project: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit actor override passed to corvee_context wins over
        $CORVEE_ACTOR, the same way the CLI's --actor flag does.
        """
        monkeypatch.setenv("CORVEE_ACTOR", "agent:env")
        with corvee_context(write=False, actor="agent:explicit") as ctx:
            assert ctx.actor == "agent:explicit"

    def test_session_id_override_wins_over_env(
        self, project: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit session_id override wins over $CORVEE_SESSION_ID."""
        monkeypatch.setenv("CORVEE_SESSION_ID", "env-session")
        with corvee_context(write=False, session_id="explicit-session") as ctx:
            assert ctx.session_id == "explicit-session"

    def test_without_override_behavior_is_unchanged(
        self, project: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Omitting actor/session_id keeps resolving from env exactly as before --
        this override is purely additive to existing CLI behavior.
        """
        monkeypatch.setenv("CORVEE_ACTOR", "agent:env")
        monkeypatch.delenv("CORVEE_SESSION_ID", raising=False)
        with corvee_context(write=False) as ctx:
            assert ctx.actor == "agent:env"
            assert ctx.session_id is None

    def test_actor_and_session_id_resolve_correctly_with_no_click_context(
        self, project: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact regression this override exists to fix: resolve_actor()/
        resolve_session_id() with no override fall through to click's
        thread-local context, which is absent in a plain worker thread (the
        shape an MCP tool handler's DB work runs in). Called from such a
        thread with an explicit override, corvee_context must still resolve
        the override, not silently fall back to $CORVEE_ACTOR/human:$USER.
        """
        monkeypatch.setenv("CORVEE_ACTOR", "agent:env")
        result: dict[str, str | None] = {}
        error: list[BaseException] = []

        def _run() -> None:
            try:
                with corvee_context(
                    write=False, actor="agent:worker-thread", session_id="sess-9"
                ) as ctx:
                    result["actor"] = ctx.actor
                    result["session_id"] = ctx.session_id
            except BaseException as exc:
                error.append(exc)

        thread = threading.Thread(target=_run)
        thread.start()
        thread.join()

        assert not error
        assert result == {"actor": "agent:worker-thread", "session_id": "sess-9"}


class TestCorveeContextProjectDbPathOverride:
    def test_given_db_path_is_used_verbatim_without_re_resolving(
        self, project: ProjectConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`project_db_path`, given, is used as-is instead of calling
        `resolve_project()` at all (TASK-37) -- proven here by running from
        a directory with no project in it whatsoever (which would raise
        `ConfigError` if `resolve_project()` were still reached, since it
        resolves from cwd) while `project_db_path` names the real,
        already-known database. The call must still succeed, and must open
        the given path, not fall back to resolving from cwd.
        """
        empty_dir = tmp_path / "no-project-here"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)

        with corvee_context(write=False, project_db_path=project.db_path) as ctx:
            assert ctx.db_path == project.db_path

    def test_omitted_falls_back_to_resolving_from_cwd(self, project: ProjectConfig) -> None:
        """Omitting project_db_path keeps the existing cwd-based resolution
        path exactly as before -- purely additive.
        """
        with corvee_context(write=False) as ctx:
            assert ctx.db_path == project.db_path


def _open_with_short_busy_timeout(db_path: Path) -> sqlite3.Connection:
    """A real connection with a tiny busy_timeout, so a lock-contention test
    does not spend the production 5s waiting for the lock (TASK-27)."""
    conn = open_connection(db_path)
    conn.execute("PRAGMA busy_timeout = 25")
    return conn


class TestCorveeContextBeginFailureIsNotMasked:
    def test_failed_begin_surfaces_its_own_error_not_a_rollback_error(
        self, project: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A BEGIN IMMEDIATE that loses the lock race must propagate
        "database is locked", not a follow-up "cannot rollback - no
        transaction is active" from rolling back a transaction that never
        opened (TASK-27).
        """
        blocker = sqlite3.connect(project.db_path)
        blocker.execute("BEGIN EXCLUSIVE")
        monkeypatch.setattr("corvee.cli.context.open_connection", _open_with_short_busy_timeout)
        try:
            with (
                pytest.raises(sqlite3.OperationalError) as excinfo,
                corvee_context(write=True),
            ):
                pytest.fail("the context body must not run")
        finally:
            blocker.rollback()
            blocker.close()

        assert "database is locked" in str(excinfo.value)
        assert "cannot rollback" not in str(excinfo.value)
