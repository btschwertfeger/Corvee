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


class TestClaimAndUpdate:
    def test_claim_then_update_by_owner_succeeds(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """The claimant can update a task it holds, and the update keeps the claim."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "claim", task_id])
        result = runner.invoke(cli, ["task", "update", task_id, "--state", "in_progress", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["state"] == "in_progress"
        assert payload[0]["claimed_by"] == "agent:test"

    def test_update_by_other_actor_without_force_is_claim_conflict(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_task: Callable[[str], str],
    ) -> None:
        """Updating a task claimed by a different actor exits 4 without --force."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "claim", task_id])

        monkeypatch.setenv("CORVEE_ACTOR", "agent:other")
        result = runner.invoke(cli, ["task", "update", task_id, "--title", "stolen", "--json"])
        assert result.exit_code == 4
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "claim_conflict"
        assert payload["error"]["claimed_by"] == "agent:test"

    def test_batch_is_all_or_nothing(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A multi-id `task update` that fails on one id leaves every id in the batch untouched."""
        a = add_task("a")
        b = add_task("b")
        runner.invoke(cli, ["task", "update", b, "--state", "done"])  # b is now in a terminal state

        # b: done -> cancelled is not a valid transition (guard violation).
        result = runner.invoke(cli, ["task", "update", a, b, "--state", "cancelled", "--json"])
        assert result.exit_code == 5

        # a must be untouched since the batch rolled back.
        show_result = runner.invoke(cli, ["task", "show", a, "--json"])
        assert json.loads(show_result.output)[0]["state"] == "open"

    def test_reopening_child_of_done_parent_warns(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Reopening a done task whose parent is also done surfaces a warning in the output."""
        parent = add_task("parent")
        child = add_task("child")
        runner.invoke(cli, ["task", "link", parent, child, "--relation", "parent_of"])
        runner.invoke(cli, ["task", "update", child, "--state", "done"])
        runner.invoke(cli, ["task", "update", parent, "--state", "done"])

        result = runner.invoke(cli, ["task", "update", child, "--state", "open", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["state"] == "open"
        assert payload[0]["warnings"] == [f"parent {parent} is done while this task reopened"]

    def test_claim_accepts_multiple_ids_in_one_call(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task claim` batches several ids into one transaction, like `task update`."""
        a = add_task("a")
        b = add_task("b")
        result = runner.invoke(cli, ["task", "claim", a, b, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [t["claimed_by"] for t in payload] == ["agent:test", "agent:test"]

    def test_claim_batch_is_all_or_nothing(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        monkeypatch: pytest.MonkeyPatch,
        add_task: Callable[[str], str],
    ) -> None:
        """A claim conflict on one id in the batch leaves every id in the batch unclaimed."""
        a = add_task("a")
        b = add_task("b")
        monkeypatch.setenv("CORVEE_ACTOR", "agent:other")
        runner.invoke(cli, ["task", "claim", b])  # b is now held by agent:other

        monkeypatch.setenv("CORVEE_ACTOR", "agent:test")
        result = runner.invoke(cli, ["task", "claim", a, b, "--json"])
        assert result.exit_code == 4

        show_result = runner.invoke(cli, ["task", "show", a, "--json"])
        assert json.loads(show_result.output)[0]["claimed_by"] is None


class TestUnclaim:
    def test_releases_claim(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task unclaim` clears claimed_by on a task the caller holds."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "claim", task_id])
        result = runner.invoke(cli, ["task", "unclaim", task_id, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["claimed_by"] is None

    def test_accepts_multiple_ids_in_one_call(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task unclaim` releases a whole batch of claims in one transaction."""
        a = add_task("a")
        b = add_task("b")
        runner.invoke(cli, ["task", "claim", a, b])

        result = runner.invoke(cli, ["task", "unclaim", a, b, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [t["claimed_by"] for t in payload] == [None, None]
