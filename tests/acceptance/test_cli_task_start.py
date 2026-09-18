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


class TestTaskStart:
    def test_claims_and_moves_an_unclaimed_task_to_in_progress(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task start` on an unclaimed task claims it for the actor and sets
        state=in_progress, in one call.
        """
        task_id = add_task("task")
        result = runner.invoke(cli, ["task", "start", task_id, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["state"] == "in_progress"
        assert payload[0]["claimed_by"] == "agent:test"

    def test_by_other_actor_without_force_is_claim_conflict(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_task: Callable[[str], str],
    ) -> None:
        """Starting a task claimed by a different actor exits 4 without --force."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "claim", task_id])

        monkeypatch.setenv("CORVEE_ACTOR", "agent:other")
        result = runner.invoke(cli, ["task", "start", task_id, "--json"])
        assert result.exit_code == 4
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "claim_conflict"
        assert payload["error"]["claimed_by"] == "agent:test"

    def test_force_steals_a_claim_held_by_another_actor(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_task: Callable[[str], str],
    ) -> None:
        """`--force` steals another actor's claim and starts the task anyway."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "claim", task_id])

        monkeypatch.setenv("CORVEE_ACTOR", "agent:other")
        result = runner.invoke(cli, ["task", "start", task_id, "--force", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["state"] == "in_progress"
        assert payload[0]["claimed_by"] == "agent:other"

    def test_rejects_a_transition_the_current_state_cannot_reach(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A `cancelled` task cannot go straight to `in_progress` (guard violation)."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "update", task_id, "--state", "cancelled"])

        result = runner.invoke(cli, ["task", "start", task_id, "--json"])
        assert result.exit_code == 5

    def test_accepts_multiple_ids_in_one_transaction(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task start` batches several ids, matching `claim`/`update`."""
        a = add_task("a")
        b = add_task("b")
        result = runner.invoke(cli, ["task", "start", a, b, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [t["state"] for t in payload] == ["in_progress", "in_progress"]
        assert [t["claimed_by"] for t in payload] == ["agent:test", "agent:test"]

    def test_already_in_progress_is_a_no_op_success(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Starting an already-in_progress task held by the caller succeeds without error."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "start", task_id])
        result = runner.invoke(cli, ["task", "start", task_id, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["state"] == "in_progress"
