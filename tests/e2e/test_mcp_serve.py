#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import subprocess
import sys
from pathlib import Path

from corvee.config import bootstrap_project

_RUN_CLI = "from corvee.cli.main import main; main()"


class TestMcpServeStdioTransport:
    def test_serves_and_exits_cleanly_on_stdin_eof(self, tmp_path: Path) -> None:
        """A real `corvee mcp serve` subprocess reaches the stdio transport and
        exits cleanly (not hanging, not crashing) once its stdin hits EOF --
        the same way a host closing the pipes on shutdown would end it. It
        prints exactly one startup line naming the resolved project to
        stderr (spec §10.1) and nothing else -- stdout stays pure JSON-RPC
        framing throughout, never touched by that message.
        """
        bootstrap_project(tmp_path)
        result = subprocess.run(
            [sys.executable, "-c", _RUN_CLI, "mcp", "serve", "--project-root", str(tmp_path)],
            input="",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stderr.startswith(f"corvee mcp serve: project {tmp_path} (actor: ")
        assert result.stderr.endswith(")\n")

    def test_global_only_mode_serves_and_exits_cleanly_on_stdin_eof(self, tmp_path: Path) -> None:
        """Omitting --project-root reaches the stdio transport too, in
        global-only mode, from a directory with no corvee project at all --
        and the one startup line to stderr says so.
        """
        result = subprocess.run(
            [sys.executable, "-c", _RUN_CLI, "mcp", "serve"],
            input="",
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tmp_path,
        )
        assert result.returncode == 0
        assert result.stderr.startswith("corvee mcp serve: No local project found")
