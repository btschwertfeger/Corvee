#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from collections.abc import Callable

from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestTaskListAfter:
    def test_pages_through_the_backlog(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--after <id> --limit <n> composes into a stable, non-overlapping next page."""
        ids = [add_task(f"t{i}") for i in range(5)]
        # Fixed order is priority desc, created_at desc, id desc — newest first.
        expected = list(reversed(ids))

        first_page = json.loads(
            runner.invoke(cli, ["task", "list", "--limit", "2", "--fields", "id", "--json"]).output
        )
        assert [t["id"] for t in first_page] == expected[:2]

        second_page = json.loads(
            runner.invoke(
                cli,
                [
                    "task",
                    "list",
                    "--after",
                    first_page[-1]["id"],
                    "--limit",
                    "2",
                    "--fields",
                    "id",
                    "--json",
                ],
            ).output
        )
        assert [t["id"] for t in second_page] == expected[2:4]

    def test_after_the_last_task_is_empty(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        task_id = add_task("only")
        result = runner.invoke(cli, ["task", "list", "--after", task_id, "--json"])
        assert json.loads(result.output) == []

    def test_missing_cursor_id_is_not_found(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        result = runner.invoke(cli, ["task", "list", "--after", "TASK-999", "--json"])
        assert result.exit_code == 3


class TestTaskReadyAfter:
    def test_pages_through_ready_tasks(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        ids = [add_task(f"t{i}") for i in range(3)]
        expected = list(reversed(ids))

        first_page = json.loads(
            runner.invoke(cli, ["task", "ready", "--limit", "1", "--fields", "id", "--json"]).output
        )
        assert [t["id"] for t in first_page] == expected[:1]

        second_page = json.loads(
            runner.invoke(
                cli,
                ["task", "ready", "--after", first_page[0]["id"], "--fields", "id", "--json"],
            ).output
        )
        assert [t["id"] for t in second_page] == expected[1:]


class TestTaskSearchAfter:
    def test_pages_through_search_results(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        ids = [add_task(f"needle {i}") for i in range(3)]
        expected = list(reversed(ids))

        first_page = json.loads(
            runner.invoke(
                cli, ["task", "search", "needle", "--limit", "1", "--fields", "id", "--json"]
            ).output
        )
        assert [t["id"] for t in first_page] == expected[:1]

        second_page = json.loads(
            runner.invoke(
                cli,
                [
                    "task",
                    "search",
                    "needle",
                    "--after",
                    first_page[0]["id"],
                    "--fields",
                    "id",
                    "--json",
                ],
            ).output
        )
        assert [t["id"] for t in second_page] == expected[1:]
