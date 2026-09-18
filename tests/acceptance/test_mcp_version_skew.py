#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio
import sqlite3

import pytest

pytest.importorskip("mcp")

from mcp.types import CallToolResult

from corvee.config import ProjectConfig
from corvee.db.schema import CURRENT_SCHEMA_VERSION
from corvee.errors import ConfigError
from corvee.mcp.server import build_server
from corvee.mcp.server_config import ServerConfig


class TestVersionSkewMidSession:
    def test_schema_migrated_ahead_by_a_newer_binary_gives_a_clean_isError_and_schedules_exit(
        self, project: ProjectConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulates §3.2/§10.1's exact scenario: another (newer) corvee
        process migrated this project's database past what the still-running
        server's binary understands. The next call must not crash with a
        raw exception, must come back as the documented exit-6 isError, and
        must schedule the process to exit rather than staying up to repeat
        it forever.
        """
        conn = sqlite3.connect(project.db_path)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (CURRENT_SCHEMA_VERSION + 1, "2026-01-01T00:00:00.000Z"),
        )
        conn.commit()
        conn.close()

        scheduled: list[ConfigError] = []
        import corvee.mcp.dispatch as dispatch_module

        monkeypatch.setattr(dispatch_module, "_schedule_exit", scheduled.append)

        config = ServerConfig(actor="agent:test", project=project, session_id="sess-server")
        server, worker = build_server(config)
        try:
            result = asyncio.run(server.call_tool("brief", {}))
        finally:
            worker.close()

        assert isinstance(result, CallToolResult)
        assert result.is_error
        assert result.structured_content is not None
        assert result.structured_content["error"]["code"] == "schema_too_new"
        assert result.structured_content["error"]["exit_code"] == 6
        assert len(scheduled) == 1
        assert scheduled[0].code == "schema_too_new"
        assert scheduled[0].exit_code == 6
