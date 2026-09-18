#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import asyncio
import re

import pytest

pytest.importorskip("mcp")

from corvee.config import ProjectConfig
from corvee.mcp.server import ServerConfig, build_instructions, build_server, startup_message


class TestBuildInstructions:
    def test_names_the_resolved_project_path(self, project: ProjectConfig) -> None:
        config = ServerConfig(actor="agent:test", project=project, session_id="sess-1")
        instructions = build_instructions(config)
        assert str(project.root) in instructions

    def test_mentions_every_registered_tool_by_name(self, project: ProjectConfig) -> None:
        """The instructions string is handwritten, not generated from the
        live tool list -- it's built before any tool is registered (it's
        a constructor argument to MCPServer itself). Nothing stops it
        drifting out of sync with the tools actually registered, so this
        test ties the two together directly.
        """
        config = ServerConfig(actor="agent:test", project=project, session_id="sess-1")
        instructions = build_instructions(config)
        app, worker = build_server(config)
        try:
            tool_names = {tool.name for tool in asyncio.run(app.list_tools())}
        finally:
            worker.close()
        missing = {
            name for name in tool_names if not re.search(rf"\b{re.escape(name)}\b", instructions)
        }
        assert missing == set()

    def test_explains_global_only_mode_when_no_project(self) -> None:
        config = ServerConfig(actor="agent:test", project=None, session_id="sess-1")
        instructions = build_instructions(config)
        assert "global-only mode" in instructions
        assert "is_global: true" in instructions


class TestStartupMessage:
    def test_names_the_resolved_project_path(self, project: ProjectConfig) -> None:
        config = ServerConfig(actor="agent:test", project=project, session_id="sess-1")
        message = startup_message(config)
        assert str(project.root) in message

    def test_names_the_actor_in_project_mode_too(self, project: ProjectConfig) -> None:
        """Global-only mode's line already names the actor (every write it
        makes gets attributed to it); project mode's own line never did,
        even though the same is just as true there (TASK-39).
        """
        config = ServerConfig(actor="agent:distinctive-actor", project=project, session_id="sess-1")
        message = startup_message(config)
        assert "agent:distinctive-actor" in message

    def test_explains_global_only_mode_when_no_project(self) -> None:
        config = ServerConfig(actor="agent:test", project=None, session_id="sess-1")
        message = startup_message(config)
        assert "global-only mode" in message


class TestBuildServerPrintsStartupMessageToStderr:
    def test_project_mode_prints_the_resolved_project_to_stderr_not_stdout(
        self, project: ProjectConfig, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = ServerConfig(actor="agent:test", project=project, session_id="sess-1")
        _, worker = build_server(config)
        try:
            captured = capsys.readouterr()
            assert str(project.root) in captured.err
            assert captured.out == ""
        finally:
            worker.close()

    def test_global_only_mode_prints_the_explanation_to_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = ServerConfig(actor="agent:test", project=None, session_id="sess-1")
        _, worker = build_server(config)
        try:
            captured = capsys.readouterr()
            assert "global-only mode" in captured.err
            assert captured.out == ""
        finally:
            worker.close()
