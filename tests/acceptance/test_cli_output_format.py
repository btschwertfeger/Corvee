#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from collections.abc import Callable

from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestTaskOutputFormat:
    def test_table_default_shows_only_the_triage_columns(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """With no -o given, `task list` shows id/title/type/priority/state/scope only."""
        add_task("a task")
        result = runner.invoke(cli, ["task", "list"])
        assert "TITLE" in result.output
        assert "STATE" in result.output
        assert "CLAIMED_BY" not in result.output
        assert "CREATED_AT" not in result.output

    def test_wide_restores_the_dropped_columns(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`-o wide` on `task list` shows the columns the default drops."""
        add_task("a task")
        result = runner.invoke(cli, ["task", "list", "-o", "wide"])
        assert "CLAIMED_BY" in result.output
        assert "CREATED_AT" in result.output

    def test_wide_is_rejected_on_a_single_row_command(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """`-o wide` is a usage error on a command with no narrow/wide distinction."""
        result = runner.invoke(cli, ["task", "add", "a task", "--description", "d", "-o", "wide"])
        assert result.exit_code == 2

    def test_wide_is_rejected_on_task_show(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task show` already shows full detail; `-o wide` has nothing to add."""
        task_id = add_task("a task")
        result = runner.invoke(cli, ["task", "show", task_id, "-o", "wide"])
        assert result.exit_code == 2

    def test_wide_is_rejected_on_task_tree(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task tree` has one row shape, not a table with a narrow/wide distinction."""
        task_id = add_task("a task")
        result = runner.invoke(cli, ["task", "tree", task_id, "-o", "wide"])
        assert result.exit_code == 2

    def test_unknown_output_value_is_a_usage_error(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """An unrecognized -o value exits 2, the same as any other bad click.Choice."""
        result = runner.invoke(cli, ["task", "list", "-o", "xml"])
        assert result.exit_code == 2


class TestFactOutputFormat:
    def test_table_default_shows_only_the_triage_columns(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """With no -o given, `fact list` shows id/claim/status/scope only."""
        add_fact("a claim")
        result = runner.invoke(cli, ["fact", "list"])
        assert "CLAIM" in result.output
        assert "STATUS" in result.output
        assert "VERIFIED_BY" not in result.output
        assert "CREATED_AT" not in result.output

    def test_wide_restores_the_dropped_columns(
        self, runner: CliRunner, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """`-o wide` on `fact list` shows the columns the default drops."""
        add_fact("a claim")
        result = runner.invoke(cli, ["fact", "list", "-o", "wide"])
        assert "VERIFIED_BY" in result.output
        assert "CREATED_AT" in result.output

    def test_wide_is_rejected_on_a_single_row_command(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """`-o wide` is a usage error on a command with no narrow/wide distinction."""
        result = runner.invoke(cli, ["fact", "add", "a claim", "-o", "wide"])
        assert result.exit_code == 2


class TestClaimAssignOutputFormat:
    """`claim`/`unclaim`/`start`/`assign`/`unassign` set exactly the columns
    the narrow default drops (claimed_by/claimed_at/assigned_to), so unlike
    other single-row echoes they accept `-o wide` too (§5).
    """

    def test_claim_table_default_hides_who_claimed_it(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """The default table gives no sign a `task claim` call did anything."""
        task_id = add_task("a task")
        result = runner.invoke(cli, ["task", "claim", task_id])
        assert "CLAIMED_BY" not in result.output

    def test_claim_wide_shows_who_claimed_it(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        task_id = add_task("a task")
        result = runner.invoke(cli, ["task", "claim", task_id, "-o", "wide"])
        assert "CLAIMED_BY" in result.output

    def test_assign_wide_shows_the_assignment(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        task_id = add_task("a task")
        result = runner.invoke(
            cli, ["task", "assign", task_id, "--to", "agent:claude", "-o", "wide"]
        )
        assert "ASSIGNED_TO" in result.output


class TestBriefOutputFormat:
    def test_wide_restores_the_dropped_task_columns(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`brief -o wide` renders its task sections with the wide column set too."""
        task_id = add_task("a task")
        runner.invoke(cli, ["task", "claim", task_id])
        result = runner.invoke(cli, ["brief", "-o", "wide"])
        assert "CLAIMED_BY" in result.output

    def test_table_default_omits_the_wide_task_columns(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`brief` with no -o given uses the same narrow default as `task list`."""
        task_id = add_task("a task")
        runner.invoke(cli, ["task", "claim", task_id])
        result = runner.invoke(cli, ["brief"])
        assert "CLAIMED_BY" not in result.output
