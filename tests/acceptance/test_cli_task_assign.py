#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from collections.abc import Callable

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestTaskAssign:
    def test_sets_assigned_to_without_claiming(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task assign` routes a task to an actor and leaves it unclaimed (GH#27)."""
        task_id = add_task("task")
        result = runner.invoke(cli, ["task", "assign", task_id, "--to", "agent:claude", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["assigned_to"] == "agent:claude"
        assert payload[0]["claimed_by"] is None

    def test_not_gated_by_an_existing_claim(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_task: Callable[[str], str],
    ) -> None:
        """Assigning a task someone else already claimed succeeds, unlike `update`."""
        task_id = add_task("task")
        monkeypatch.setenv("CORVEE_ACTOR", "agent:other")
        runner.invoke(cli, ["task", "claim", task_id])
        monkeypatch.setenv("CORVEE_ACTOR", "agent:test")

        result = runner.invoke(cli, ["task", "assign", task_id, "--to", "agent:claude", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["assigned_to"] == "agent:claude"
        assert payload[0]["claimed_by"] == "agent:other"

    def test_multiple_ids_apply_in_one_call(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        first = add_task("first")
        second = add_task("second")
        result = runner.invoke(
            cli, ["task", "assign", first, second, "--to", "agent:claude", "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [t["assigned_to"] for t in payload] == ["agent:claude", "agent:claude"]

    def test_empty_target_is_a_usage_error(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        task_id = add_task("task")
        result = runner.invoke(cli, ["task", "assign", task_id, "--to", "   ", "--json"])
        assert result.exit_code == 2

    def test_missing_task_is_not_found(self, runner: CliRunner, project: ProjectConfig) -> None:
        result = runner.invoke(cli, ["task", "assign", "TASK-999", "--to", "agent:claude"])
        assert result.exit_code == 3


class TestTaskUnassign:
    def test_clears_the_assignment(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        task_id = add_task("task")
        runner.invoke(cli, ["task", "assign", task_id, "--to", "agent:claude"])
        result = runner.invoke(cli, ["task", "unassign", task_id, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["assigned_to"] is None

    def test_on_an_unassigned_task_is_a_no_op_success(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        task_id = add_task("task")
        result = runner.invoke(cli, ["task", "unassign", task_id, "--json"])
        assert result.exit_code == 0


class TestTaskListAssignedToFilter:
    def test_narrows_to_the_given_actor(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        routed = add_task("routed")
        add_task("unrouted")
        runner.invoke(cli, ["task", "assign", routed, "--to", "agent:claude"])

        result = runner.invoke(cli, ["task", "list", "--assigned-to", "agent:claude", "--json"])
        payload = json.loads(result.output)
        assert [t["id"] for t in payload] == [routed]


class TestTaskMineIncludesAssignments:
    def test_includes_unclaimed_tasks_assigned_to_the_actor(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`mine` surfaces work routed to the calling actor even before it's claimed."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "assign", task_id, "--to", "agent:test"])

        result = runner.invoke(cli, ["task", "mine", "--json"])
        payload = json.loads(result.output)
        assert [t["id"] for t in payload] == [task_id]

    def test_does_not_include_a_task_assigned_to_someone_else(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        task_id = add_task("task")
        runner.invoke(cli, ["task", "assign", task_id, "--to", "agent:other"])

        result = runner.invoke(cli, ["task", "mine", "--json"])
        assert json.loads(result.output) == []
