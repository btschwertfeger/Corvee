#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3

import pytest

from corvee.db.events import get_task_events
from corvee.db.links import link_tasks
from corvee.db.tasks import (
    TaskFilter,
    apply_update,
    assign_task,
    cascade_cancel_descendants,
    get_task,
    insert_task,
    list_tasks,
    purge_task,
    require_task,
    require_tasks,
)
from corvee.errors import GuardViolationError, NotFoundError


class TestInsertTask:
    def test_sets_defaults(self, conn: sqlite3.Connection) -> None:
        """A minimal insert gets the documented defaults: task/medium/todo, unclaimed."""
        task = insert_task(conn, title="do the thing")
        assert task.title == "do the thing"
        assert task.description == ""
        assert task.type == "task"
        assert task.priority == "medium"
        assert task.state == "open"
        assert task.claimed_by is None
        assert task.created_at == task.updated_at

    def test_with_explicit_fields(self, conn: sqlite3.Connection) -> None:
        """Explicit description/type/priority values are stored as given."""
        task = insert_task(
            conn, title="fix bug", description="oops", type_="bug", priority="critical"
        )
        assert task.description == "oops"
        assert task.type == "bug"
        assert task.priority == "critical"

    def test_no_actor_writes_no_event(self, conn: sqlite3.Connection) -> None:
        """Omitted `actor` (the default -- every existing caller that
        doesn't care about attribution) writes no event at all, the
        historical behavior kept for the ~200 call sites across this
        suite that predate TASK-29's fix.
        """
        task = insert_task(conn, title="do the thing")
        events, _ = get_task_events(conn, task.id)
        assert events == []

    def test_actor_given_writes_a_created_event(self, conn: sqlite3.Connection) -> None:
        """`actor`, given, writes a `created` event carrying it and the
        given `session_id` -- the task equivalent of what `insert_fact`
        has always done (TASK-29).
        """
        task = insert_task(conn, title="do the thing", actor="agent:test", session_id="sess-1")
        events, _ = get_task_events(conn, task.id)
        assert len(events) == 1
        assert events[0]["kind"] == "created"
        assert events[0]["new_value"] == "do the thing"
        assert events[0]["actor"] == "agent:test"
        assert events[0]["session_id"] == "sess-1"


class TestGetAndRequireTask:
    def test_get_task_returns_none_when_missing(self, conn: sqlite3.Connection) -> None:
        """get_task returns None for a missing id rather than raising."""
        assert get_task(conn, 999) is None

    def test_require_task_raises_not_found(self, conn: sqlite3.Connection) -> None:
        """require_task raises NotFoundError (exit 3) naming the TASK-<n> form of the missing id."""
        with pytest.raises(NotFoundError) as excinfo:
            require_task(conn, 999)
        assert excinfo.value.exit_code == 3
        assert excinfo.value.extra["task_id"] == "TASK-999"

    def test_require_tasks_preserves_given_order(self, conn: sqlite3.Connection) -> None:
        """require_tasks returns tasks in the order their ids were given, not insertion order."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        result = require_tasks(conn, [b.id, a.id])
        assert [t.id for t in result] == [b.id, a.id]


class TestListTasks:
    def test_excludes_done_and_cancelled_by_default(self, conn: sqlite3.Connection) -> None:
        """The default filter is "open": done/cancelled tasks are excluded."""
        open_task = insert_task(conn, title="open")
        done_task = insert_task(conn, title="closed")
        conn.execute("UPDATE tasks SET state = 'done' WHERE id = ?", (done_task.id,))

        results = list_tasks(conn, TaskFilter())
        assert [t.id for t in results] == [open_task.id]

    def test_include_all(self, conn: sqlite3.Connection) -> None:
        """include_all=True returns tasks regardless of state, done/cancelled included."""
        open_task = insert_task(conn, title="open")
        done_task = insert_task(conn, title="closed")
        conn.execute("UPDATE tasks SET state = 'done' WHERE id = ?", (done_task.id,))

        results = list_tasks(conn, TaskFilter(include_all=True))
        assert {t.id for t in results} == {open_task.id, done_task.id}

    def test_orders_by_priority_desc_then_id_desc(self, conn: sqlite3.Connection) -> None:
        """Results sort by priority descending, then id descending (newest first) within a tier."""
        low = insert_task(conn, title="low", priority="low")
        critical = insert_task(conn, title="critical", priority="critical")
        medium_first = insert_task(conn, title="medium1", priority="medium")
        medium_second = insert_task(conn, title="medium2", priority="medium")

        results = list_tasks(conn, TaskFilter())
        assert [t.id for t in results] == [
            critical.id,
            medium_second.id,
            medium_first.id,
            low.id,
        ]

    def test_orders_by_created_at_desc_before_id_desc(self, conn: sqlite3.Connection) -> None:
        """created_at desc breaks a priority tie before id does, matching §5.1.1's
        documented "fixed and total" order -- a lower id can still hold the later
        created_at, and that row must still sort first.
        """
        lower_id_newer = insert_task(conn, title="first")
        higher_id_older = insert_task(conn, title="second")
        conn.execute(
            "UPDATE tasks SET created_at = '2030-01-01T00:00:00.000Z' WHERE id = ?",
            (lower_id_newer.id,),
        )
        conn.execute(
            "UPDATE tasks SET created_at = '2020-01-01T00:00:00.000Z' WHERE id = ?",
            (higher_id_older.id,),
        )

        results = list_tasks(conn, TaskFilter())
        assert [t.id for t in results] == [lower_id_newer.id, higher_id_older.id]

    def test_filters_by_type_and_priority(self, conn: sqlite3.Connection) -> None:
        """type and priority filters combine with AND, matching only the intersection."""
        insert_task(conn, title="bug", type_="bug", priority="high")
        match = insert_task(conn, title="chore", type_="chore", priority="high")
        insert_task(conn, title="chore-low", type_="chore", priority="low")

        results = list_tasks(conn, TaskFilter(type="chore", priority="high"))
        assert [t.id for t in results] == [match.id]

    def test_filters_by_assigned_to(self, conn: sqlite3.Connection) -> None:
        """--assigned-to matches tasks routed to the given actor, not any other."""
        routed = insert_task(conn, title="routed")
        insert_task(conn, title="unrouted")
        assign_task(conn, routed.id, "agent:a", "human:supervisor")

        results = list_tasks(conn, TaskFilter(assigned_to="agent:a"))
        assert [t.id for t in results] == [routed.id]

    def test_limit(self, conn: sqlite3.Connection) -> None:
        """limit caps the number of rows returned."""
        for i in range(5):
            insert_task(conn, title=f"t{i}")
        results = list_tasks(conn, TaskFilter(limit=2))
        assert len(results) == 2

    def test_label_filter_is_and(self, conn: sqlite3.Connection) -> None:
        """Multiple labels in the filter require every one of them, not any."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        conn.execute("INSERT INTO labels (name) VALUES ('api'), ('urgent')")
        api_id, urgent_id = (row[0] for row in conn.execute("SELECT id FROM labels ORDER BY name"))
        conn.execute("INSERT INTO task_labels (task_id, label_id) VALUES (?, ?)", (a.id, api_id))
        conn.execute("INSERT INTO task_labels (task_id, label_id) VALUES (?, ?)", (a.id, urgent_id))
        conn.execute("INSERT INTO task_labels (task_id, label_id) VALUES (?, ?)", (b.id, api_id))

        results = list_tasks(conn, TaskFilter(labels=("api", "urgent")))
        assert [t.id for t in results] == [a.id]

    def test_parent_filter_matches_direct_children_only(self, conn: sqlite3.Connection) -> None:
        """--parent matches only direct children, not grandchildren further down the tree."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        grandchild = insert_task(conn, title="grandchild")
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'parent_of')",
            (parent.id, child.id),
        )
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'parent_of')",
            (child.id, grandchild.id),
        )

        results = list_tasks(conn, TaskFilter(parent_id=parent.id))
        assert [t.id for t in results] == [child.id]

    def test_blocks_filter_matches_what_the_given_task_blocks(
        self, conn: sqlite3.Connection
    ) -> None:
        """--blocks <id> matches tasks that <id> blocks."""
        blocker = insert_task(conn, title="blocker")
        blocked = insert_task(conn, title="blocked")
        insert_task(conn, title="unrelated")
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'blocks')",
            (blocker.id, blocked.id),
        )

        results = list_tasks(conn, TaskFilter(blocks_id=blocker.id))
        assert [t.id for t in results] == [blocked.id]

    def test_blocked_by_filter_matches_what_blocks_the_given_task(
        self, conn: sqlite3.Connection
    ) -> None:
        """--blocked-by <id> matches tasks that block <id>."""
        blocker = insert_task(conn, title="blocker")
        blocked = insert_task(conn, title="blocked")
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'blocks')",
            (blocker.id, blocked.id),
        )

        results = list_tasks(conn, TaskFilter(blocked_by_id=blocked.id))
        assert [t.id for t in results] == [blocker.id]

    def test_relates_to_filter_matches_either_side_of_the_symmetric_link(
        self, conn: sqlite3.Connection
    ) -> None:
        """--relates-to <id> matches regardless of which side <id> was stored on."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'relates_to')",
            (min(a.id, b.id), max(a.id, b.id)),
        )

        assert [t.id for t in list_tasks(conn, TaskFilter(relates_to_id=a.id))] == [b.id]
        assert [t.id for t in list_tasks(conn, TaskFilter(relates_to_id=b.id))] == [a.id]

    def test_since_filter_matches_updated_at_cutoff(self, conn: sqlite3.Connection) -> None:
        """--since keeps tasks updated at or after the cutoff, dropping older ones."""
        old = insert_task(conn, title="old")
        recent = insert_task(conn, title="recent")
        conn.execute(
            "UPDATE tasks SET updated_at = '2020-01-01T00:00:00.000Z' WHERE id = ?", (old.id,)
        )
        conn.execute(
            "UPDATE tasks SET updated_at = '2026-01-01T00:00:00.000Z' WHERE id = ?", (recent.id,)
        )

        results = list_tasks(conn, TaskFilter(updated_since="2025-01-01T00:00:00.000Z"))
        assert [t.id for t in results] == [recent.id]


class TestCascadeCancelDescendants:
    def test_terminates_on_a_hand_crafted_parent_of_cycle(self, conn: sqlite3.Connection) -> None:
        """A `parent_of` cycle in the data (bypassing corvee's own insert-time
        cycle guard, e.g. via a hand-edited database) must not hang the
        cascade traversal forever -- a visited set bounds it the same way
        `guards/ancestry.py:is_reachable` already bounds its own walk.
        """
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        c = insert_task(conn, title="c")
        for source, target in ((a.id, b.id), (b.id, c.id), (c.id, a.id)):
            conn.execute(
                "INSERT INTO task_links (source_id, target_id, relation)"
                " VALUES (?, ?, 'parent_of')",
                (source, target),
            )

        # The cycle makes `a` reachable again via c -> a, so the traversal legitimately
        # revisits and cancels it too; what matters is that it terminates at all.
        touched = cascade_cancel_descendants(conn, a.id, "agent:test", None, force=True)
        assert set(touched) == {a.id, b.id, c.id}


class TestPurgeTask:
    def test_removes_a_cancelled_unlinked_task(self, conn: sqlite3.Connection) -> None:
        """A cancelled, link-free task is gone entirely after purge, not just relabeled."""
        task = insert_task(conn, title="junk")
        apply_update(conn, task.id, "agent:a", state="cancelled")

        purge_task(conn, task.id)

        assert get_task(conn, task.id) is None

    def test_returns_the_tasks_last_state(self, conn: sqlite3.Connection) -> None:
        """The row it returns is the pre-deletion snapshot, since nothing is left to fetch."""
        task = insert_task(conn, title="junk")
        apply_update(conn, task.id, "agent:a", state="cancelled")

        result = purge_task(conn, task.id)

        assert result.id == task.id
        assert result.state == "cancelled"

    def test_removes_its_task_events_history(self, conn: sqlite3.Connection) -> None:
        task = insert_task(conn, title="junk")
        apply_update(conn, task.id, "agent:a", state="cancelled")

        purge_task(conn, task.id)

        count = conn.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id = ?", (task.id,)
        ).fetchone()[0]
        assert count == 0

    def test_removes_its_labels(self, conn: sqlite3.Connection) -> None:
        task = insert_task(conn, title="junk")
        conn.execute("INSERT INTO labels (name) VALUES ('api')")
        label_id = conn.execute("SELECT id FROM labels WHERE name = 'api'").fetchone()[0]
        conn.execute(
            "INSERT INTO task_labels (task_id, label_id) VALUES (?, ?)", (task.id, label_id)
        )
        apply_update(conn, task.id, "agent:a", state="cancelled")

        purge_task(conn, task.id)

        count = conn.execute(
            "SELECT COUNT(*) FROM task_labels WHERE task_id = ?", (task.id,)
        ).fetchone()[0]
        assert count == 0

    def test_refuses_a_task_that_is_not_cancelled(self, conn: sqlite3.Connection) -> None:
        """Purging an open (or any non-cancelled) task is a guard violation, not a shortcut."""
        task = insert_task(conn, title="junk")

        with pytest.raises(GuardViolationError) as excinfo:
            purge_task(conn, task.id)
        assert excinfo.value.exit_code == 5
        assert excinfo.value.code == "task_not_cancelled"
        assert get_task(conn, task.id) is not None

    def test_refuses_a_cancelled_task_that_still_has_a_link(self, conn: sqlite3.Connection) -> None:
        """A link to another task blocks purge until it is removed (`task unlink` first)."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        link_tasks(conn, a.id, b.id, "relates_to", "agent:a", None)
        apply_update(conn, a.id, "agent:a", state="cancelled")

        with pytest.raises(GuardViolationError) as excinfo:
            purge_task(conn, a.id)
        assert excinfo.value.code == "task_has_links"
        assert get_task(conn, a.id) is not None

    def test_purge_after_unlinking_succeeds(self, conn: sqlite3.Connection) -> None:
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        link_tasks(conn, a.id, b.id, "relates_to", "agent:a", None)
        apply_update(conn, a.id, "agent:a", state="cancelled")
        conn.execute("DELETE FROM task_links WHERE source_id = ? AND target_id = ?", (a.id, b.id))

        purge_task(conn, a.id)

        assert get_task(conn, a.id) is None

    def test_missing_task_raises_not_found(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(NotFoundError):
            purge_task(conn, 999)
