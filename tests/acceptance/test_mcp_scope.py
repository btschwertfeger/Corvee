#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from pathlib import Path

import pytest

from corvee.cli.context import corvee_context
from corvee.config import ProjectConfig
from corvee.constants import Scope
from corvee.db.tasks import TaskFilter, insert_task, list_tasks
from corvee.errors import ConfigError
from corvee.mcp.scope import fetch_merged_for_config, scopes_for_config
from corvee.mcp.server import ServerConfig


class TestScopesForConfig:
    def test_local_scope_with_a_project_returns_local(self, project: ProjectConfig) -> None:
        config = ServerConfig(actor="agent:test", project=project, session_id="sess-server")
        assert scopes_for_config(config, "local") == ("local",)

    def test_local_scope_with_no_project_raises(self) -> None:
        """Explicitly requesting local scope with no project is a real usage
        error, mirroring `cli/scope.py::scopes_for`'s own "requested
        explicitly, keeps failing loudly" rule for --scope local.
        """
        config = ServerConfig(actor="agent:test", project=None, session_id="sess-server")
        with pytest.raises(ConfigError):
            scopes_for_config(config, "local")

    def test_all_scope_with_no_project_and_no_global_db_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A global-only server with nothing filed anywhere merges to nothing,
        not an error -- the same graceful "empty scope" `scopes_for` gives
        the CLI for a merged read with no local project.
        """
        monkeypatch.setenv("CORVEE_GLOBAL_DB", str(tmp_path / "nonexistent" / "corvee.db"))
        config = ServerConfig(actor="agent:test", project=None, session_id="sess-server")
        assert scopes_for_config(config, "all") == ()

    def test_all_scope_with_a_project_includes_local(self, project: ProjectConfig) -> None:
        config = ServerConfig(actor="agent:test", project=project, session_id="sess-server")
        assert "local" in scopes_for_config(config, "all")


def _titles(conn: sqlite3.Connection, scope: Scope) -> list[str]:
    del scope
    return [t.title for t in list_tasks(conn, TaskFilter())]


class TestFetchMergedForConfig:
    def test_merges_local_and_global_scopes(self, project: ProjectConfig) -> None:
        """A scope="all" fetch concatenates results from both databases,
        each opened with the ServerConfig's own actor/project rather than
        anything derived from cwd or click's ambient context.
        """
        config = ServerConfig(actor="agent:test", project=project, session_id="sess-server")
        with corvee_context(scope="local", actor=config.actor, session_id=None) as ctx:
            insert_task(ctx.conn, title="local task", description="d")
        with corvee_context(scope="global", actor=config.actor, session_id=None) as ctx:
            insert_task(ctx.conn, title="global task", description="d")

        titles = fetch_merged_for_config(config, "all", _titles)
        assert sorted(titles) == ["global task", "local task"]

    def test_local_only_scope_excludes_global(self, project: ProjectConfig) -> None:
        config = ServerConfig(actor="agent:test", project=project, session_id="sess-server")
        with corvee_context(scope="local", actor=config.actor, session_id=None) as ctx:
            insert_task(ctx.conn, title="local task", description="d")
        with corvee_context(scope="global", actor=config.actor, session_id=None) as ctx:
            insert_task(ctx.conn, title="global task", description="d")

        assert fetch_merged_for_config(config, "local", _titles) == ["local task"]

    def test_never_calls_resolve_project_reusing_the_cached_project_instead(
        self, project: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`ServerConfig.project` is already a fully-resolved `ProjectConfig`
        (spec §10.1: resolved once at launch); `fetch_merged_for_config`
        must pass its `db_path` straight through rather than re-deriving it
        via a fresh `resolve_project` filesystem walk + TOML re-parse per
        call (TASK-37). Proven by making `resolve_project` itself explode
        if called at all.
        """
        import corvee.cli.context

        def _must_not_be_called(*args: object, **kwargs: object) -> None:
            raise AssertionError(
                "resolve_project was called; the cached project.db_path was not reused"
            )

        monkeypatch.setattr(corvee.cli.context, "resolve_project", _must_not_be_called)

        config = ServerConfig(actor="agent:test", project=project, session_id="sess-server")
        assert fetch_merged_for_config(config, "local", _titles) == []
