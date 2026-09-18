#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3

import pytest

from corvee.db.events import get_task_events
from corvee.db.tasks import apply_update, claim_task, insert_task, require_task, unclaim_task
from corvee.errors import ClaimConflictError, GuardViolationError
from corvee.models import task_ref


class TestClaimTask:
    def test_unclaimed_task_succeeds(self, conn: sqlite3.Connection) -> None:
        """Claiming an unclaimed task sets claimed_by and stamps claimed_at."""
        task = insert_task(conn, title="t")
        claimed = claim_task(conn, task.id, "agent:a")
        assert claimed.claimed_by == "agent:a"
        assert claimed.claimed_at is not None

    def test_repeat_claim_by_same_actor_refreshes_claimed_at(
        self, conn: sqlite3.Connection
    ) -> None:
        """Re-claiming a task the caller already holds refreshes claimed_at (the heartbeat)."""
        task = insert_task(conn, title="t")
        first = claim_task(conn, task.id, "agent:a")
        second = claim_task(conn, task.id, "agent:a")
        assert second.claimed_by == "agent:a"
        assert first.claimed_at is not None
        assert second.claimed_at is not None
        assert second.claimed_at >= first.claimed_at

    def test_by_different_actor_without_force_raises(self, conn: sqlite3.Connection) -> None:
        """Claiming a task another actor holds raises ClaimConflictError (exit 4) without force."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        with pytest.raises(ClaimConflictError) as excinfo:
            claim_task(conn, task.id, "agent:b")
        assert excinfo.value.exit_code == 4
        assert excinfo.value.extra["claimed_by"] == "agent:a"

    def test_by_different_actor_with_force_steals_it(self, conn: sqlite3.Connection) -> None:
        """force=True lets a different actor steal an existing claim."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        stolen = claim_task(conn, task.id, "agent:b", force=True)
        assert stolen.claimed_by == "agent:b"

    def test_a_done_task_raises_guard_violation(self, conn: sqlite3.Connection) -> None:
        """Claiming an already-done task is rejected rather than leaving a stray,
        never-stale claim on a task nobody is actually working on.
        """
        task = insert_task(conn, title="t")
        apply_update(conn, task.id, "agent:a", state="done")
        with pytest.raises(GuardViolationError) as excinfo:
            claim_task(conn, task.id, "agent:a")
        assert excinfo.value.exit_code == 5
        assert excinfo.value.code == "task_terminal"
        assert require_task(conn, task.id).claimed_by is None

    def test_a_cancelled_task_raises_guard_violation(self, conn: sqlite3.Connection) -> None:
        """Same rejection for a cancelled task, the other terminal state."""
        task = insert_task(conn, title="t")
        apply_update(conn, task.id, "agent:a", state="cancelled")
        with pytest.raises(GuardViolationError):
            claim_task(conn, task.id, "agent:a")

    def test_a_done_task_raises_even_with_force(self, conn: sqlite3.Connection) -> None:
        """--force overrides a conflicting claimant, not a task being finished."""
        task = insert_task(conn, title="t")
        apply_update(conn, task.id, "agent:a", state="done")
        with pytest.raises(GuardViolationError):
            claim_task(conn, task.id, "agent:b", force=True)


class TestUnclaimTask:
    def test_unclaimed_task_is_a_no_op(self, conn: sqlite3.Connection) -> None:
        """Unclaiming an already-unclaimed task succeeds without error."""
        task = insert_task(conn, title="t")
        result = unclaim_task(conn, task.id, "agent:a")
        assert result.claimed_by is None

    def test_own_claim_clears_it(self, conn: sqlite3.Connection) -> None:
        """Unclaiming a task the caller holds clears both claimed_by and claimed_at."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        result = unclaim_task(conn, task.id, "agent:a")
        assert result.claimed_by is None
        assert result.claimed_at is None

    def test_someone_elses_claim_without_force_raises(self, conn: sqlite3.Connection) -> None:
        """Unclaiming someone else's task without --force raises ClaimConflictError."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        with pytest.raises(ClaimConflictError):
            unclaim_task(conn, task.id, "agent:b")

    def test_someone_elses_claim_with_force_succeeds(self, conn: sqlite3.Connection) -> None:
        """force=True lets a different actor release someone else's claim."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        result = unclaim_task(conn, task.id, "agent:b", force=True)
        assert result.claimed_by is None


class TestApplyUpdateTransientClaimRules:
    def test_unclaimed_task_takes_and_releases_transient_claim(
        self, conn: sqlite3.Connection
    ) -> None:
        """Updating an unclaimed task takes and releases a transient claim in the same call."""
        task = insert_task(conn, title="t")
        results = apply_update(conn, task.id, "agent:a", title="new title")
        updated = results[0]
        assert updated.title == "new title"
        assert updated.claimed_by is None

    def test_update_to_in_progress_keeps_the_claim(self, conn: sqlite3.Connection) -> None:
        """A --state in_progress update is the one case that keeps the transient claim."""
        task = insert_task(conn, title="t")
        results = apply_update(conn, task.id, "agent:a", state="in_progress")
        assert results[0].claimed_by == "agent:a"

    def test_field_only_update_on_already_in_progress_task_releases_claim(
        self, conn: sqlite3.Connection
    ) -> None:
        """A field-only edit landing on an already-in_progress task must not keep the claim.

        Only an explicit --state in_progress should keep it; the resulting
        state happening to already be in_progress is not the same thing.
        """
        task = insert_task(conn, title="t")
        apply_update(conn, task.id, "agent:a", state="in_progress")
        unclaim_task(conn, task.id, "agent:a")

        results = apply_update(conn, task.id, "agent:b", priority="high")

        assert results[0].priority == "high"
        assert results[0].claimed_by is None

    def test_by_current_claimant_does_not_release_claim(self, conn: sqlite3.Connection) -> None:
        """An update by the actor who already holds the claim leaves that claim in place."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        results = apply_update(conn, task.id, "agent:a", title="renamed")
        assert results[0].claimed_by == "agent:a"

    def test_by_current_claimant_refreshes_claimed_at(self, conn: sqlite3.Connection) -> None:
        """An update by the current claimant refreshes claimed_at, the same as a repeat claim."""
        task = insert_task(conn, title="t")
        before = claim_task(conn, task.id, "agent:a")
        results = apply_update(conn, task.id, "agent:a", title="renamed")
        assert before.claimed_at is not None
        assert results[0].claimed_at is not None
        assert results[0].claimed_at >= before.claimed_at

    def test_with_claim_held_by_other_actor_raises_without_force(
        self, conn: sqlite3.Connection
    ) -> None:
        """Updating a task claimed by another actor raises, leaving the task's fields unchanged."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        with pytest.raises(ClaimConflictError) as excinfo:
            apply_update(conn, task.id, "agent:b", title="stolen title")
        assert excinfo.value.exit_code == 4
        unchanged = require_task(conn, task.id)
        assert unchanged.title == "t"

    def test_with_force_steals_and_follows_transient_release_rule(
        self, conn: sqlite3.Connection
    ) -> None:
        """force=True on update steals the claim, applies the change, then releases it."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        results = apply_update(conn, task.id, "agent:b", title="stolen", force=True)
        assert results[0].title == "stolen"
        assert results[0].claimed_by is None

    def test_reaching_done_clears_claim(self, conn: sqlite3.Connection) -> None:
        """Reaching the terminal "done" state clears the claim, even the current claimant's own."""
        task = insert_task(conn, title="t")
        claim_task(conn, task.id, "agent:a")
        results = apply_update(conn, task.id, "agent:a", state="done")
        assert results[0].state == "done"
        assert results[0].claimed_by is None

    def test_same_state_update_is_a_no_op_but_other_fields_still_apply(
        self, conn: sqlite3.Connection
    ) -> None:
        """Setting state to its current value is a no-op; other fields in the call still apply."""
        task = insert_task(conn, title="t")
        results = apply_update(conn, task.id, "agent:a", state="open", title="renamed")
        assert results[0].state == "open"
        assert results[0].title == "renamed"

    def test_invalid_transition_raises_guard_violation(self, conn: sqlite3.Connection) -> None:
        """A transition absent from the state table raises GuardViolationError (exit 5)."""
        task = insert_task(conn, title="t")
        apply_update(conn, task.id, "agent:a", state="done")
        with pytest.raises(GuardViolationError) as excinfo:
            apply_update(conn, task.id, "agent:a", state="cancelled")
        assert excinfo.value.exit_code == 5

    def test_transient_call_that_changes_nothing_writes_no_events(
        self, conn: sqlite3.Connection
    ) -> None:
        """A transient (not-already-claimed-by-actor) call requesting a state
        that already holds and no field changes must not take-and-release a
        claim it never needed -- that would misleadingly show up in
        task_events as "claimed then immediately released" by an actor who
        never actually claimed it for anything (unlike `revise_fact`/
        `add_label`/`remove_label`, which already short-circuit this way).
        This is exactly what happens when a --cascade side effect already
        landed a task in its target state and the same id is also named
        explicitly in the same multi-id call.
        """
        task = insert_task(conn, title="t")
        apply_update(conn, task.id, "agent:a", state="done")
        before_events, _ = get_task_events(conn, task.id)

        results = apply_update(conn, task.id, "agent:b", state="done")

        assert results[0].state == "done"
        assert results[0].claimed_by is None
        after_events, _ = get_task_events(conn, task.id)
        assert after_events == before_events


def _link_parent_of(conn: sqlite3.Connection, parent_id: int, child_id: int) -> None:
    conn.execute(
        "INSERT INTO task_links (source_id, target_id, relation) VALUES (?, ?, 'parent_of')",
        (parent_id, child_id),
    )


class TestApplyUpdateParentChildGuardAndCascade:
    def test_cannot_close_while_child_is_open(self, conn: sqlite3.Connection) -> None:
        """Closing a parent while a child is still open raises and lists the blocking child id."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        _link_parent_of(conn, parent.id, child.id)

        with pytest.raises(GuardViolationError) as excinfo:
            apply_update(conn, parent.id, "agent:a", state="done")
        assert excinfo.value.exit_code == 5
        assert excinfo.value.extra["blocking_ids"] == [task_ref(child.id)]

    def test_can_close_when_children_are_terminal(self, conn: sqlite3.Connection) -> None:
        """Closing a parent succeeds once every child has reached a terminal state."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        _link_parent_of(conn, parent.id, child.id)
        apply_update(conn, child.id, "agent:a", state="done")

        results = apply_update(conn, parent.id, "agent:a", state="done")
        assert results[0].state == "done"

    def test_cancel_without_cascade_rejected_while_child_open(
        self, conn: sqlite3.Connection
    ) -> None:
        """Cancelling a parent without --cascade is rejected too, while a child is open."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        _link_parent_of(conn, parent.id, child.id)

        with pytest.raises(GuardViolationError):
            apply_update(conn, parent.id, "agent:a", state="cancelled")

    def test_cancel_with_cascade_cancels_open_descendants_and_keeps_done_ones(
        self, conn: sqlite3.Connection
    ) -> None:
        """--cascade cancels every open descendant, clearing own-actor claims, leaves done ones."""
        parent = insert_task(conn, title="parent")
        open_child = insert_task(conn, title="open-child")
        done_child = insert_task(conn, title="done-child")
        grandchild = insert_task(conn, title="grandchild")
        _link_parent_of(conn, parent.id, open_child.id)
        _link_parent_of(conn, parent.id, done_child.id)
        _link_parent_of(conn, open_child.id, grandchild.id)
        apply_update(conn, done_child.id, "agent:a", state="done")
        claim_task(conn, open_child.id, "agent:a")

        results = apply_update(conn, parent.id, "agent:a", state="cancelled", cascade=True)

        result_by_id = {t.id: t for t in results}
        assert result_by_id[parent.id].state == "cancelled"
        assert result_by_id[open_child.id].state == "cancelled"
        assert result_by_id[open_child.id].claimed_by is None
        assert result_by_id[grandchild.id].state == "cancelled"
        assert done_child.id not in result_by_id
        assert require_task(conn, done_child.id).state == "done"

    def test_cascade_without_force_rejects_descendant_claimed_by_another_actor(
        self, conn: sqlite3.Connection
    ) -> None:
        """A descendant claimed by another actor blocks --cascade, like a claim conflict."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        _link_parent_of(conn, parent.id, child.id)
        claim_task(conn, child.id, "agent:b")

        with pytest.raises(ClaimConflictError) as excinfo:
            apply_update(conn, parent.id, "agent:a", state="cancelled", cascade=True)
        assert excinfo.value.extra["claimed_by"] == "agent:b"
        assert require_task(conn, child.id).state == "open"
        assert require_task(conn, child.id).claimed_by == "agent:b"

    def test_cascade_with_force_steals_descendant_claimed_by_another_actor(
        self, conn: sqlite3.Connection
    ) -> None:
        """--force lets --cascade clear a descendant's claim held by another actor."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        _link_parent_of(conn, parent.id, child.id)
        claim_task(conn, child.id, "agent:b")

        results = apply_update(
            conn, parent.id, "agent:a", state="cancelled", cascade=True, force=True
        )

        result_by_id = {t.id: t for t in results}
        assert result_by_id[child.id].state == "cancelled"
        assert result_by_id[child.id].claimed_by is None


class TestApplyUpdateReopenWarning:
    def test_reopening_child_of_done_parent_warns(self, conn: sqlite3.Connection) -> None:
        """Reopening a done child whose parent is also done surfaces a warning."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        _link_parent_of(conn, parent.id, child.id)
        apply_update(conn, child.id, "agent:a", state="done")
        apply_update(conn, parent.id, "agent:a", state="done")

        results = apply_update(conn, child.id, "agent:a", state="open")

        assert results[0].warnings == (
            f"parent {task_ref(parent.id)} is done while this task reopened",
        )

    def test_reopening_child_of_open_parent_does_not_warn(self, conn: sqlite3.Connection) -> None:
        """No warning when the parent isn't done."""
        parent = insert_task(conn, title="parent")
        child = insert_task(conn, title="child")
        _link_parent_of(conn, parent.id, child.id)
        apply_update(conn, child.id, "agent:a", state="done")

        results = apply_update(conn, child.id, "agent:a", state="open")

        assert results[0].warnings == ()

    def test_ordinary_transition_does_not_warn(self, conn: sqlite3.Connection) -> None:
        """No warning for a plain state change that isn't a reopen."""
        task = insert_task(conn, title="t")

        results = apply_update(conn, task.id, "agent:a", state="in_progress")

        assert results[0].warnings == ()
