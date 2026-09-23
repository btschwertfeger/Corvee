#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Iterator

import pytest

from corvee.config import global_db_path
from corvee.constants import RELATIONS, Relation
from corvee.db.connection import open_connection
from corvee.db.links import get_children, get_task_links, link_tasks, unlink_tasks
from corvee.db.tasks import apply_update, insert_task
from corvee.errors import GuardViolationError, NotFoundError


@pytest.fixture
def global_conn() -> Iterator[sqlite3.Connection]:
    """A connection to the global database, bootstrapped on first open.

    `_fake_home` in conftest.py points $HOME at the test's tmp_path, so this
    never touches a real ~/.corvee/corvee.db. The parent directory is created
    the same way `corvee_context` creates it on the first global write.
    """
    db_path = global_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = open_connection(db_path)
    yield connection
    connection.close()


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

    @pytest.mark.parametrize("relation", RELATIONS)
    def test_self_link_is_rejected_for_every_relation(
        self, conn: sqlite3.Connection, relation: Relation
    ) -> None:
        """A task linked to itself raises a guard violation (exit 5) for every
        relation, not just parent_of/blocks (which happened to exit 5 already,
        incidentally, via the cycle check) -- duplicates/relates_to used to fall
        through to the schema's raw CHECK constraint instead (exit 1).
        """
        a = insert_task(conn, title="a")

        with pytest.raises(GuardViolationError) as excinfo:
            link_tasks(conn, a.id, a.id, relation, "agent:a", None)
        assert excinfo.value.exit_code == 5
        assert excinfo.value.code == "self_link"

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


class TestGlobalScopeLinks:
    def test_link_and_events_use_the_global_id_form(self, global_conn: sqlite3.Connection) -> None:
        """A link between two global tasks renders and records `TASK-GLOBAL-<n>`,
        not the bare `TASK-<n>` form that every other database also answers to.
        """
        a = insert_task(global_conn, title="a")
        b = insert_task(global_conn, title="b")
        link_tasks(global_conn, a.id, b.id, "relates_to", "agent:a", None, scope="global")

        assert get_task_links(global_conn, a.id, scope="global") == [
            {"relation": "relates_to", "task_id": "TASK-GLOBAL-2", "direction": "outgoing"}
        ]
        values = global_conn.execute(
            "SELECT new_value FROM task_events WHERE field = 'link:relates_to' ORDER BY task_id"
        ).fetchall()
        assert [row[0] for row in values] == ["TASK-GLOBAL-2", "TASK-GLOBAL-1"]

    def test_unlink_records_the_global_id_form(self, global_conn: sqlite3.Connection) -> None:
        """Unlinking a global pair records the removed link in the same id form."""
        a = insert_task(global_conn, title="a")
        b = insert_task(global_conn, title="b")
        link_tasks(global_conn, a.id, b.id, "duplicates", "agent:a", None, scope="global")
        unlink_tasks(global_conn, a.id, b.id, "duplicates", "agent:a", None, scope="global")

        values = global_conn.execute(
            "SELECT old_value FROM task_events WHERE task_id = ? AND field = 'link:duplicates'"
            " ORDER BY rowid DESC LIMIT 1",
            (a.id,),
        ).fetchone()
        assert values is not None
        assert values[0] == "TASK-GLOBAL-2"

    def test_guard_messages_use_the_global_id_form(self, global_conn: sqlite3.Connection) -> None:
        """A rejected link names both tasks in the form the caller used."""
        a = insert_task(global_conn, title="a")
        b = insert_task(global_conn, title="b")
        c = insert_task(global_conn, title="c")
        link_tasks(global_conn, a.id, b.id, "parent_of", "agent:a", None, scope="global")
        link_tasks(global_conn, b.id, c.id, "parent_of", "agent:a", None, scope="global")

        with pytest.raises(GuardViolationError) as excinfo:
            link_tasks(global_conn, c.id, a.id, "parent_of", "agent:a", None, scope="global")
        assert "TASK-GLOBAL-3 -> TASK-GLOBAL-1" in str(excinfo.value)

    def test_require_task_failure_names_the_global_id(
        self, global_conn: sqlite3.Connection
    ) -> None:
        """The not-found error for a global link names `TASK-GLOBAL-<n>`, not `TASK-<n>`."""
        a = insert_task(global_conn, title="a")
        with pytest.raises(NotFoundError) as excinfo:
            link_tasks(global_conn, a.id, 999, "blocks", "agent:a", None, scope="global")
        assert "TASK-GLOBAL-999" in str(excinfo.value)
