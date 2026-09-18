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


class TestLink:
    def test_parent_of_shows_up_as_subtask(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Linking parent_of makes the child appear in the parent's `task show` subtasks."""
        parent = add_task("parent")
        child = add_task("child")
        result = runner.invoke(
            cli, ["task", "link", parent, child, "--relation", "parent_of", "--json"]
        )
        assert result.exit_code == 0

        show_result = runner.invoke(cli, ["task", "show", parent, "--json"])
        payload = json.loads(show_result.output)
        assert payload[0]["subtasks"] == [child]

    def test_attaching_open_child_to_done_parent_warns(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Linking an open child under a done parent warns on the parent, doesn't reopen it."""
        parent = add_task("parent")
        child = add_task("child")
        runner.invoke(cli, ["task", "update", parent, "--state", "done"])

        result = runner.invoke(
            cli, ["task", "link", parent, child, "--relation", "parent_of", "--json"]
        )
        assert result.exit_code == 0
        payload = {t["id"]: t for t in json.loads(result.output)}
        assert payload[parent]["state"] == "done"
        assert payload[parent]["warnings"] == [f"child {child} is open while this parent is done"]
        assert "warnings" not in payload[child]

    def test_second_parent_is_rejected(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A task already carrying a parent_of parent rejects a second one with a guard error."""
        parent1 = add_task("p1")
        parent2 = add_task("p2")
        child = add_task("child")
        runner.invoke(cli, ["task", "link", parent1, child, "--relation", "parent_of"])

        result = runner.invoke(
            cli, ["task", "link", parent2, child, "--relation", "parent_of", "--json"]
        )
        assert result.exit_code == 5
        payload = json.loads(result.stderr)
        assert payload["error"]["code"] == "already_has_parent"


class TestUnlink:
    def test_then_relink_to_new_parent(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Unlinking a parent_of edge frees the child to be linked under a different parent."""
        parent1 = add_task("p1")
        parent2 = add_task("p2")
        child = add_task("child")
        runner.invoke(cli, ["task", "link", parent1, child, "--relation", "parent_of"])
        runner.invoke(cli, ["task", "unlink", parent1, child, "--relation", "parent_of"])

        result = runner.invoke(
            cli, ["task", "link", parent2, child, "--relation", "parent_of", "--json"]
        )
        assert result.exit_code == 0


class TestCascadeCancel:
    def test_reports_every_touched_task(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """--cascade on a cancelled parent cancels its open children too, reporting all of them."""
        parent = add_task("parent")
        child = add_task("child")
        runner.invoke(cli, ["task", "link", parent, child, "--relation", "parent_of"])

        result = runner.invoke(
            cli, ["task", "update", parent, "--state", "cancelled", "--cascade", "--json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        ids = {t["id"] for t in payload}
        assert ids == {parent, child}
        assert all(t["state"] == "cancelled" for t in payload)
