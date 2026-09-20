#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli


@pytest.fixture(autouse=True)
def _in_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


class TestInit:
    def test_creates_project_and_reports_text(self, tmp_path: Path) -> None:
        """`corvee init` creates .corvee/config.toml and reports what it did in plain text."""
        result = CliRunner().invoke(cli, ["init"])
        assert result.exit_code == 0
        assert "config: created" in result.output
        assert (tmp_path / ".corvee" / "config.toml").is_file()

    def test_json_reports_structured_result(self) -> None:
        """`corvee init --json` reports the same result as a structured JSON object.

        .gitignore doesn't exist in a fresh tmp_path, so it's skipped rather than
        created from scratch (GH#29) -- init only ever appends to a .gitignore a
        project already has. The pointer block is reported unconditionally, since
        init never writes AGENTS.md itself.
        """
        result = CliRunner().invoke(cli, ["init", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["config_created"] is True
        assert payload["gitignore_status"] == "skipped"
        assert "This project tracks" in payload["agents_block_local"]
        assert "Projects that have run" in payload["agents_block_global"]

    def test_twice_is_idempotent(self) -> None:
        """Re-running `init` in an already-initialized directory changes nothing and reports so."""
        CliRunner().invoke(cli, ["init"])
        result = CliRunner().invoke(cli, ["init", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["config_created"] is False
        assert payload["gitignore_status"] == "skipped"

    def test_appends_to_an_existing_gitignore(self, tmp_path: Path) -> None:
        """A .gitignore that already exists gets the .corvee/ entry appended."""
        (tmp_path / ".gitignore").write_text("node_modules/\n")
        result = CliRunner().invoke(cli, ["init", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["gitignore_status"] == "appended"
        assert ".corvee/" in (tmp_path / ".gitignore").read_text().splitlines()

    def test_never_creates_a_gitignore_from_scratch(self, tmp_path: Path) -> None:
        """No .gitignore in the directory means init leaves none behind."""
        CliRunner().invoke(cli, ["init"])
        assert not (tmp_path / ".gitignore").exists()

    def test_never_touches_an_existing_agents_md(self, tmp_path: Path) -> None:
        """corvee no longer writes to AGENTS.md; an existing file is left untouched."""
        original = "# Project conventions\n"
        (tmp_path / "AGENTS.md").write_text(original)
        result = CliRunner().invoke(cli, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "AGENTS.md").read_text() == original

    def test_never_creates_an_agents_md_from_scratch(self, tmp_path: Path) -> None:
        """No AGENTS.md in the directory means init leaves none behind (GH#29)."""
        CliRunner().invoke(cli, ["init"])
        assert not (tmp_path / "AGENTS.md").exists()

    def test_prints_both_pointer_blocks_to_paste_in_by_hand(self, tmp_path: Path) -> None:
        """Text output always shows both blocks, whether or not AGENTS.md exists
        here, since init never writes either of them itself.
        """
        (tmp_path / "AGENTS.md").write_text("# Project conventions\n")
        result = CliRunner().invoke(cli, ["init"])
        assert result.exit_code == 0
        assert "This project tracks" in result.output
        assert "Projects that have run" in result.output
        assert "~/.claude/CLAUDE.md" in result.output

    def test_db_path_option_is_written_to_config(self, tmp_path: Path) -> None:
        """--db-path writes the given path into config.toml instead of the default."""
        result = CliRunner().invoke(cli, ["init", "--db-path", "../main/.corvee/corvee.db"])
        assert result.exit_code == 0
        content = (tmp_path / ".corvee" / "config.toml").read_text()
        assert content == 'db_path = "../main/.corvee/corvee.db"\n'

    def test_db_path_holding_a_quote_leaves_a_usable_project(self, tmp_path: Path) -> None:
        """The value reaches config.toml escaped, so the project keeps working.

        Writing it raw produced `db_path = "foo"bar.db"`, which failed `init`
        itself and then every later command in that directory.
        """
        result = CliRunner().invoke(cli, ["init", "--db-path", 'foo"bar.db'])

        assert result.exit_code == 0
        written = (tmp_path / ".corvee" / "config.toml").read_text()
        assert tomllib.loads(written)["db_path"] == 'foo"bar.db'
        assert (tmp_path / ".corvee" / 'foo"bar.db').is_file()
        assert json.loads(CliRunner().invoke(cli, ["task", "list", "--json"]).output) == []

    def test_db_path_is_ignored_on_a_second_init(self, tmp_path: Path) -> None:
        """--db-path on a re-run against an existing config changes nothing."""
        CliRunner().invoke(cli, ["init"])
        before = (tmp_path / ".corvee" / "config.toml").read_text()
        result = CliRunner().invoke(cli, ["init", "--db-path", "somewhere/else.db"])
        assert result.exit_code == 0
        assert (tmp_path / ".corvee" / "config.toml").read_text() == before

    def test_help_has_at_least_three_examples(self) -> None:
        """`corvee init --help` carries at least three runnable example lines."""
        result = CliRunner().invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        example_lines = [
            line for line in result.output.splitlines() if line.strip().startswith("corvee ")
        ]
        assert len(example_lines) >= 3
