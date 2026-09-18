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


class TestTaskPurge:
    def test_removes_a_cancelled_task(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A cancelled task is gone from `task show` after purge (GH#25)."""
        task_id = add_task("junk")
        runner.invoke(cli, ["task", "update", task_id, "--state", "cancelled"])

        result = runner.invoke(cli, ["task", "purge", task_id, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["id"] == task_id
        assert payload[0]["state"] == "cancelled"

        show = runner.invoke(cli, ["task", "show", task_id, "--json"])
        assert show.exit_code == 3

    def test_refuses_a_task_that_is_not_cancelled(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        task_id = add_task("junk")
        result = runner.invoke(cli, ["task", "purge", task_id, "--json"])
        assert result.exit_code == 5

    def test_shrinks_doctors_total(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Purging removes the row from doctor's counts, unlike `cancelled` alone."""
        task_id = add_task("junk")
        runner.invoke(cli, ["task", "update", task_id, "--state", "cancelled"])
        before = json.loads(runner.invoke(cli, ["doctor", "--json"]).output)
        assert before["local"]["tasks"]["total"] == 1

        runner.invoke(cli, ["task", "purge", task_id])

        after = json.loads(runner.invoke(cli, ["doctor", "--json"]).output)
        assert after["local"]["tasks"]["total"] == 0

    def test_refuses_a_task_with_a_link(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        a = add_task("a")
        b = add_task("b")
        runner.invoke(cli, ["task", "link", a, b, "--relation", "relates_to"])
        runner.invoke(cli, ["task", "update", a, "--state", "cancelled"])

        result = runner.invoke(cli, ["task", "purge", a, "--json"])
        assert result.exit_code == 5

    def test_multiple_ids_apply_in_one_transaction(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A bad id anywhere in the batch rolls the whole purge back."""
        cancelled = add_task("cancelled")
        runner.invoke(cli, ["task", "update", cancelled, "--state", "cancelled"])
        still_open = add_task("open")

        result = runner.invoke(cli, ["task", "purge", cancelled, still_open, "--json"])
        assert result.exit_code == 5

        show = runner.invoke(cli, ["task", "show", cancelled, "--json"])
        assert show.exit_code == 0

    def test_missing_task_is_not_found(self, runner: CliRunner, project: ProjectConfig) -> None:
        result = runner.invoke(cli, ["task", "purge", "TASK-999"])
        assert result.exit_code == 3
