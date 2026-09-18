#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from collections.abc import Callable

from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig, global_db_path


class TestTaskShowReferenced:
    def test_mention_in_description_resolves(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """A TASK-<n> mention in another task's description is surfaced."""
        runner.invoke(cli, ["task", "add", "target", "--description", "d", "--json"])
        runner.invoke(
            cli, ["task", "add", "source", "--description", "depends on TASK-1", "--json"]
        )
        result = runner.invoke(cli, ["task", "show", "TASK-2", "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == ["TASK-1"]

    def test_mention_in_comment_body_resolves(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A FACT-<n> mention in a comment is surfaced, not just description text."""
        task_id = add_task("task")
        runner.invoke(cli, ["fact", "add", "requests is Apache-2.0 licensed", "--json"])
        runner.invoke(cli, ["task", "comment", task_id, "verified via FACT-1"])
        result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == ["FACT-1"]

    def test_self_reference_is_excluded(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A task mentioning its own id is not listed as referencing itself."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "comment", task_id, f"as discussed in {task_id}"])
        result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == []

    def test_nonexistent_mention_is_dropped(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A mention that doesn't resolve to a real row is silently dropped."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "comment", task_id, "blocked on TASK-999"])
        result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == []

    def test_duplicate_mentions_are_deduplicated(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """The same id mentioned twice appears once, in order of first appearance."""
        runner.invoke(cli, ["task", "add", "target", "--description", "d", "--json"])
        task_id = add_task("task")
        runner.invoke(cli, ["task", "comment", task_id, "see TASK-1"])
        runner.invoke(cli, ["task", "comment", task_id, "still TASK-1"])
        result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == ["TASK-1"]

    def test_cross_scope_mention_resolves(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A TASK-GLOBAL-<n> mention inside a local task resolves against the
        global database, opened only because that mention was found.
        """
        runner.invoke(
            cli, ["task", "add", "global target", "--description", "d", "--global", "--json"]
        )
        task_id = add_task("local task")
        runner.invoke(cli, ["task", "comment", task_id, "mirrors TASK-GLOBAL-1"])
        result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == ["TASK-GLOBAL-1"]

    def test_cross_scope_mention_that_does_not_exist_does_not_create_the_global_db(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Checking a TASK-GLOBAL-<n> mention against a never-used global database
        must not materialize it (§3.3), the same guarantee a direct
        `task show TASK-GLOBAL-<n>` already has.
        """
        assert not global_db_path().is_file()
        task_id = add_task("local task")
        runner.invoke(cli, ["task", "comment", task_id, "mirrors TASK-GLOBAL-1"])
        result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == []
        assert not global_db_path().is_file()

    def test_plain_text_shows_referenced_line(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Plain-text output includes a referenced: line, like labels:/subtasks:."""
        runner.invoke(cli, ["task", "add", "target", "--description", "d", "--json"])
        task_id = add_task("task")
        runner.invoke(cli, ["task", "comment", task_id, "see TASK-1"])
        result = runner.invoke(cli, ["task", "show", task_id])
        assert "referenced: TASK-1" in result.output

    def test_plain_text_shows_none_placeholder(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A task with no resolvable mentions shows referenced: (none)."""
        task_id = add_task("task")
        result = runner.invoke(cli, ["task", "show", task_id])
        assert "referenced: (none)" in result.output


class TestFactShowReferenced:
    def test_mention_in_claim_resolves(self, runner: CliRunner, project: ProjectConfig) -> None:
        """A TASK-<n> mention in a fact's claim text is surfaced."""
        runner.invoke(cli, ["task", "add", "task", "--description", "d", "--json"])
        runner.invoke(cli, ["fact", "add", "confirmed while working TASK-1", "--json"])
        result = runner.invoke(cli, ["fact", "show", "FACT-1", "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == ["TASK-1"]

    def test_mention_in_proof_resolves(self, runner: CliRunner, project: ProjectConfig) -> None:
        """A mention inside --proof text is surfaced too, not just the claim."""
        runner.invoke(cli, ["task", "add", "task", "--description", "d", "--json"])
        runner.invoke(
            cli, ["fact", "add", "package is MIT", "--proof", "see TASK-1 for the repro", "--json"]
        )
        result = runner.invoke(cli, ["fact", "show", "FACT-1", "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == ["TASK-1"]

    def test_self_reference_is_excluded(self, runner: CliRunner, project: ProjectConfig) -> None:
        """A fact mentioning its own id is not listed as referencing itself."""
        runner.invoke(cli, ["fact", "add", "a claim", "--json"])
        runner.invoke(cli, ["fact", "revise", "FACT-1", "a claim about FACT-1 itself", "--json"])
        result = runner.invoke(cli, ["fact", "show", "FACT-1", "--json"])
        payload = json.loads(result.output)
        assert payload[0]["referenced"] == []
