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


class TestReady:
    def test_excludes_claimed_and_blocked(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task ready` returns only unclaimed, unblocked, open tasks."""
        ready_id = add_task("ready one")
        claimed_id = add_task("claimed one")
        runner.invoke(cli, ["task", "claim", claimed_id])

        result = runner.invoke(cli, ["task", "ready", "--json"])
        payload = json.loads(result.output)
        assert [t["id"] for t in payload] == [ready_id]

    def test_label_filter_narrows_the_result(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--label restricts `task ready` to tasks carrying that label."""
        labeled_id = add_task("labeled")
        runner.invoke(cli, ["task", "label", labeled_id, "--add", "api"])
        add_task("unlabeled")

        result = runner.invoke(cli, ["task", "ready", "--label", "api", "--json"])
        payload = json.loads(result.output)
        assert [t["id"] for t in payload] == [labeled_id]

    def test_label_filter_matches_regardless_of_case(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--label API matches a task labeled api, the same as add_label normalizes it."""
        labeled_id = add_task("labeled")
        runner.invoke(cli, ["task", "label", labeled_id, "--add", "API"])

        result = runner.invoke(cli, ["task", "ready", "--label", "API", "--json"])
        payload = json.loads(result.output)
        assert [t["id"] for t in payload] == [labeled_id]

    def test_invalid_label_filter_exits_two(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """--label is normalized the same way as `task label --add`, so a bad pattern exits 2."""
        result = runner.invoke(cli, ["task", "ready", "--label", "has space", "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "invalid_label"

    def test_limit_caps_the_result(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--limit caps the sorted result to the first N, not an arbitrary N."""
        add_task("a")
        b_id = add_task("b")
        result = runner.invoke(cli, ["task", "ready", "--limit", "1", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [b_id]


class TestSearch:
    def test_finds_title_substring(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task search` matches a case-insensitive substring of the title."""
        add_task("Fix the flaky auth test")
        add_task("unrelated task")
        result = runner.invoke(cli, ["task", "search", "flaky auth", "--json"])
        payload = json.loads(result.output)
        assert len(payload) == 1

    def test_include_comments_matches_comment_text(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--include-comments extends the match to comment bodies."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "comment", task_id, "root cause was a stale cache"])

        assert (
            json.loads(runner.invoke(cli, ["task", "search", "stale cache", "--json"]).output) == []
        )

        result = runner.invoke(
            cli, ["task", "search", "stale cache", "--include-comments", "--json"]
        )
        assert [t["id"] for t in json.loads(result.output)] == [task_id]

    def test_all_includes_done_and_cancelled(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--all extends the search to done/cancelled tasks, excluded by default."""
        done_id = add_task("archived flaky fix")
        runner.invoke(cli, ["task", "update", done_id, "--state", "done"])

        assert json.loads(runner.invoke(cli, ["task", "search", "flaky", "--json"]).output) == []

        result = runner.invoke(cli, ["task", "search", "flaky", "--all", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [done_id]

    def test_limit_caps_the_result(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--limit caps the sorted result to the first N, not an arbitrary N."""
        add_task("matching one")
        second_id = add_task("matching two")
        result = runner.invoke(cli, ["task", "search", "matching", "--limit", "1", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [second_id]


class TestMine:
    def test_lists_claimed_tasks_with_last_comment(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task mine` lists tasks the current actor holds, each with its most recent comment."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "claim", task_id])
        runner.invoke(cli, ["task", "comment", task_id, "starting now"])

        result = runner.invoke(cli, ["task", "mine", "--json"])
        payload = json.loads(result.output)
        assert payload[0]["id"] == task_id
        assert payload[0]["last_comment"]["body"] == "starting now"

    def test_last_comment_is_null_when_no_comments(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A claimed task with no comments yet reports last_comment as null, not missing."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "claim", task_id])
        result = runner.invoke(cli, ["task", "mine", "--json"])
        payload = json.loads(result.output)
        assert payload[0]["last_comment"] is None

    def test_fields_projection(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--fields trims the result to the requested columns, like list/ready/search."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "claim", task_id])
        result = runner.invoke(cli, ["task", "mine", "--fields", "id,title", "--json"])
        payload = json.loads(result.output)
        assert payload == [{"id": task_id, "title": "task"}]

    def test_limit_caps_the_result(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--limit caps the sorted result to the first N, not an arbitrary N."""
        first = add_task("first")
        second = add_task("second")
        runner.invoke(cli, ["task", "claim", first])
        runner.invoke(cli, ["task", "claim", second])
        result = runner.invoke(cli, ["task", "mine", "--limit", "1", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [second]

    def test_help_mentions_assigned_but_unclaimed_tasks(self, runner: CliRunner) -> None:
        """--help documents that `mine` also returns assigned-but-unclaimed tasks (§4.4)."""
        result = runner.invoke(cli, ["task", "mine", "--help"])
        assert "assigned" in result.output


class TestComment:
    def test_appears_in_show_timeline(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A comment shows up as a "comment"-kind event in `task show`'s timeline."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "comment", task_id, "a note"])
        result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        payload = json.loads(result.output)
        comment_events = [e for e in payload[0]["events"] if e["kind"] == "comment"]
        assert len(comment_events) == 1
        assert comment_events[0]["body"] == "a note"

    def test_show_no_events_reports_omitted_count(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--no-events drops the timeline but still reports how many events were omitted."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "comment", task_id, "note one"])
        runner.invoke(cli, ["task", "comment", task_id, "note two"])
        result = runner.invoke(cli, ["task", "show", task_id, "--no-events", "--json"])
        payload = json.loads(result.output)
        assert payload[0]["events"] == []
        # created (from add_task) + the two comments
        assert payload[0]["events_omitted"] == 3
