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


@pytest.fixture
def blocked_pair(
    runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
) -> tuple[str, str]:
    """(blocker, blocked): `blocker` blocks `blocked`."""
    blocker = add_task("blocker")
    blocked = add_task("blocked")
    runner.invoke(cli, ["task", "link", blocker, blocked, "--relation", "blocks"])
    return blocker, blocked


def _state_cells(runner: CliRunner) -> dict[str, str]:
    """Map task id to the STATE cell of the `task list` table."""
    lines = runner.invoke(cli, ["task", "list", "--fields", "id,state"]).output.splitlines()
    return {cells[0]: cells[1] for line in lines[1:] if (cells := line.split())}


class TestBlockedBy:
    def test_json_lists_open_blockers_and_keeps_stored_state(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        """`blocked_by` names the open blockers while `state` stays the stored value."""
        blocker, blocked = blocked_pair
        payload = json.loads(runner.invoke(cli, ["task", "list", "-o", "json"]).output)
        by_id = {task["id"]: task for task in payload}
        assert by_id[blocked]["blocked_by"] == [blocker]
        assert by_id[blocked]["state"] == "open"
        assert by_id[blocker]["blocked_by"] == []

    @pytest.mark.parametrize("final_state", ["done", "cancelled"])
    def test_finished_blocker_releases_the_task(
        self, runner: CliRunner, blocked_pair: tuple[str, str], final_state: str
    ) -> None:
        """A `done` or `cancelled` blocker no longer appears in `blocked_by`."""
        blocker, blocked = blocked_pair
        runner.invoke(cli, ["task", "update", blocker, "--state", final_state])
        payload = json.loads(runner.invoke(cli, ["task", "show", blocked, "-o", "json"]).output)
        assert payload[0]["blocked_by"] == []

    def test_fields_projection_accepts_blocked_by(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        blocker, blocked = blocked_pair
        result = runner.invoke(
            cli, ["task", "list", "--fields", "id,blocked_by", "--state", "blocked", "-o", "json"]
        )
        assert json.loads(result.output) == [{"id": blocked, "blocked_by": [blocker]}]

    def test_table_renders_blocked_by_comma_joined(
        self, runner: CliRunner, blocked_pair: tuple[str, str], add_task: Callable[[str], str]
    ) -> None:
        blocker, blocked = blocked_pair
        second = add_task("second blocker")
        runner.invoke(cli, ["task", "link", second, blocked, "--relation", "blocks"])
        result = runner.invoke(cli, ["task", "list", "--fields", "id,blocked_by"])
        assert f"{blocker},{second}" in result.output


class TestDerivedBlockedDisplay:
    def test_marks_open_task_with_open_blocker(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        blocker, blocked = blocked_pair
        cells = _state_cells(runner)
        assert cells[blocked] == "blocked*"
        assert cells[blocker] == "open"

    def test_marker_clears_when_the_last_blocker_finishes(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        blocker, blocked = blocked_pair
        runner.invoke(cli, ["task", "update", blocker, "--state", "done"])
        assert _state_cells(runner)[blocked] == "open"

    def test_manual_blocked_stays_plain(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        """A stored `blocked` shows without the `*`, even with an open blocker."""
        _, blocked = blocked_pair
        runner.invoke(cli, ["task", "update", blocked, "--state", "blocked"])
        assert _state_cells(runner)[blocked] == "blocked"

    def test_in_progress_task_keeps_its_state(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        _, blocked = blocked_pair
        runner.invoke(cli, ["task", "update", blocked, "--state", "in_progress"])
        assert _state_cells(runner)[blocked] == "in_progress"

    def test_show_header_marks_state(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        _, blocked = blocked_pair
        output = runner.invoke(cli, ["task", "show", blocked]).output
        assert "state: blocked*" in output.splitlines()


class TestStateFilter:
    def test_blocked_filter_includes_derived_and_manual(
        self,
        runner: CliRunner,
        blocked_pair: tuple[str, str],
        add_task: Callable[[str], str],
    ) -> None:
        _, derived = blocked_pair
        manual = add_task("manual")
        runner.invoke(cli, ["task", "update", manual, "--state", "blocked"])
        payload = json.loads(
            runner.invoke(cli, ["task", "list", "--state", "blocked", "-o", "json"]).output
        )
        assert {task["id"] for task in payload} == {derived, manual}

    def test_open_filter_excludes_derived_blocked(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        blocker, _ = blocked_pair
        payload = json.loads(
            runner.invoke(cli, ["task", "list", "--state", "open", "-o", "json"]).output
        )
        assert [task["id"] for task in payload] == [blocker]

    def test_combines_with_other_filters(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        _, blocked = blocked_pair
        runner.invoke(cli, ["task", "update", blocked, "--priority", "high"])
        args = ["task", "list", "--state", "blocked", "-o", "json"]
        assert len(json.loads(runner.invoke(cli, [*args, "--priority", "high"]).output)) == 1
        assert json.loads(runner.invoke(cli, [*args, "--priority", "low"]).output) == []


class TestOtherViews:
    """Every plain-text view shows the marker, and every JSON view the stored state."""

    @pytest.mark.parametrize("output_flag", [[], ["-o", "wide"]])
    def test_brief_marks_state_and_joins_blocked_by(
        self, runner: CliRunner, blocked_pair: tuple[str, str], output_flag: list[str]
    ) -> None:
        _, blocked = blocked_pair
        runner.invoke(cli, ["task", "claim", blocked])
        output = runner.invoke(cli, ["brief", *output_flag]).output
        assert "blocked*" in output
        assert "['" not in output
        assert ("BLOCKED_BY" in output) == bool(output_flag)

    @pytest.mark.parametrize("command", [["task", "mine"], ["task", "search", "blocked"]])
    def test_mine_and_search_tables_mark_state(
        self, runner: CliRunner, blocked_pair: tuple[str, str], command: list[str]
    ) -> None:
        _, blocked = blocked_pair
        runner.invoke(cli, ["task", "claim", blocked])
        assert "blocked*" in runner.invoke(cli, command).output

    def test_wide_list_shows_comma_joined_blocked_by(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        blocker, _ = blocked_pair
        output = runner.invoke(cli, ["task", "list", "-o", "wide"]).output
        assert "BLOCKED_BY" in output.splitlines()[0]
        assert blocker in output
        assert "['" not in output

    def test_ready_is_unchanged(self, runner: CliRunner, blocked_pair: tuple[str, str]) -> None:
        blocker, _ = blocked_pair
        payload = json.loads(runner.invoke(cli, ["task", "ready", "-o", "json"]).output)
        assert [task["id"] for task in payload] == [blocker]

    def test_mutation_returns_blocked_by(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        blocker, blocked = blocked_pair
        payload = json.loads(runner.invoke(cli, ["task", "claim", blocked, "-o", "json"]).output)
        assert payload[0]["blocked_by"] == [blocker]

    def test_manual_blocked_keeps_stored_state_in_json(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        _, blocked = blocked_pair
        runner.invoke(cli, ["task", "update", blocked, "--state", "blocked"])
        payload = json.loads(runner.invoke(cli, ["task", "show", blocked, "-o", "json"]).output)
        assert payload[0]["state"] == "blocked"

    def test_global_tasks_carry_blocked_by_in_a_merged_list(
        self, runner: CliRunner, blocked_pair: tuple[str, str]
    ) -> None:
        """A `blocks` link lives in one database, so a global blocker shows as TASK-GLOBAL-n."""
        ids = [
            json.loads(
                runner.invoke(
                    cli,
                    ["task", "add", title, "--description", "d", "--global", "-o", "json"],
                ).output
            )[0]["id"]
            for title in ("global blocker", "global blocked")
        ]
        runner.invoke(cli, ["task", "link", ids[0], ids[1], "--relation", "blocks"])
        payload = json.loads(runner.invoke(cli, ["task", "list", "-o", "json"]).output)
        by_id = {task["id"]: task for task in payload}
        assert by_id[ids[1]]["blocked_by"] == [ids[0]]
        assert by_id[blocked_pair[1]]["blocked_by"] == [blocked_pair[0]]
        assert by_id[ids[0]]["blocked_by"] == []
