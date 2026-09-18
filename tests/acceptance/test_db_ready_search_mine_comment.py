#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3

from corvee.db.events import get_last_comment, get_task_events, record_comment
from corvee.db.links import link_tasks
from corvee.db.tasks import (
    add_comment,
    apply_update,
    assign_task,
    claim_task,
    insert_task,
    mine_tasks,
    ready_tasks,
    search_tasks,
    unassign_task,
)


class TestReadyTasks:
    def test_excludes_claimed_tasks(self, conn: sqlite3.Connection) -> None:
        """A claimed task never appears in the ready list."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        assert ready_tasks(conn) == []

    def test_excludes_blocked_state(self, conn: sqlite3.Connection) -> None:
        """A task in state=blocked never appears in the ready list."""
        task = insert_task(conn, title="t")
        apply_update(conn, task.id, "agent:a", state="blocked")
        assert ready_tasks(conn) == []

    def test_excludes_task_with_open_blocker(self, conn: sqlite3.Connection) -> None:
        """A task with an open `blocks` predecessor is excluded; the blocker itself is not."""
        blocker = insert_task(conn, title="blocker")
        blocked = insert_task(conn, title="blocked")
        link_tasks(conn, blocker.id, blocked.id, "blocks", "agent:a", None)
        assert [t.id for t in ready_tasks(conn)] == [blocker.id]

    def test_includes_task_once_blocker_is_done(self, conn: sqlite3.Connection) -> None:
        """Once the blocker reaches "done", the previously-blocked task becomes ready."""
        blocker = insert_task(conn, title="blocker")
        blocked = insert_task(conn, title="blocked")
        link_tasks(conn, blocker.id, blocked.id, "blocks", "agent:a", None)
        apply_update(conn, blocker.id, "agent:a", state="done")

        ready_ids = {t.id for t in ready_tasks(conn)}
        assert blocked.id in ready_ids
        assert blocker.id not in ready_ids


class TestSearchTasks:
    def test_matches_title_case_insensitively(self, conn: sqlite3.Connection) -> None:
        """Search matches the title regardless of case."""
        insert_task(conn, title="Fix the Auth Bug")
        insert_task(conn, title="unrelated")
        results = search_tasks(conn, "auth bug")
        assert len(results) == 1

    def test_matches_description(self, conn: sqlite3.Connection) -> None:
        """Search also matches a substring found only in the description."""
        insert_task(conn, title="t", description="contains a needle here")
        results = search_tasks(conn, "needle")
        assert len(results) == 1

    def test_escapes_percent_and_underscore(self, conn: sqlite3.Connection) -> None:
        """A literal % or _ in the search query matches literally, not as a LIKE wildcard."""
        insert_task(conn, title="100% done_deal")
        insert_task(conn, title="XXXXdoneXdeal")  # would match unescaped % and _ wildcards
        results = search_tasks(conn, "% done_")
        assert len(results) == 1

    def test_ignores_comments_by_default(self, conn: sqlite3.Connection) -> None:
        """A match only in a comment body is invisible without --include-comments."""
        task = insert_task(conn, title="t")
        record_comment(
            conn, task_id=task.id, body="found the xylophone bug", actor="a", session_id=None
        )
        assert search_tasks(conn, "xylophone") == []

    def test_include_comments_matches_comment_bodies(self, conn: sqlite3.Connection) -> None:
        """include_comments=True extends the match to comment text."""
        task = insert_task(conn, title="t")
        record_comment(
            conn, task_id=task.id, body="found the xylophone bug", actor="a", session_id=None
        )
        results = search_tasks(conn, "xylophone", include_comments=True)
        assert [t.id for t in results] == [task.id]


class TestMineTasks:
    def test_orders_by_claimed_at_desc(self, conn: sqlite3.Connection) -> None:
        """`mine` sorts by most-recently-claimed first, unlike every other list-shaped query."""
        first = insert_task(conn, title="first")
        second = insert_task(conn, title="second")
        claim_task(conn, first.id, "agent:a")
        claim_task(conn, second.id, "agent:a")
        # Force distinct timestamps — both claims can land in the same millisecond.
        conn.execute(
            "UPDATE tasks SET claimed_at = '2026-01-01T00:00:00.000Z' WHERE id = ?", (first.id,)
        )
        conn.execute(
            "UPDATE tasks SET claimed_at = '2026-01-01T00:00:01.000Z' WHERE id = ?",
            (second.id,),
        )

        results = mine_tasks(conn, "agent:a")
        assert [t.id for t in results] == [second.id, first.id]

    def test_breaks_a_claimed_at_tie_on_id_desc(self, conn: sqlite3.Connection) -> None:
        """A claimed_at tie breaks on id desc, matching every other ordering's
        tiebreak convention (`_ORDER_BY`, `cli/scope.py`'s sort helpers) instead
        of the opposite direction.
        """
        first = insert_task(conn, title="first")
        second = insert_task(conn, title="second")
        claim_task(conn, first.id, "agent:a")
        claim_task(conn, second.id, "agent:a")
        same_claimed_at = "2026-01-01T00:00:00.000Z"
        conn.execute(
            "UPDATE tasks SET claimed_at = ? WHERE id IN (?, ?)",
            (same_claimed_at, first.id, second.id),
        )

        results = mine_tasks(conn, "agent:a")
        assert [t.id for t in results] == [second.id, first.id]

    def test_only_includes_own_open_claims(self, conn: sqlite3.Connection) -> None:
        """`mine` includes only tasks the given actor holds, not another actor's claims."""
        mine = insert_task(conn, title="mine")
        others = insert_task(conn, title="others")
        claim_task(conn, mine.id, "agent:a")
        claim_task(conn, others.id, "agent:b")

        results = mine_tasks(conn, "agent:a")
        assert [t.id for t in results] == [mine.id]

    def test_includes_unclaimed_tasks_assigned_to_the_actor(self, conn: sqlite3.Connection) -> None:
        """`mine` also surfaces open, unclaimed tasks routed to the actor via
        `assign` (advisory, §4.4), not only ones it has claimed.
        """
        task = insert_task(conn, title="routed")
        assign_task(conn, task.id, "agent:a", "human:supervisor")

        results = mine_tasks(conn, "agent:a")
        assert [t.id for t in results] == [task.id]

    def test_excludes_a_task_assigned_to_the_actor_but_claimed_by_someone_else(
        self, conn: sqlite3.Connection
    ) -> None:
        """Once another actor claims an assigned task, it drops out of the
        assignee's `mine` — the claim is the actual, non-advisory signal.
        """
        task = insert_task(conn, title="routed")
        assign_task(conn, task.id, "agent:a", "human:supervisor")
        claim_task(conn, task.id, "agent:b")

        assert mine_tasks(conn, "agent:a") == []

    def test_does_not_include_tasks_assigned_to_someone_else(
        self, conn: sqlite3.Connection
    ) -> None:
        """An assignment to a different actor never leaks into this actor's `mine`."""
        task = insert_task(conn, title="routed")
        assign_task(conn, task.id, "agent:b", "human:supervisor")

        assert mine_tasks(conn, "agent:a") == []


class TestAssignTask:
    def test_sets_assigned_to_without_claiming(self, conn: sqlite3.Connection) -> None:
        """Assigning a task is advisory routing: it never touches claimed_by."""
        task = insert_task(conn, title="t")
        result = assign_task(conn, task.id, "agent:a", "human:supervisor")
        assert result.assigned_to == "agent:a"
        assert result.claimed_by is None

    def test_not_gated_by_an_existing_claim(self, conn: sqlite3.Connection) -> None:
        """Assignment succeeds even when another actor already holds the claim."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:b")
        result = assign_task(conn, task.id, "agent:a", "human:supervisor")
        assert result.assigned_to == "agent:a"
        assert result.claimed_by == "agent:b"

    def test_reassigning_to_a_different_actor_overwrites_it(self, conn: sqlite3.Connection) -> None:
        """A second `assign` to a different actor replaces the previous one."""
        task = insert_task(conn, title="t")
        assign_task(conn, task.id, "agent:a", "human:supervisor")
        result = assign_task(conn, task.id, "agent:b", "human:supervisor")
        assert result.assigned_to == "agent:b"

    def test_reassigning_to_the_same_actor_is_a_no_op(self, conn: sqlite3.Connection) -> None:
        """Assigning to the actor already holding it writes no event."""
        task = insert_task(conn, title="t")
        assign_task(conn, task.id, "agent:a", "human:supervisor")
        events_before = conn.execute("SELECT COUNT(*) FROM task_events").fetchone()[0]
        assign_task(conn, task.id, "agent:a", "human:supervisor")
        events_after = conn.execute("SELECT COUNT(*) FROM task_events").fetchone()[0]
        assert events_after == events_before

    def test_records_a_field_change_event(self, conn: sqlite3.Connection) -> None:
        """Assignment is audited the same way any other field change is."""
        task = insert_task(conn, title="t")
        assign_task(conn, task.id, "agent:a", "human:supervisor", session_id="s1")
        events, _ = get_task_events(conn, task.id)
        change = next(e for e in events if e["kind"] == "field_change")
        assert change["field"] == "assigned_to"
        assert change["old_value"] is None
        assert change["new_value"] == "agent:a"
        assert change["actor"] == "human:supervisor"
        assert change["session_id"] == "s1"


class TestUnassignTask:
    def test_clears_assigned_to(self, conn: sqlite3.Connection) -> None:
        task = insert_task(conn, title="t")
        assign_task(conn, task.id, "agent:a", "human:supervisor")
        result = unassign_task(conn, task.id, "human:supervisor")
        assert result.assigned_to is None

    def test_on_an_already_unassigned_task_is_a_no_op_success(
        self, conn: sqlite3.Connection
    ) -> None:
        task = insert_task(conn, title="t")
        result = unassign_task(conn, task.id, "human:supervisor")
        assert result.assigned_to is None


class TestAddComment:
    def test_appears_in_timeline(self, conn: sqlite3.Connection) -> None:
        """A comment is recorded as a "comment"-kind event in the task's timeline."""
        task = insert_task(conn, title="t")
        add_comment(conn, task.id, "handoff note", "agent:a", "session-1")
        events, omitted = get_task_events(conn, task.id)
        assert omitted == 0
        assert len(events) == 1
        assert events[0]["kind"] == "comment"
        assert events[0]["body"] == "handoff note"

    def test_by_claimant_refreshes_claimed_at(self, conn: sqlite3.Connection) -> None:
        """A comment from the current claimant refreshes claimed_at, the heartbeat rule."""
        task = insert_task(conn, title="t")
        before = claim_task(conn, task.id, "agent:a")
        assert before.claimed_at is not None
        updated = add_comment(conn, task.id, "still working", "agent:a", None)
        assert updated.claimed_at is not None
        assert updated.claimed_at >= before.claimed_at

    def test_by_bystander_does_not_touch_claim(self, conn: sqlite3.Connection) -> None:
        """A comment from a different actor is no liveness evidence; claimed_at stays put."""
        task = insert_task(conn, title="t")
        before = claim_task(conn, task.id, "agent:a")
        updated = add_comment(conn, task.id, "note", "agent:b", None)
        assert updated.claimed_at == before.claimed_at


class TestEventQueries:
    def test_get_last_comment_returns_most_recent(self, conn: sqlite3.Connection) -> None:
        """get_last_comment returns the most recently added comment, not the first."""
        task = insert_task(conn, title="t")
        add_comment(conn, task.id, "first", "agent:a", None)
        add_comment(conn, task.id, "second", "agent:a", None)
        last = get_last_comment(conn, task.id)
        assert last is not None
        assert last["body"] == "second"

    def test_get_task_events_since_reports_omitted_count(self, conn: sqlite3.Connection) -> None:
        """A `since` cutoff keeps only newer events and reports how many older ones were omitted."""
        task = insert_task(conn, title="t")
        add_comment(conn, task.id, "old", "agent:a", None)
        conn.execute(
            "UPDATE task_events SET created_at = '2026-01-01T00:00:00.000Z' WHERE task_id = ?",
            (task.id,),
        )
        add_comment(conn, task.id, "new", "agent:a", None)
        conn.execute(
            "UPDATE task_events SET created_at = '2026-01-02T00:00:00.000Z'"
            " WHERE task_id = ? AND body = 'new'",
            (task.id,),
        )

        kept, omitted = get_task_events(conn, task.id, since="2026-01-01T12:00:00.000Z")
        assert omitted == 1
        assert len(kept) == 1
        assert kept[0]["body"] == "new"
