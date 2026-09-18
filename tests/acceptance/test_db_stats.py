#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import itertools
import sqlite3

from corvee.db.events import record_comment
from corvee.db.facts import insert_fact, retract_fact, verify_fact
from corvee.db.labels import add_label
from corvee.db.stats import claims_summary, integrity_findings, project_stats
from corvee.db.tasks import apply_update, claim_task, insert_task, require_task
from corvee.timeutil import timestamp

ACTOR = "agent:test"


class TestProjectStats:
    def test_empty_project(self, conn: sqlite3.Connection) -> None:
        """An empty project reports all-zero counts, not an error."""
        stats = project_stats(conn, stale_before=None)
        assert stats["tasks"]["total"] == 0
        assert stats["tasks"]["claimed"] == 0
        assert stats["tasks"]["stale"] == 0
        assert stats["facts"]["total"] == 0
        assert stats["labels"] == 0

    def test_counts_tasks_by_state(self, conn: sqlite3.Connection) -> None:
        """by_state reflects every task regardless of open/closed, unlike task list's default."""
        todo = insert_task(conn, title="todo task")
        done = insert_task(conn, title="done task")
        apply_update(conn, done.id, ACTOR, state="done")

        stats = project_stats(conn, stale_before=None)
        assert stats["tasks"]["total"] == 2
        assert stats["tasks"]["by_state"]["open"] == 1
        assert stats["tasks"]["by_state"]["done"] == 1
        assert stats["tasks"]["by_state"]["blocked"] == 0
        assert todo.id != done.id

    def test_counts_claimed_tasks(self, conn: sqlite3.Connection) -> None:
        """claimed counts tasks currently held by any actor."""
        task = insert_task(conn, title="task")
        claim_task(conn, task.id, ACTOR)
        insert_task(conn, title="unclaimed task")

        stats = project_stats(conn, stale_before=None)
        assert stats["tasks"]["claimed"] == 1

    def test_counts_stale_tasks_against_the_given_cutoff(self, conn: sqlite3.Connection) -> None:
        """stale counts claims whose claimed_at is older than stale_before."""
        task = insert_task(conn, title="task")
        claim_task(conn, task.id, ACTOR)
        conn.execute(
            "UPDATE tasks SET claimed_at = '2020-01-01T00:00:00.000Z' WHERE id = ?", (task.id,)
        )

        stats = project_stats(conn, stale_before=timestamp())
        assert stats["tasks"]["stale"] == 1

    def test_stale_is_zero_when_no_cutoff_given(self, conn: sqlite3.Connection) -> None:
        """stale_before=None (no --stale duration) reports 0 rather than counting everything."""
        task = insert_task(conn, title="task")
        claim_task(conn, task.id, ACTOR)
        stats = project_stats(conn, stale_before=None)
        assert stats["tasks"]["stale"] == 0

    def test_counts_facts_by_status(self, conn: sqlite3.Connection) -> None:
        """by_status reflects every fact regardless of retracted, unlike fact list's default."""
        verified = insert_fact(conn, claim="a", actor=ACTOR)
        verify_fact(conn, verified.id, "proof", ACTOR)
        retracted = insert_fact(conn, claim="b", actor=ACTOR)
        retract_fact(conn, retracted.id, ACTOR)
        insert_fact(conn, claim="c", actor=ACTOR)

        stats = project_stats(conn, stale_before=None)
        assert stats["facts"]["total"] == 3
        assert stats["facts"]["by_status"]["verified"] == 1
        assert stats["facts"]["by_status"]["retracted"] == 1
        assert stats["facts"]["by_status"]["unverified"] == 1

    def test_counts_distinct_labels(self, conn: sqlite3.Connection) -> None:
        """labels counts distinct label names in the project, not label attachments."""
        task = insert_task(conn, title="task")
        add_label(conn, task.id, "api", ACTOR, None)
        add_label(conn, task.id, "urgent", ACTOR, None)

        stats = project_stats(conn, stale_before=None)
        assert stats["labels"] == 2


class TestIntegrityFindings:
    def test_healthy_project_reports_no_findings(self, conn: sqlite3.Connection) -> None:
        """A project with no cycles and no dangling rows reports an empty list."""
        insert_task(conn, title="a")
        assert integrity_findings(conn) == []

    def test_detects_a_parent_of_cycle(self, conn: sqlite3.Connection) -> None:
        """A parent_of cycle, only possible via a hand-edited database, is reported."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'parent_of')",
            (a.id, b.id),
        )
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'parent_of')",
            (b.id, a.id),
        )

        findings = integrity_findings(conn)
        assert len(findings) == 1
        assert findings[0]["kind"] == "cycle"
        assert findings[0]["relation"] == "parent_of"
        assert set(findings[0]["task_ids"]) == {f"TASK-{a.id}", f"TASK-{b.id}"}

    def test_detects_a_blocks_cycle(self, conn: sqlite3.Connection) -> None:
        """A blocks cycle is reported separately from parent_of cycles."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'blocks')",
            (a.id, b.id),
        )
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'blocks')",
            (b.id, a.id),
        )

        findings = integrity_findings(conn)
        assert [f["relation"] for f in findings] == ["blocks"]

    def test_formats_task_ids_for_the_given_scope(self, conn: sqlite3.Connection) -> None:
        """task_ids in a cycle finding use the caller's scope, like every other task ref."""
        a = insert_task(conn, title="a")
        b = insert_task(conn, title="b")
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'blocks')",
            (a.id, b.id),
        )
        conn.execute(
            "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'blocks')",
            (b.id, a.id),
        )

        findings = integrity_findings(conn, scope="global")
        assert set(findings[0]["task_ids"]) == {f"TASK-GLOBAL-{a.id}", f"TASK-GLOBAL-{b.id}"}

    def test_detects_a_dangling_foreign_key(self, conn: sqlite3.Connection) -> None:
        """A label attachment pointing at a deleted task is reported, not silently ignored.

        Only reachable with foreign_keys off, like a database edited by
        something other than corvee itself (corvee's own connections always
        run with it on and would refuse this delete).
        """
        task = insert_task(conn, title="a")
        add_label(conn, task.id, "api", ACTOR, None)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM tasks WHERE id = ?", (task.id,))
        conn.execute("PRAGMA foreign_keys = ON")

        findings = integrity_findings(conn)
        assert findings
        assert all(f["kind"] == "dangling_foreign_key" for f in findings)
        assert "task_labels" in {f["table"] for f in findings}

    # A cutoff safely in the past relative to real event timestamps: recent
    # ("in the window") means created_at >= this, the same direction
    # project_stats's own stale check already uses (see
    # test_counts_stale_tasks_against_the_given_cutoff above).
    RECENT_CUTOFF = "2020-01-01T00:00:00.000Z"

    def test_detects_two_sessions_sharing_one_actor_on_a_claimed_task(
        self, conn: sqlite3.Connection
    ) -> None:
        """A currently-claimed task whose claimant's own recent events carry two
        distinct session ids is the detectable signature of two unconfigured
        sessions colliding under one actor string (GH#24).
        """
        task = insert_task(conn, title="a")
        claim_task(conn, task.id, ACTOR, session_id="session-a")
        claim_task(conn, task.id, ACTOR, session_id="session-b")

        findings = integrity_findings(conn, stale_before=self.RECENT_CUTOFF)
        assert findings == [
            {
                "kind": "shared_actor_sessions",
                "task_id": f"TASK-{task.id}",
                "actor": ACTOR,
                "session_ids": ["session-a", "session-b"],
            }
        ]

    def test_no_finding_with_only_one_session(self, conn: sqlite3.Connection) -> None:
        """A claim heartbeated twice under the same session id is not a collision."""
        task = insert_task(conn, title="a")
        claim_task(conn, task.id, ACTOR, session_id="session-a")
        claim_task(conn, task.id, ACTOR, session_id="session-a")

        assert integrity_findings(conn, stale_before=self.RECENT_CUTOFF) == []

    def test_no_finding_when_stale_before_is_not_given(self, conn: sqlite3.Connection) -> None:
        """The check is skipped entirely without a cutoff, like project_stats's stale count."""
        task = insert_task(conn, title="a")
        claim_task(conn, task.id, ACTOR, session_id="session-a")
        claim_task(conn, task.id, ACTOR, session_id="session-b")

        assert integrity_findings(conn) == []

    def test_no_finding_for_activity_outside_the_recent_window(
        self, conn: sqlite3.Connection
    ) -> None:
        """A second session's claim from before the cutoff is ordinary resuming,
        not a live collision -- only recent multi-session activity counts.
        """
        task = insert_task(conn, title="a")
        claim_task(conn, task.id, ACTOR, session_id="session-a")
        conn.execute(
            "UPDATE task_events SET created_at = '2000-01-01T00:00:00.000Z' WHERE task_id = ?",
            (task.id,),
        )
        claim_task(conn, task.id, ACTOR, session_id="session-b")

        assert integrity_findings(conn, stale_before=self.RECENT_CUTOFF) == []

    def test_no_finding_for_a_bystander_comment_from_another_actor(
        self, conn: sqlite3.Connection
    ) -> None:
        """Comments from a non-claimant are open to anyone (§4.4) and never count
        toward the claimant's own session diversity.
        """
        task = insert_task(conn, title="a")
        claim_task(conn, task.id, ACTOR, session_id="session-a")
        record_comment(conn, task_id=task.id, body="fyi", actor="agent:other", session_id="s2")

        assert integrity_findings(conn, stale_before=self.RECENT_CUTOFF) == []

    def test_survives_a_chain_deeper_than_the_python_recursion_limit(
        self, conn: sqlite3.Connection
    ) -> None:
        """A long, perfectly valid (acyclic) parent_of chain must not raise
        RecursionError -- cycle detection has to stay safe against any
        size/shape of database, not just small ones, since that is the
        whole point of `doctor`.
        """
        ids = [insert_task(conn, title=f"t{i}").id for i in range(3000)]
        for parent, child in itertools.pairwise(ids):
            conn.execute(
                "INSERT INTO task_links (source_id, target_id, relation)"
                " VALUES (?, ?, 'parent_of')",
                (parent, child),
            )

        assert integrity_findings(conn) == []


class TestClaimsSummary:
    def test_empty_project_returns_no_rows(self, conn: sqlite3.Connection) -> None:
        """No claims at all yields an empty list, not an error."""
        assert claims_summary(conn) == []

    def test_groups_by_actor_with_count_and_oldest_claimed_at(
        self, conn: sqlite3.Connection
    ) -> None:
        """Each actor holding at least one claim gets one row: count and the oldest claimed_at."""
        a1 = insert_task(conn, title="a1")
        a2 = insert_task(conn, title="a2")
        b1 = insert_task(conn, title="b1")
        insert_task(conn, title="unclaimed")
        claim_task(conn, a1.id, "agent:a")
        claim_task(conn, a2.id, "agent:a")
        claim_task(conn, b1.id, "agent:b")

        summary = {row["actor"]: row for row in claims_summary(conn)}
        assert summary["agent:a"]["count"] == 2
        assert summary["agent:b"]["count"] == 1
        assert summary["agent:a"]["oldest_claimed_at"] == require_task(conn, a1.id).claimed_at

    def test_oldest_claim_first(self, conn: sqlite3.Connection) -> None:
        """Rows are ordered by oldest_claimed_at ascending, the longest-held claim first."""
        first = insert_task(conn, title="first")
        second = insert_task(conn, title="second")
        claim_task(conn, first.id, "agent:a")
        claim_task(conn, second.id, "agent:b")
        conn.execute(
            "UPDATE tasks SET claimed_at = '2020-01-01T00:00:00.000Z' WHERE id = ?", (first.id,)
        )
        conn.execute(
            "UPDATE tasks SET claimed_at = '2026-01-01T00:00:00.000Z' WHERE id = ?", (second.id,)
        )

        actors = [row["actor"] for row in claims_summary(conn)]
        assert actors == ["agent:a", "agent:b"]
