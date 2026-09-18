#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig, global_db_path


class TestExport:
    def test_to_stdout_is_valid_json(self, runner: CliRunner, project: ProjectConfig) -> None:
        """`export` with no --output writes the whole-project JSON, tasks and facts, to stdout."""
        runner.invoke(cli, ["task", "add", "task one", "--description", "d", "--json"])
        runner.invoke(cli, ["fact", "add", "fact one", "--json"])
        result = runner.invoke(cli, ["export"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["tasks"]) == 1
        assert len(data["facts"]) == 1
        assert "schema_version" in data

    def test_to_file(self, runner: CliRunner, project: ProjectConfig, tmp_path: Path) -> None:
        """--output writes the export document to a file instead of stdout."""
        runner.invoke(cli, ["task", "add", "task one", "--description", "d", "--json"])
        output_file = tmp_path / "backup.json"
        result = runner.invoke(cli, ["export", "--output", str(output_file)])
        assert result.exit_code == 0
        assert result.output == ""
        data = json.loads(output_file.read_text())
        assert len(data["tasks"]) == 1

    def test_scope_global_dumps_the_global_database_only(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """--scope global exports ~/.corvee/corvee.db, not the local project database."""
        runner.invoke(cli, ["task", "add", "local task", "--description", "d", "--json"])
        runner.invoke(
            cli, ["task", "add", "global task", "--description", "d", "--global", "--json"]
        )

        result = runner.invoke(cli, ["export", "--scope", "global"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert [t["title"] for t in data["tasks"]] == ["global task"]


class TestImport:
    def test_round_trip_via_cli(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Exporting a populated project and importing it into a fresh one restores every task."""
        runner.invoke(cli, ["task", "add", "task one", "--description", "d", "--json"])
        runner.invoke(cli, ["task", "add", "task two", "--description", "d", "--json"])
        output_file = tmp_path / "backup.json"
        runner.invoke(cli, ["export", "--output", str(output_file)])

        new_project_dir = tmp_path / "restored"
        new_project_dir.mkdir()
        monkeypatch.chdir(new_project_dir)
        runner.invoke(cli, ["init"])
        result = runner.invoke(cli, ["import", str(output_file), "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert len(payload) == 2

    def test_scope_global_round_trip(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """--scope global on both export and import restores into the global database."""
        runner.invoke(
            cli, ["task", "add", "global task", "--description", "d", "--global", "--json"]
        )
        output_file = tmp_path / "global-backup.json"
        runner.invoke(cli, ["export", "--scope", "global", "--output", str(output_file)])

        # Wipe the global db (a fresh one gets created lazily) and restore into it.
        runner.invoke(cli, ["task", "add", "throwaway", "--description", "d", "--global"])
        global_db_path().unlink()
        result = runner.invoke(cli, ["import", str(output_file), "--scope", "global", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [t["title"] for t in payload] == ["global task"]
        assert payload[0]["id"] == "TASK-GLOBAL-1"
        assert payload[0]["scope"] == "global"

    def test_into_nonempty_project_exits_two(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Importing into a project that already holds tasks exits 2, not a silent merge."""
        runner.invoke(cli, ["task", "add", "existing task", "--description", "d", "--json"])
        output_file = "backup.json"
        runner.invoke(cli, ["export", "--output", output_file])

        result = runner.invoke(cli, ["import", output_file, "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "import_into_nonempty_project"

    def test_malformed_json_exits_two(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """A file that isn't valid JSON exits 2 usage_error, not 1 internal_error."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json")

        result = runner.invoke(cli, ["import", str(bad_file), "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] != "internal_error"

    def test_missing_schema_version_exits_two(
        self, runner: CliRunner, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """A dump missing the required schema_version key exits 2, not 1 internal_error."""
        dump_file = tmp_path / "no-version.json"
        dump_file.write_text(json.dumps({"tasks": [], "facts": []}))

        result = runner.invoke(cli, ["import", str(dump_file), "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] != "internal_error"
