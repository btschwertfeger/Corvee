#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3

import pytest

from corvee.cli.context import corvee_context
from corvee.config import ProjectConfig
from corvee.constants import Scope
from corvee.db.tasks import TaskFilter, insert_task, list_tasks
from corvee.mcp.scope import fetch_merged_for_config
from corvee.mcp.server_config import ServerConfig


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

        def _must_not_be_called(*args: object, **kwargs: object) -> None:
            raise AssertionError(
                "resolve_project was called; the cached project.db_path was not reused"
            )

        monkeypatch.setattr("corvee.cli.context.resolve_project", _must_not_be_called)

        config = ServerConfig(actor="agent:test", project=project, session_id="sess-server")
        assert fetch_merged_for_config(config, "local", _titles) == []
