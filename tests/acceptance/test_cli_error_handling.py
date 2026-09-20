#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json

import click
from click.testing import CliRunner

from corvee import __version__
from corvee.cli.main import cli
from corvee.config import ProjectConfig
from corvee.db.schema import CURRENT_SCHEMA_VERSION
from corvee.errors import NotFoundError


class TestHelpAndVersion:
    def test_help_exits_zero(self, runner: CliRunner) -> None:
        """`corvee --help` exits 0 and mentions the tool name."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "corvee" in result.output

    def test_version_reports_package_and_schema_version(self, runner: CliRunner) -> None:
        """`corvee --version` prints both the package version and the schema version."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output
        assert str(CURRENT_SCHEMA_VERSION) in result.output

    def test_help_and_version_write_plain_text_not_json_error(self, runner: CliRunner) -> None:
        """--help and --version are plain-text success paths, not the JSON error shape."""
        help_result = runner.invoke(cli, ["--help"])
        assert help_result.stderr == ""

        version_result = runner.invoke(cli, ["--version"])
        assert version_result.stderr == ""


class TestConfigProblems:
    def test_a_write_against_a_read_only_database_exits_six(
        self, project: ProjectConfig, runner: CliRunner
    ) -> None:
        """A database file this process cannot write to is a project problem (exit 6).

        SQLite only reports it once a statement actually writes, past the point
        `open_connection` can see it, so the translation happens around the
        command body in `corvee_context` instead.
        """
        project.db_path.chmod(0o444)
        try:
            result = runner.invoke(cli, ["task", "add", "x", "--description", "d", "--json"])
        finally:
            project.db_path.chmod(0o644)

        assert result.exit_code == 6
        assert result.stdout == ""
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "unusable_database"
        assert payload["error"]["path"] == str(project.db_path)


class TestErrorHandling:
    def test_corvee_error_from_a_command_emits_json_error_and_exit_code(
        self, runner: CliRunner
    ) -> None:
        """A raised CorveeError is routed into the documented JSON-on-stderr shape."""

        @cli.command(name="boom-cmd")
        def _boom() -> None:
            raise NotFoundError("task_not_found", "no such task", task_id="TASK-99")

        try:
            result = runner.invoke(cli, ["boom-cmd"])
            assert result.exit_code == 3
            assert result.stdout == ""
            payload = json.loads(result.stderr)
            assert payload == {
                "error": {
                    "code": "task_not_found",
                    "message": "no such task",
                    "task_id": "TASK-99",
                },
            }
        finally:
            del cli.commands["boom-cmd"]

    def test_click_abort_exits_one(self, runner: CliRunner) -> None:
        """A raised click.Abort (e.g. an aborted confirmation prompt) exits 1 silently,
        not through the internal_error JSON path click.Abort would otherwise fall into
        (it is a RuntimeError subclass and would match the generic except Exception).
        """

        @cli.command(name="abort-cmd")
        def _abort() -> None:
            raise click.Abort

        try:
            result = runner.invoke(cli, ["abort-cmd"])
            assert result.exit_code == 1
            assert result.output == ""
        finally:
            del cli.commands["abort-cmd"]

    def test_click_usage_error_is_also_emitted_as_json(self, runner: CliRunner) -> None:
        """Click's own usage errors (e.g. an unknown subcommand) also emit the JSON error shape."""
        result = runner.invoke(cli, ["no-such-command"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "usage_error"

    def test_internal_error_exits_one_and_emits_json(self, runner: CliRunner) -> None:
        """An unexpected exception from a command exits 1 as an internal_error, not a traceback."""

        @cli.command(name="explode-cmd")
        def _explode() -> None:
            raise ValueError("kaboom")

        try:
            result = runner.invoke(cli, ["explode-cmd"])
            assert result.exit_code == 1
            payload = json.loads(result.stderr)
            assert payload["error"]["code"] == "internal_error"
            assert "kaboom" in payload["error"]["message"]
        finally:
            del cli.commands["explode-cmd"]
