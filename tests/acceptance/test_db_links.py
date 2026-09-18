#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3

import pytest

from corvee.db.links import get_children, get_task_links, link_tasks, unlink_tasks
from corvee.db.tasks import apply_update, insert_task
from corvee.errors import GuardViolationError


class TestLinkTasks:
    def test_parent_of_registers_child(self, conn: sqlite3.Connection) -> None:
        """A parent_of link makes the child show up in the parent's children."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        link_tasks(conn, parent.id, child.id, "parent_of", "agent:a", None)
        assert get_children(conn, parent.id) == [child.id]

    def test_twice_is_a_no_op(self, conn: sqlite3.Connection) -> None:
        """Linking the same pair/relation twice does not create a duplicate row."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        link_tasks(conn, a.id, b.id, "blocks", "agent:a", None)
        link_tasks(conn, a.id, b.id, "blocks", "agent:a", None)
        links = get_task_links(conn, a.id)
        assert len(links) == 1

    def test_parent_of_cycle_is_rejected(self, conn: sqlite3.Connection) -> None:
        """Linking C parent_of A, closing a A-B-C parent_of chain into a cycle, raises."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        c = insert_task(conn, title="c")
        link_tasks(conn, a.id, b.id, "parent_of", "agent:a", None)
        link_tasks(conn, b.id, c.id, "parent_of", "agent:a", None)

        with pytest.raises(GuardViolationError) as excinfo:
            link_tasks(conn, c.id, a.id, "parent_of", "agent:a", None)
        assert excinfo.value.exit_code == 5
        assert excinfo.value.extra["relation"] == "parent_of"

    def test_blocks_two_cycle_is_rejected(self, conn: sqlite3.Connection) -> None:
        """A blocks B plus B blocks A is rejected as a two-node cycle."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        link_tasks(conn, a.id, b.id, "blocks", "agent:a", None)

        with pytest.raises(GuardViolationError):
            link_tasks(conn, b.id, a.id, "blocks", "agent:a", None)

    def test_task_cannot_have_two_parents(self, conn: sqlite3.Connection) -> None:
        """A child with an existing parent rejects a second parent_of, naming the current one."""
        parent1 = insert_task(conn, title="p1")
        parent2 = insert_task(conn, title="p2")
        child = insert_task(conn, title="child")
        link_tasks(conn, parent1.id, child.id, "parent_of", "agent:a", None)

        with pytest.raises(GuardViolationError) as excinfo:
            link_tasks(conn, parent2.id, child.id, "parent_of", "agent:a", None)
        assert excinfo.value.extra["current_parent"].endswith(str(parent1.id))

    def test_relinking_same_parent_is_a_no_op(self, conn: sqlite3.Connection) -> None:
        """Linking a child to its already-existing parent again succeeds without conflict."""
        parent = insert_task(conn, title="p")
        child = insert_task(conn, title="c")
        link_tasks(conn, parent.id, child.id, "parent_of", "agent:a", None)
        link_tasks(conn, parent.id, child.id, "parent_of", "agent:a", None)
        assert get_children(conn, parent.id) == [child.id]

    def test_attaching_open_child_under_done_parent_warns(self, conn: sqlite3.Connection) -> None:
        """Linking a non-terminal child under a done parent returns a warning for the parent."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        apply_update(conn, parent.id, "agent:a", state="done")

        warnings = link_tasks(conn, parent.id, child.id, "parent_of", "agent:a", None)

        assert list(warnings.keys()) == [parent.id]
        assert "TASK-" + str(child.id) in warnings[parent.id]

    def test_attaching_done_child_under_done_parent_does_not_warn(
        self, conn: sqlite3.Connection
    ) -> None:
        """No warning when the child being attached is already terminal too."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        apply_update(conn, parent.id, "agent:a", state="done")
        apply_update(conn, child.id, "agent:a", state="done")

        warnings = link_tasks(conn, parent.id, child.id, "parent_of", "agent:a", None)

        assert warnings == {}

    def test_attaching_child_under_open_parent_does_not_warn(
        self, conn: sqlite3.Connection
    ) -> None:
        """No warning for the ordinary case: parent is not done."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")

        warnings = link_tasks(conn, parent.id, child.id, "parent_of", "agent:a", None)

        assert warnings == {}

    def test_relates_to_is_normalized_and_symmetric(self, conn: sqlite3.Connection) -> None:
        """relates_to is stored as one normalized row and shows up on both ends."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        link_tasks(conn, max(a.id, b.id), min(a.id, b.id), "relates_to", "agent:a", None)

        links_a = get_task_links(conn, a.id)
        links_b = get_task_links(conn, b.id)
        assert len(links_a) == 1
        assert len(links_b) == 1
        assert links_a[0]["relation"] == "relates_to"


class TestUnlinkTasks:
    def test_removes_the_link(self, conn: sqlite3.Connection) -> None:
        """Unlinking an existing link removes it."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        link_tasks(conn, a.id, b.id, "duplicates", "agent:a", None)
        unlink_tasks(conn, a.id, b.id, "duplicates", "agent:a", None)
        assert get_task_links(conn, a.id) == []

    def test_not_linked_is_a_no_op(self, conn: sqlite3.Connection) -> None:
        """Unlinking a pair that was never linked succeeds without error."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        unlink_tasks(conn, a.id, b.id, "duplicates", "agent:a", None)  # must not raise
        assert get_task_links(conn, a.id) == []

    def test_parent_frees_child_for_new_parent(self, conn: sqlite3.Connection) -> None:
        """Unlinking a parent_of edge frees the child to be linked under a different parent."""
        parent1 = insert_task(conn, title="p1")
        parent2 = insert_task(conn, title="p2")
        child = insert_task(conn, title="child")
        link_tasks(conn, parent1.id, child.id, "parent_of", "agent:a", None)
        unlink_tasks(conn, parent1.id, child.id, "parent_of", "agent:a", None)

        link_tasks(conn, parent2.id, child.id, "parent_of", "agent:a", None)
        assert get_children(conn, parent2.id) == [child.id]
