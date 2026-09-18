#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import builtins
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig, bootstrap_project

# Isolates every test in this module from whatever real corvee project might
# exist at the actual process cwd (this repository's own self-tracking
# .corvee/, for one) -- the same isolation test_cli_no_project.py's
# `_no_project` fixture already provides for the plain CLI. Tests that need
# a real project use the `project` fixture, which chdirs to its own
# tmp_path and so overrides this safely.


@pytest.fixture(autouse=True)
def _no_project_at_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


class _FakeApp:
    """Stands in for the real MCPServer: records that .run() was reached
    instead of actually starting a stdio transport, which would block on
    real I/O the acceptance-test layer has no business exercising (that's
    the e2e test's job).
    """

    def __init__(self) -> None:
        self.run_calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> None:
        self.run_calls.append(kwargs)


class _FakeWorker:
    """Stands in for DbWorker: records that close() was reached."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def captured_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patches `corvee.mcp.server.build_server` to capture the ServerConfig
    it was called with and return a `(_FakeApp, _FakeWorker)` pair instead
    of a real MCPServer/DbWorker.

    `serve()`'s own unconditional `import mcp` (serve.py, ahead of the
    part this fixture fakes out) still runs first, so a test using this
    fixture needs the real package importable regardless -- skipped, not
    failed, without the optional `corvee[mcp]` extra installed.
    `TestServeMissingExtra` below covers that path itself, without this
    fixture, by blocking the import rather than relying on it genuinely
    being absent.
    """
    pytest.importorskip("mcp")
    captured: dict[str, Any] = {}
    fake_app = _FakeApp()
    fake_worker = _FakeWorker()

    def _fake_build_server(config: Any) -> tuple[_FakeApp, _FakeWorker]:
        captured["config"] = config
        return fake_app, fake_worker

    monkeypatch.setattr("corvee.mcp.server.build_server", _fake_build_server)
    captured["app"] = fake_app
    captured["worker"] = fake_worker
    return captured


class TestServeActorAndProjectRootResolution:
    def test_no_project_root_and_no_project_at_cwd_gives_global_only_mode(
        self, runner: CliRunner, captured_config: dict[str, Any]
    ) -> None:
        """Omitting --project-root with nothing found at cwd (this module's
        autouse fixture isolates cwd to an empty tmp_path) resolves
        ServerConfig.project to None -- global-only mode.
        """
        result = runner.invoke(cli, ["mcp", "serve"])
        assert result.exit_code == 0
        assert captured_config["config"].project is None
        assert captured_config["app"].run_calls == [{"transport": "stdio"}]

    def test_no_project_root_auto_detects_the_project_at_cwd(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        captured_config: dict[str, Any],
    ) -> None:
        """Omitting --project-root auto-detects the project at cwd, exactly
        like every CLI command's own default -- no flag needed when the
        host spawns the server with cwd set to the project directory.
        """
        result = runner.invoke(cli, ["mcp", "serve"])
        assert result.exit_code == 0
        resolved_project = captured_config["config"].project
        assert isinstance(resolved_project, ProjectConfig)
        assert resolved_project.db_path == project.db_path

    def test_db_worker_is_closed_after_the_server_stops(
        self, runner: CliRunner, captured_config: dict[str, Any]
    ) -> None:
        """The dedicated DB worker thread is shut down once app.run() returns,
        not left dangling after the server process would otherwise exit.
        """
        result = runner.invoke(cli, ["mcp", "serve"])
        assert result.exit_code == 0
        assert captured_config["worker"].closed is True

    def test_project_root_resolves_the_given_path(
        self, runner: CliRunner, tmp_path: Path, captured_config: dict[str, Any]
    ) -> None:
        """--project-root resolves that project, regardless of cwd."""
        init_result = bootstrap_project(tmp_path)
        result = runner.invoke(cli, ["mcp", "serve", "--project-root", str(tmp_path)])
        assert result.exit_code == 0
        project = captured_config["config"].project
        assert isinstance(project, ProjectConfig)
        assert project.db_path == init_result.db_path

    def test_bad_project_root_fails_with_exit_6_not_starting_the_server(
        self, runner: CliRunner, tmp_path: Path, captured_config: dict[str, Any]
    ) -> None:
        """A --project-root that doesn't resolve to a real project refuses to
        start (exit 6, ConfigError), the same failure `resolve_project`
        already raises for the CLI -- no tool calls are ever registered.
        """
        result = runner.invoke(cli, ["mcp", "serve", "--project-root", str(tmp_path / "nope")])
        assert result.exit_code == 6
        error = json.loads(result.output)["error"]
        assert error["code"] == "no_project"
        assert "config" not in captured_config

    def test_actor_flag_wins_over_env(
        self,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        captured_config: dict[str, Any],
    ) -> None:
        """--actor on `mcp serve` itself resolves the same way the CLI's
        global --actor flag does: explicit value wins over $CORVEE_ACTOR.
        """
        monkeypatch.setenv("CORVEE_ACTOR", "agent:env")
        result = runner.invoke(cli, ["mcp", "serve", "--actor", "agent:explicit"])
        assert result.exit_code == 0
        assert captured_config["config"].actor == "agent:explicit"

    def test_without_actor_flag_falls_back_to_env(
        self,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        captured_config: dict[str, Any],
    ) -> None:
        """Omitting --actor falls back to $CORVEE_ACTOR, same as everywhere else."""
        monkeypatch.setenv("CORVEE_ACTOR", "agent:env")
        result = runner.invoke(cli, ["mcp", "serve"])
        assert result.exit_code == 0
        assert captured_config["config"].actor == "agent:env"

    def test_session_id_flag_wins_over_env(
        self,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        captured_config: dict[str, Any],
    ) -> None:
        """--session-id on `mcp serve` resolves the server's default session
        id, same override precedence as --actor.
        """
        monkeypatch.setenv("CORVEE_SESSION_ID", "env-session")
        result = runner.invoke(cli, ["mcp", "serve", "--session-id", "explicit-session"])
        assert result.exit_code == 0
        assert captured_config["config"].session_id == "explicit-session"

    def test_without_session_id_flag_falls_back_to_env(
        self,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        captured_config: dict[str, Any],
    ) -> None:
        monkeypatch.setenv("CORVEE_SESSION_ID", "env-session")
        result = runner.invoke(cli, ["mcp", "serve"])
        assert result.exit_code == 0
        assert captured_config["config"].session_id == "env-session"

    def test_without_session_id_flag_or_env_a_uuid_is_generated(
        self,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        captured_config: dict[str, Any],
    ) -> None:
        """No --session-id, no $CORVEE_SESSION_ID: the server still starts
        with a usable default rather than leaving every write tool with
        nothing to fall back to.
        """
        import uuid

        monkeypatch.delenv("CORVEE_SESSION_ID", raising=False)
        result = runner.invoke(cli, ["mcp", "serve"])
        assert result.exit_code == 0
        assert uuid.UUID(captured_config["config"].session_id)


class TestServeMissingExtra:
    def test_missing_mcp_package_fails_cleanly_not_a_raw_traceback(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without the mcp package installed, `corvee mcp serve` fails with a
        clean, exit-6-shaped error naming the install command -- never a raw
        ImportError traceback.
        """
        real_import = builtins.__import__

        def _blocking_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "mcp" or name.startswith("mcp."):
                raise ModuleNotFoundError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocking_import)

        result = runner.invoke(cli, ["mcp", "serve"])
        assert result.exit_code == 6
        error = json.loads(result.output)["error"]
        assert error["code"] == "mcp_extra_not_installed"
        assert "corvee[mcp]" in error["message"]
        assert "Traceback" not in result.output

    def test_broken_submodule_also_fails_cleanly_not_a_raw_traceback(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The top-level `import mcp` check alone doesn't prove
        `build_server`'s own deferred `from mcp.server.mcpserver import
        MCPServer` will succeed -- a future mcp release that moves or
        removes that submodule must surface the same clean exit 6, not
        an uncaught ImportError falling through to a generic exit 1
        (TASK-36).

        Reproduced with a stand-in `mcp` module already sitting in
        `sys.modules` (so the initial `import mcp` check succeeds
        without transitively loading anything) while
        `mcp.server.mcpserver` is blocked -- against the real installed
        SDK, `import mcp` alone already eagerly loads that submodule as
        a side effect, so blocking it outright would trip the *first*
        check too and this test would prove nothing about the second,
        deferred one this fix actually adds.
        """
        monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
        monkeypatch.delitem(sys.modules, "mcp.server.mcpserver", raising=False)
        monkeypatch.delitem(sys.modules, "mcp.server", raising=False)

        real_import = builtins.__import__

        def _blocking_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "mcp.server.mcpserver":
                raise ModuleNotFoundError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocking_import)

        result = runner.invoke(cli, ["mcp", "serve"])
        assert result.exit_code == 6
        error = json.loads(result.output)["error"]
        assert error["code"] == "mcp_extra_not_installed"
        assert "corvee[mcp]" in error["message"]
        assert "Traceback" not in result.output
