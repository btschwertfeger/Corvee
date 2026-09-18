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


class TestLabelCommand:
    def test_add_and_show(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--add attaches labels, visible afterward in `task show`."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "label", task_id, "--add", "API", "--add", "urgent"])
        result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        payload = json.loads(result.output)
        assert sorted(payload[0]["labels"]) == ["api", "urgent"]

    def test_remove_before_add_in_same_call(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--remove applies before --add, so `--remove x --add x` ends with x attached."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "label", task_id, "--add", "x"])
        result = runner.invoke(
            cli, ["task", "label", task_id, "--remove", "x", "--add", "x", "--json"]
        )
        assert result.exit_code == 0
        show_result = runner.invoke(cli, ["task", "show", task_id, "--json"])
        assert json.loads(show_result.output)[0]["labels"] == ["x"]

    def test_invalid_name_exits_two(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A label name that fails the allowed pattern exits 2 with the invalid_label error code."""
        task_id = add_task("task")
        result = runner.invoke(cli, ["task", "label", task_id, "--add", "has space", "--json"])
        assert result.exit_code == 2
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "invalid_label"

    def test_on_missing_task_exits_three(self, runner: CliRunner, project: ProjectConfig) -> None:
        """Labeling a nonexistent task id exits 3."""
        result = runner.invoke(cli, ["task", "label", "999", "--add", "x", "--json"])
        assert result.exit_code == 3

    def test_accepts_multiple_ids_in_one_call(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task label` applies --add/--remove to every id given, in one transaction."""
        a = add_task("a")
        b = add_task("b")
        result = runner.invoke(cli, ["task", "label", a, b, "--add", "urgent", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [t["id"] for t in payload] == [a, b]

        show_result = runner.invoke(cli, ["task", "show", a, b, "--json"])
        for task in json.loads(show_result.output):
            assert task["labels"] == ["urgent"]

    def test_batch_is_all_or_nothing(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A missing id in the batch rolls back labels already applied earlier in the call."""
        a = add_task("a")
        result = runner.invoke(cli, ["task", "label", a, "999", "--add", "urgent", "--json"])
        assert result.exit_code == 3

        show_result = runner.invoke(cli, ["task", "show", a, "--json"])
        assert json.loads(show_result.output)[0]["labels"] == []


class TestLabelsCommand:
    def test_lists_names_and_counts(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """`task labels` lists every label in the project along with its task count."""
        a = add_task("a")
        b = add_task("b")
        runner.invoke(cli, ["task", "label", a, "--add", "api"])
        runner.invoke(cli, ["task", "label", b, "--add", "api"])
        runner.invoke(cli, ["task", "label", a, "--add", "urgent"])

        result = runner.invoke(cli, ["task", "labels", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        counts = {entry["name"]: entry["task_count"] for entry in payload}
        assert counts == {"api": 2, "urgent": 1}


class TestListLabelFilter:
    def test_combines_multiple_labels_with_and_semantics(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Repeating --label on `task list` narrows to tasks carrying all of them, not either."""
        a = add_task("a")
        b = add_task("b")
        runner.invoke(cli, ["task", "label", a, "--add", "api", "--add", "urgent"])
        runner.invoke(cli, ["task", "label", b, "--add", "api"])

        result = runner.invoke(
            cli, ["task", "list", "--label", "api", "--label", "urgent", "--json"]
        )
        payload = json.loads(result.output)
        assert [t["id"] for t in payload] == [a]
