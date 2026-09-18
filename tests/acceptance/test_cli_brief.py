#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import sqlite3
from collections.abc import Callable

from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestBrief:
    def test_empty_project_returns_empty_sections(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A project with nothing claimed, ready, or stale returns empty arrays, not an error."""
        result = runner.invoke(cli, ["brief", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload == {"mine": [], "ready": [], "stale": [], "labels": []}

    def test_combines_mine_ready_and_stale(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        conn: sqlite3.Connection,
        add_task: Callable[[str], str],
    ) -> None:
        """One call surfaces the same rows `task mine`/`task ready`/`task list --stale` would."""
        mine_id = add_task("in progress")
        runner.invoke(cli, ["task", "claim", mine_id])
        runner.invoke(cli, ["task", "update", mine_id, "--state", "in_progress"])

        ready_id = add_task("ready to start")

        stale_id = add_task("stale claim")
        runner.invoke(cli, ["task", "claim", stale_id])
        stale_num = stale_id.removeprefix("TASK-")
        conn.execute(
            "UPDATE tasks SET claimed_at = '2000-01-01T00:00:00.000Z' WHERE id = ?", (stale_num,)
        )
        conn.commit()

        result = runner.invoke(cli, ["brief", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert {t["id"] for t in payload["mine"]} == {stale_id, mine_id}
        assert [t["id"] for t in payload["ready"]] == [ready_id]
        assert [t["id"] for t in payload["stale"]] == [stale_id]

    def test_ready_is_capped_at_five_regardless_of_backlog_size(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """The ready section stays capped even when far more tasks are startable."""
        for i in range(8):
            add_task(f"task {i}")

        result = runner.invoke(cli, ["brief", "--json"])
        payload = json.loads(result.output)
        assert len(payload["ready"]) == 5

    def test_plain_text_omits_empty_sections(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A section with no rows doesn't print a header over an empty table."""
        add_task("ready to start")
        result = runner.invoke(cli, ["brief"])
        assert result.exit_code == 0
        assert "ready:" in result.output
        assert "mine:" not in result.output
        assert "stale:" not in result.output

    def test_plain_text_table_uses_the_narrow_default_fields(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """The description column is dropped by default, like every other list-shaped
        command's table -- a long free-text value would otherwise blow up the
        fixed-width row.
        """
        runner.invoke(
            cli,
            [
                "task",
                "add",
                "ready to start",
                "--description",
                "a long free-text description",
                "--json",
            ],
        )
        result = runner.invoke(cli, ["brief"])
        assert "DESCRIPTION" not in result.output
        assert "a long free-text description" not in result.output

    def test_scope_global_merges_the_global_database(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """--scope behaves like task list's: all merges local and global."""
        runner.invoke(
            cli, ["task", "add", "global task", "--description", "d", "--global", "--json"]
        )
        result = runner.invoke(cli, ["brief", "--json"])
        payload = json.loads(result.output)
        assert [t["id"] for t in payload["ready"]] == ["TASK-GLOBAL-1"]

    def test_labels_shows_existing_vocabulary_with_task_counts(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`labels` surfaces the project's label vocabulary, same shape as `task labels`."""
        task_id = add_task("tagged")
        runner.invoke(cli, ["task", "label", task_id, "--add", "api"])

        result = runner.invoke(cli, ["brief", "--json"])
        payload = json.loads(result.output)
        assert payload["labels"] == [{"name": "api", "task_count": 1}]

    def test_labels_are_not_merged_across_scope(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A global task's labels stay out of `labels`, regardless of --scope (§3.3)."""
        global_result = runner.invoke(
            cli, ["task", "add", "global task", "--description", "d", "--global", "--json"]
        )
        global_id = json.loads(global_result.output)[0]["id"]
        runner.invoke(cli, ["task", "label", global_id, "--add", "global-only"])

        result = runner.invoke(cli, ["brief", "--scope", "all", "--json"])
        payload = json.loads(result.output)
        assert payload["labels"] == []

    def test_plain_text_labels_section(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Plain-text output includes a labels: section when labels exist."""
        task_id = add_task("tagged")
        runner.invoke(cli, ["task", "label", task_id, "--add", "api"])

        result = runner.invoke(cli, ["brief"])
        assert "labels:" in result.output
        assert "api" in result.output
