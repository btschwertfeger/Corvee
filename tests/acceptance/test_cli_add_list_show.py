#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import sqlite3
from collections.abc import Callable

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig


class TestAdd:
    def test_requires_description(self, runner: CliRunner, project: ProjectConfig) -> None:
        """`task add` without --description exits 2; a title alone is not enough."""
        result = runner.invoke(cli, ["task", "add", "Fix the bug", "--json"])
        assert result.exit_code == 2

    def test_rejects_whitespace_only_description(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """--description " " cannot be used to route around the requirement."""
        result = runner.invoke(
            cli, ["task", "add", "Fix the bug", "--description", "   ", "--json"]
        )
        assert result.exit_code == 2

    def test_rejects_whitespace_only_title(self, runner: CliRunner, project: ProjectConfig) -> None:
        """A title of only whitespace is as unidentifiable as an empty one."""
        result = runner.invoke(cli, ["task", "add", "   ", "--description", "d", "--json"])
        assert result.exit_code == 2

    def test_rejects_empty_title(self, runner: CliRunner, project: ProjectConfig) -> None:
        """An empty title exits 2 the same as a whitespace-only one."""
        result = runner.invoke(cli, ["task", "add", "", "--description", "d", "--json"])
        assert result.exit_code == 2

    def test_creates_task_and_returns_it(self, runner: CliRunner, project: ProjectConfig) -> None:
        """`task add` creates an open task, unclaimed, and returns it with the TASK-1 id."""
        result = runner.invoke(
            cli, ["task", "add", "Fix the bug", "--description", "steps to reproduce", "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert len(payload) == 1
        assert payload[0]["title"] == "Fix the bug"
        assert payload[0]["state"] == "open"
        assert payload[0]["claimed_by"] is None
        assert payload[0]["id"] == "TASK-1"

    def test_with_explicit_fields(self, runner: CliRunner, project: ProjectConfig) -> None:
        """--type and --priority on `task add` are stored and echoed back."""
        result = runner.invoke(
            cli,
            [
                "task",
                "add",
                "Investigate",
                "--description",
                "d",
                "--type",
                "bug",
                "--priority",
                "critical",
                "--json",
            ],
        )
        payload = json.loads(result.output)
        assert payload[0]["type"] == "bug"
        assert payload[0]["priority"] == "critical"

    def test_reads_title_from_stdin(self, runner: CliRunner, project: ProjectConfig) -> None:
        """A "-" title argument reads the title from stdin instead of argv."""
        result = runner.invoke(
            cli, ["task", "add", "-", "--description", "d", "--json"], input="From stdin"
        )
        payload = json.loads(result.output)
        assert payload[0]["title"] == "From stdin"

    def test_with_labels(self, runner: CliRunner, project: ProjectConfig) -> None:
        """--label (repeatable) attaches labels to the task in the same call."""
        result = runner.invoke(
            cli,
            [
                "task",
                "add",
                "task",
                "--description",
                "d",
                "--label",
                "API",
                "--label",
                "urgent",
                "--json",
            ],
        )
        task_id = json.loads(result.output)[0]["id"]
        show_result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        assert sorted(json.loads(show_result.output)[0]["labels"]) == ["api", "urgent"]

    def test_with_parent(self, runner: CliRunner, project: ProjectConfig) -> None:
        """--parent <id> links the new task as a child of an existing task."""
        parent_result = runner.invoke(
            cli, ["task", "add", "parent", "--description", "d", "--json"]
        )
        parent_id = json.loads(parent_result.output)[0]["id"]

        child_result = runner.invoke(
            cli, ["task", "add", "child", "--description", "d", "--parent", parent_id, "--json"]
        )
        assert child_result.exit_code == 0

        show_result = runner.invoke(cli, ["task", "show", parent_id, "--json"])
        payload = json.loads(show_result.output)[0]
        assert len(payload["subtasks"]) == 1

    def test_with_missing_parent_exits_three(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """--parent naming a nonexistent task exits 3, and nothing is created."""
        result = runner.invoke(
            cli, ["task", "add", "orphan", "--description", "d", "--parent", "999", "--json"]
        )
        assert result.exit_code == 3
        assert json.loads(runner.invoke(cli, ["task", "list", "--json"]).output) == []


class TestList:
    def test_default_excludes_done_and_cancelled(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """`task list` with no filter returns only open tasks."""
        runner.invoke(cli, ["task", "add", "open task", "--description", "d", "--json"])
        result = runner.invoke(cli, ["task", "list", "--json"])
        payload = json.loads(result.output)
        assert len(payload) == 1
        assert payload[0]["title"] == "open task"

    def test_plain_output_renders_unclaimed_columns_blank(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Without --json, an unclaimed task's CLAIMED_BY/CLAIMED_AT/ASSIGNED_TO
        columns render blank, not the string "None" (TASK-35).
        """
        runner.invoke(cli, ["task", "add", "open task", "--description", "d", "--json"])
        result = runner.invoke(cli, ["task", "list"])
        assert "None" not in result.output

    def test_no_match_returns_empty_array(self, runner: CliRunner, project: ProjectConfig) -> None:
        """An empty backlog returns [] rather than an error."""
        result = runner.invoke(cli, ["task", "list", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_fields_projection(self, runner: CliRunner, project: ProjectConfig) -> None:
        """--fields projects the JSON objects down to exactly the requested keys."""
        runner.invoke(cli, ["task", "add", "task one", "--description", "d", "--json"])
        result = runner.invoke(cli, ["task", "list", "--json", "--fields", "id,title"])
        payload = json.loads(result.output)
        assert payload == [{"id": "TASK-1", "title": "task one"}]

    def test_rejects_unknown_field(self, runner: CliRunner, project: ProjectConfig) -> None:
        """An unrecognized --fields column exits 2 with the unknown_field error code."""
        result = runner.invoke(cli, ["task", "list", "--json", "--fields", "bogus"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "unknown_field"

    def test_ls_is_an_alias_for_list(self, runner: CliRunner, project: ProjectConfig) -> None:
        """`task ls` behaves exactly like `task list`, flags included."""
        runner.invoke(cli, ["task", "add", "task one", "--description", "d", "--json"])
        result = runner.invoke(cli, ["task", "ls", "--json", "--fields", "id,title"])
        assert result.exit_code == 0
        assert json.loads(result.output) == [{"id": "TASK-1", "title": "task one"}]

    def test_blocks_and_blocked_by_filters(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--blocks/--blocked-by find each side of a `blocks` link."""
        blocker = add_task("blocker")
        blocked = add_task("blocked")
        runner.invoke(cli, ["task", "link", blocker, blocked, "--relation", "blocks"])

        blocks_result = runner.invoke(cli, ["task", "list", "--blocks", blocker, "--json"])
        assert [t["id"] for t in json.loads(blocks_result.output)] == [blocked]

        blocked_by_result = runner.invoke(cli, ["task", "list", "--blocked-by", blocked, "--json"])
        assert [t["id"] for t in json.loads(blocked_by_result.output)] == [blocker]

    def test_relates_to_filter_is_symmetric(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--relates-to <id> finds the other end regardless of link insertion order."""
        a = add_task("a")
        b = add_task("b")
        runner.invoke(cli, ["task", "link", a, b, "--relation", "relates_to"])

        result = runner.invoke(cli, ["task", "list", "--relates-to", a, "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [b]

    def test_since_filters_out_tasks_updated_before_the_cutoff(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        conn: sqlite3.Connection,
        add_task: Callable[[str], str],
    ) -> None:
        """--since drops tasks whose updated_at predates the duration cutoff."""
        old_id = add_task("old task")
        recent_id = add_task("recent task")
        conn.execute(
            "UPDATE tasks SET updated_at = '2020-01-01T00:00:00.000Z' WHERE id = ?",
            (int(old_id.removeprefix("TASK-")),),
        )
        conn.commit()

        result = runner.invoke(cli, ["task", "list", "--since", "7d", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [recent_id]

    def test_state_filter_narrows_to_one_state(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--state matches only that state, in place of the open-states default."""
        open_id = add_task("stays open")
        in_progress_id = add_task("in progress")
        done_id = add_task("done")
        runner.invoke(cli, ["task", "update", in_progress_id, "--state", "in_progress"])
        runner.invoke(cli, ["task", "update", done_id, "--state", "done"])

        result = runner.invoke(cli, ["task", "list", "--state", "in_progress", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [in_progress_id]

        result = runner.invoke(cli, ["task", "list", "--state", "open", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [open_id]

        # --state must replace the default open-states filter, not narrow it
        # further -- "done" is excluded by default, so this only passes if
        # --state on its own is sufficient to surface it.
        result = runner.invoke(cli, ["task", "list", "--state", "done", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [done_id]

    def test_claimed_by_filters_to_that_actor(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        add_task: Callable[[str], str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--claimed-by matches only tasks claimed by that exact actor."""
        mine = add_task("mine")
        theirs = add_task("theirs")
        runner.invoke(cli, ["task", "claim", mine])
        monkeypatch.setenv("CORVEE_ACTOR", "agent:other")
        runner.invoke(cli, ["task", "claim", theirs])

        result = runner.invoke(cli, ["task", "list", "--claimed-by", "agent:other", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [theirs]

    def test_unclaimed_excludes_claimed_tasks(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--unclaimed returns only tasks with no claimed_by set."""
        unclaimed_id = add_task("unclaimed")
        claimed_id = add_task("claimed")
        runner.invoke(cli, ["task", "claim", claimed_id])

        result = runner.invoke(cli, ["task", "list", "--unclaimed", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [unclaimed_id]

    def test_stale_filters_to_claims_older_than_the_duration(
        self,
        runner: CliRunner,
        project: ProjectConfig,
        conn: sqlite3.Connection,
        add_task: Callable[[str], str],
    ) -> None:
        """--stale only returns tasks claimed before the cutoff, not unclaimed ones."""
        stale_id = add_task("stale claim")
        fresh_id = add_task("fresh claim")
        add_task("never claimed")
        runner.invoke(cli, ["task", "claim", stale_id])
        runner.invoke(cli, ["task", "claim", fresh_id])
        conn.execute(
            "UPDATE tasks SET claimed_at = '2020-01-01T00:00:00.000Z' WHERE id = ?",
            (int(stale_id.removeprefix("TASK-")),),
        )
        conn.commit()

        result = runner.invoke(cli, ["task", "list", "--stale", "1h", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [stale_id]

    def test_limit_truncates_the_merged_result(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--limit caps the sorted result to the first N, not an arbitrary N."""
        add_task("a")
        b_id = add_task("b")
        c_id = add_task("c")

        result = runner.invoke(cli, ["task", "list", "--limit", "2", "--json"])
        assert [t["id"] for t in json.loads(result.output)] == [c_id, b_id]


class TestShow:
    def test_returns_full_detail_shape(self, runner: CliRunner, project: ProjectConfig) -> None:
        """`task show` adds labels/links/subtasks/events to the base task shape."""
        runner.invoke(cli, ["task", "add", "task one", "--description", "d", "--json"])
        result = runner.invoke(cli, ["task", "show", "1", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["labels"] == []
        assert payload[0]["links"] == []
        assert payload[0]["subtasks"] == []
        assert [e["kind"] for e in payload[0]["events"]] == ["created"]
        assert payload[0]["referenced"] == []

    def test_add_writes_a_created_event_carrying_the_actor(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """`task add` used to write no event at all (TASK-29) -- unlike
        every other mutating command, which always has.
        """
        runner.invoke(cli, ["task", "add", "task one", "--description", "d", "--json"])
        result = runner.invoke(cli, ["task", "show", "1", "--json"])
        payload = json.loads(result.output)
        created = [e for e in payload[0]["events"] if e["kind"] == "created"]
        assert len(created) == 1
        assert created[0]["actor"] == "agent:test"
        assert created[0]["new_value"] == "task one"

    def test_missing_task_exits_three(self, runner: CliRunner, project: ProjectConfig) -> None:
        """Showing a nonexistent task id exits 3 with the task_not_found error code."""
        result = runner.invoke(cli, ["task", "show", "999", "--json"])
        assert result.exit_code == 3
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "task_not_found"

    @pytest.mark.parametrize("value", ["²", "9" * 23, "9" * 5000])
    def test_unparsable_id_exits_two(
        self, runner: CliRunner, project: ProjectConfig, value: str
    ) -> None:
        """A non-ASCII-digit or out-of-range id exits 2, never as an internal error."""
        result = runner.invoke(cli, ["task", "show", value, "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "invalid_task_id"

    def test_preserves_given_id_order(self, runner: CliRunner, project: ProjectConfig) -> None:
        """Multiple ids to `task show` come back in the order they were given, not id order."""
        runner.invoke(cli, ["task", "add", "a", "--description", "d", "--json"])
        runner.invoke(cli, ["task", "add", "b", "--description", "d", "--json"])
        result = runner.invoke(cli, ["task", "show", "2", "1", "--json"])
        payload = json.loads(result.output)
        assert [t["id"] for t in payload] == ["TASK-2", "TASK-1"]

    def test_plain_output_renders_unclaimed_fields_as_none_placeholder(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Without --json, `task show` renders an unset claimed_by as (none),
        not the string "None" (TASK-35).
        """
        runner.invoke(cli, ["task", "add", "task one", "--description", "d", "--json"])
        result = runner.invoke(cli, ["task", "show", "1"])
        assert "claimed_by: (none)" in result.output
        assert "None" not in result.output

    def test_plain_output_includes_comments_and_labels(
        self, runner: CliRunner, project: ProjectConfig
    ) -> None:
        """Without --json, `task show` still surfaces comments and labels, not just the
        bare row -- a human has no other way to read a task's history.
        """
        runner.invoke(cli, ["task", "add", "task one", "--description", "d", "--json"])
        runner.invoke(cli, ["task", "label", "1", "--add", "api"])
        runner.invoke(cli, ["task", "comment", "1", "found the root cause"])
        result = runner.invoke(cli, ["task", "show", "1"])
        assert result.exit_code == 0
        assert "api" in result.output
        assert "found the root cause" in result.output
