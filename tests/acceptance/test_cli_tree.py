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


def _link(runner: CliRunner, parent: str, child: str) -> None:
    runner.invoke(cli, ["task", "link", parent, child, "--relation", "parent_of"])


class TestTaskTree:
    def test_leaf_task_has_no_children(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A task with no parent_of children returns itself with an empty children list."""
        task_id = add_task("solo")
        result = runner.invoke(cli, ["task", "tree", task_id, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["id"] == task_id
        assert payload["children"] == []

    def test_nested_subtree_shape(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A multi-level tree nests correctly, and includes descendants of every state."""
        root = add_task("root")
        done_child = add_task("done child")
        in_progress_child = add_task("in progress child")
        grandchild = add_task("grandchild")
        _link(runner, root, done_child)
        _link(runner, root, in_progress_child)
        _link(runner, in_progress_child, grandchild)
        runner.invoke(cli, ["task", "update", done_child, "--state", "done"])
        runner.invoke(cli, ["task", "update", in_progress_child, "--state", "in_progress"])

        result = runner.invoke(cli, ["task", "tree", root, "--json"])
        payload = json.loads(result.output)
        assert payload["id"] == root
        assert payload["state"] == "open"
        child_ids = {c["id"] for c in payload["children"]}
        assert child_ids == {done_child, in_progress_child}
        done_node = next(c for c in payload["children"] if c["id"] == done_child)
        assert done_node["state"] == "done"
        assert done_node["children"] == []
        in_progress_node = next(c for c in payload["children"] if c["id"] == in_progress_child)
        assert in_progress_node["state"] == "in_progress"
        assert [c["id"] for c in in_progress_node["children"]] == [grandchild]

    def test_missing_task_exits_three(self, runner: CliRunner, project: ProjectConfig) -> None:
        """A tree rooted at a nonexistent id exits 3, same as `task show`."""
        result = runner.invoke(cli, ["task", "tree", "TASK-99", "--json"])
        assert result.exit_code == 3

    def test_plain_text_indents_by_depth(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Plain-text output is an indented ASCII tree, deeper levels indented further."""
        root = add_task("root")
        child = add_task("child")
        _link(runner, root, child)

        result = runner.invoke(cli, ["task", "tree", root])
        assert result.exit_code == 0
        lines = result.output.splitlines()
        assert lines[0].startswith(f"{root} [open]")
        assert lines[1].startswith(f"  {child} [open]")

    def test_hand_crafted_cycle_terminates_instead_of_hanging(
        self, runner: CliRunner, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """A parent_of cycle (only reachable via a hand-edited database) must not
        hang the traversal -- the same visited-set protection cascade_cancel_
        descendants and doctor's cycle detection already apply.
        """
        a = add_task("a")
        b = add_task("b")
        _link(runner, a, b)
        # Hand-craft the cycle back to `a`, bypassing the insert-time cycle guard.
        from corvee.db.connection import open_connection

        conn = open_connection(project.db_path)
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'parent_of')",
            (int(b.removeprefix("TASK-")), int(a.removeprefix("TASK-"))),
        )
        conn.commit()
        conn.close()

        result = runner.invoke(cli, ["task", "tree", a, "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["id"] == a
        assert [c["id"] for c in payload["children"]] == [b]
        assert payload["children"][0]["children"] == []
