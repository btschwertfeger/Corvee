#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3

import pytest

from corvee.db.events import get_fact_events
from corvee.db.facts import (
    FactFilter,
    delete_fact,
    get_fact,
    insert_fact,
    list_facts,
    require_fact,
    require_facts,
    retract_fact,
    revise_fact,
    search_facts,
    unverify_fact,
    verify_fact,
)
from corvee.errors import GuardViolationError, NotFoundError

ACTOR = "agent:test"


class TestInsertFact:
    def test_sets_defaults_and_writes_created_event(self, conn: sqlite3.Connection) -> None:
        """A minimal insert defaults to status=unverified and writes a single "created" event."""
        fact = insert_fact(conn, claim="package X is MIT-licensed", actor=ACTOR)
        assert fact.claim == "package X is MIT-licensed"
        assert fact.status == "unverified"
        assert fact.verified_at is None
        assert fact.verified_by is None
        assert fact.proof is None
        # updated_at advances past created_at here, unlike a task: fact
        # creation writes a 'created' fact_events row, which bumps
        # facts.updated_at the same way any later event would.
        assert fact.updated_at >= fact.created_at

        events = get_fact_events(conn, fact.id)
        assert [e["kind"] for e in events] == ["created"]
        assert events[0]["new_value"] == "package X is MIT-licensed"
        assert events[0]["actor"] == ACTOR

    def test_with_proof_verifies_immediately(self, conn: sqlite3.Connection) -> None:
        """Passing proof at insert time verifies immediately ("created" then "verified")."""
        fact = insert_fact(conn, claim="claim", actor=ACTOR, proof="see LICENSE")
        assert fact.status == "verified"
        assert fact.proof == "see LICENSE"
        assert fact.verified_by == ACTOR
        assert fact.verified_at is not None

        events = get_fact_events(conn, fact.id)
        assert [e["kind"] for e in events] == ["created", "verified"]


class TestGetAndRequireFact:
    def test_get_fact_returns_none_when_missing(self, conn: sqlite3.Connection) -> None:
        """get_fact returns None for a missing id rather than raising."""
        assert get_fact(conn, 999) is None

    def test_require_fact_raises_not_found(self, conn: sqlite3.Connection) -> None:
        """require_fact raises NotFoundError (exit 3) naming the FACT-<n> form of the missing id."""
        with pytest.raises(NotFoundError) as excinfo:
            require_fact(conn, 999)
        assert excinfo.value.exit_code == 3
        assert excinfo.value.extra["fact_id"] == "FACT-999"

    def test_require_facts_preserves_given_order(self, conn: sqlite3.Connection) -> None:
        """require_facts returns facts in the order their ids were given, not insertion order."""
        a = insert_fact(conn, claim="a", actor=ACTOR)
        b = insert_fact(conn, claim="b", actor=ACTOR)
        result = require_facts(conn, [b.id, a.id])
        assert [f.id for f in result] == [b.id, a.id]


class TestListFacts:
    def test_excludes_retracted_by_default(self, conn: sqlite3.Connection) -> None:
        """The default filter excludes retracted facts."""
        kept = insert_fact(conn, claim="kept", actor=ACTOR)
        withdrawn = insert_fact(conn, claim="withdrawn", actor=ACTOR)
        retract_fact(conn, withdrawn.id, ACTOR)

        results = list_facts(conn, FactFilter())
        assert [f.id for f in results] == [kept.id]

    def test_includes_unverified_by_default(self, conn: sqlite3.Connection) -> None:
        """Unlike tasks, an unverified fact is not excluded by the default filter."""
        fact = insert_fact(conn, claim="unchecked", actor=ACTOR)
        results = list_facts(conn, FactFilter())
        assert [f.id for f in results] == [fact.id]

    def test_include_all(self, conn: sqlite3.Connection) -> None:
        """include_all=True returns facts regardless of status, retracted included."""
        kept = insert_fact(conn, claim="kept", actor=ACTOR)
        withdrawn = insert_fact(conn, claim="withdrawn", actor=ACTOR)
        retract_fact(conn, withdrawn.id, ACTOR)

        results = list_facts(conn, FactFilter(include_all=True))
        assert {f.id for f in results} == {kept.id, withdrawn.id}

    def test_filters_by_status(self, conn: sqlite3.Connection) -> None:
        """The status filter matches only facts holding exactly that status."""
        verified = insert_fact(conn, claim="v", actor=ACTOR, proof="proof")
        insert_fact(conn, claim="u", actor=ACTOR)

        results = list_facts(conn, FactFilter(status="verified"))
        assert [f.id for f in results] == [verified.id]

    def test_orders_by_id_descending(self, conn: sqlite3.Connection) -> None:
        """Facts sort by id descending (newest first); there is no priority to break ties on."""
        a = insert_fact(conn, claim="a", actor=ACTOR)
        b = insert_fact(conn, claim="b", actor=ACTOR)
        results = list_facts(conn, FactFilter())
        assert [f.id for f in results] == [b.id, a.id]

    def test_limit(self, conn: sqlite3.Connection) -> None:
        """limit caps the number of rows returned."""
        for i in range(5):
            insert_fact(conn, claim=f"f{i}", actor=ACTOR)
        results = list_facts(conn, FactFilter(limit=2))
        assert len(results) == 2

    def test_since_filter_matches_updated_at_cutoff(self, conn: sqlite3.Connection) -> None:
        """--since keeps facts updated at or after the cutoff, dropping older ones."""
        old = insert_fact(conn, claim="old", actor=ACTOR)
        recent = insert_fact(conn, claim="recent", actor=ACTOR)
        conn.execute(
            "UPDATE facts SET updated_at = '2020-01-01T00:00:00.000Z' WHERE id = ?", (old.id,)
        )
        conn.execute(
            "UPDATE facts SET updated_at = '2026-01-01T00:00:00.000Z' WHERE id = ?", (recent.id,)
        )

        results = list_facts(conn, FactFilter(updated_since="2025-01-01T00:00:00.000Z"))
        assert [f.id for f in results] == [recent.id]

    def test_verified_by_filter_matches_only_that_actor(self, conn: sqlite3.Connection) -> None:
        """--verified-by matches facts whose verified_by is exactly the given actor."""
        mine = insert_fact(conn, claim="mine", actor=ACTOR, proof="proof")
        insert_fact(conn, claim="theirs", actor="agent:b", proof="proof")
        insert_fact(conn, claim="unverified", actor=ACTOR)

        results = list_facts(conn, FactFilter(verified_by=ACTOR))
        assert [f.id for f in results] == [mine.id]

    def test_stale_filter_matches_verified_facts_past_the_cutoff(
        self, conn: sqlite3.Connection
    ) -> None:
        """--stale keeps verified facts whose verified_at predates the cutoff."""
        stale = insert_fact(conn, claim="stale", actor=ACTOR, proof="proof")
        fresh = insert_fact(conn, claim="fresh", actor=ACTOR, proof="proof")
        insert_fact(conn, claim="never verified", actor=ACTOR)
        conn.execute(
            "UPDATE facts SET verified_at = '2020-01-01T00:00:00.000Z' WHERE id = ?", (stale.id,)
        )
        conn.execute(
            "UPDATE facts SET verified_at = '2026-01-01T00:00:00.000Z' WHERE id = ?", (fresh.id,)
        )

        results = list_facts(conn, FactFilter(stale_before="2025-01-01T00:00:00.000Z"))
        assert [f.id for f in results] == [stale.id]

    def test_stale_filter_excludes_never_verified_facts(self, conn: sqlite3.Connection) -> None:
        """A fact with verified_at IS NULL never matches --stale, regardless of duration."""
        insert_fact(conn, claim="never verified", actor=ACTOR)
        results = list_facts(conn, FactFilter(stale_before="2099-01-01T00:00:00.000Z"))
        assert results == []


class TestSearchFacts:
    def test_finds_claim_substring(self, conn: sqlite3.Connection) -> None:
        """Search matches a case-insensitive substring of the claim text."""
        insert_fact(conn, claim="package X is MIT-licensed", actor=ACTOR)
        insert_fact(conn, claim="unrelated claim", actor=ACTOR)

        results = search_facts(conn, "MIT")
        assert len(results) == 1

    def test_excludes_retracted_by_default(self, conn: sqlite3.Connection) -> None:
        """Search excludes retracted facts by default; include_all brings them back."""
        fact = insert_fact(conn, claim="license claim", actor=ACTOR)
        retract_fact(conn, fact.id, ACTOR)

        assert search_facts(conn, "license") == []
        assert len(search_facts(conn, "license", include_all=True)) == 1

    def test_verified_by_filter_matches_only_that_actor(self, conn: sqlite3.Connection) -> None:
        """--verified-by narrows a search to facts verified by exactly that actor."""
        mine = insert_fact(conn, claim="license mine", actor=ACTOR, proof="proof")
        insert_fact(conn, claim="license theirs", actor="agent:b", proof="proof")

        results = search_facts(conn, "license", verified_by=ACTOR)
        assert [f.id for f in results] == [mine.id]

    def test_ignores_proof_by_default(self, conn: sqlite3.Connection) -> None:
        """A match only in proof text is invisible without include_proof."""
        insert_fact(conn, claim="claim text", actor=ACTOR, proof="see PR #123 for confirmation")
        assert search_facts(conn, "PR #123") == []

    def test_include_proof_matches_proof_text(self, conn: sqlite3.Connection) -> None:
        """include_proof=True extends the match to proof text."""
        fact = insert_fact(
            conn, claim="claim text", actor=ACTOR, proof="see PR #123 for confirmation"
        )
        results = search_facts(conn, "PR #123", include_proof=True)
        assert [f.id for f in results] == [fact.id]


class TestReviseFact:
    def test_identical_text_is_a_no_op(self, conn: sqlite3.Connection) -> None:
        """Revising to the exact current claim text writes no new event."""
        fact = insert_fact(conn, claim="claim text", actor=ACTOR)
        revised = revise_fact(conn, fact.id, "claim text", ACTOR)
        assert revised == fact
        events = get_fact_events(conn, fact.id)
        assert [e["kind"] for e in events] == ["created"]

    def test_different_text_writes_revised_event(self, conn: sqlite3.Connection) -> None:
        """Revising to genuinely different text updates the claim and writes a "revised" event."""
        fact = insert_fact(conn, claim="old claim", actor=ACTOR)
        revised = revise_fact(conn, fact.id, "new claim", ACTOR)
        assert revised.claim == "new claim"
        events = get_fact_events(conn, fact.id)
        assert [e["kind"] for e in events] == ["created", "revised"]
        assert events[1]["old_value"] == "old claim"
        assert events[1]["new_value"] == "new claim"

    def test_revising_a_verified_fact_resets_it_to_unverified(
        self, conn: sqlite3.Connection
    ) -> None:
        """Changing the claim of a verified fact resets it to unverified, clearing proof fields."""
        fact = insert_fact(conn, claim="old claim", actor=ACTOR, proof="proof")
        revised = revise_fact(conn, fact.id, "new claim", ACTOR)
        assert revised.status == "unverified"
        assert revised.verified_at is None
        assert revised.verified_by is None
        assert revised.proof is None

        events = get_fact_events(conn, fact.id)
        assert [e["kind"] for e in events] == ["created", "verified", "revised", "unverified"]

    def test_revising_an_unverified_fact_does_not_write_unverified_event(
        self, conn: sqlite3.Connection
    ) -> None:
        """Revising an already-unverified fact does not add a redundant "unverified" event."""
        fact = insert_fact(conn, claim="old claim", actor=ACTOR)
        revise_fact(conn, fact.id, "new claim", ACTOR)
        events = get_fact_events(conn, fact.id)
        assert [e["kind"] for e in events] == ["created", "revised"]

    def test_revising_a_retracted_fact_moves_it_back_to_unverified(
        self, conn: sqlite3.Connection
    ) -> None:
        """Revising a retracted fact's text moves it back into the normal flow, not a dead end."""
        fact = insert_fact(conn, claim="old claim", actor=ACTOR)
        retract_fact(conn, fact.id, ACTOR)
        revised = revise_fact(conn, fact.id, "new claim", ACTOR)
        assert revised.status == "unverified"
        assert revised.claim == "new claim"

        events = get_fact_events(conn, fact.id)
        assert [e["kind"] for e in events] == ["created", "retracted", "revised", "unverified"]


class TestVerifyFact:
    def test_sets_status_and_denormalized_fields(self, conn: sqlite3.Connection) -> None:
        """Verifying sets status=verified and stamps proof/verified_by/verified_at."""
        fact = insert_fact(conn, claim="claim", actor=ACTOR)
        verified = verify_fact(conn, fact.id, "see file.py:12", ACTOR)
        assert verified.status == "verified"
        assert verified.proof == "see file.py:12"
        assert verified.verified_by == ACTOR
        assert verified.verified_at is not None

    def test_reverifying_an_already_verified_fact_refreshes_proof(
        self, conn: sqlite3.Connection
    ) -> None:
        """Re-verifying an already-verified fact succeeds and replaces the recorded proof."""
        fact = insert_fact(conn, claim="claim", actor=ACTOR, proof="old proof")
        reverified = verify_fact(conn, fact.id, "new proof", ACTOR)
        assert reverified.proof == "new proof"
        events = get_fact_events(conn, fact.id)
        assert [e["kind"] for e in events] == ["created", "verified", "verified"]


class TestUnverifyFact:
    def test_clears_denormalized_fields(self, conn: sqlite3.Connection) -> None:
        """Unverifying clears verified_at/verified_by/proof and records the given note."""
        fact = insert_fact(conn, claim="claim", actor=ACTOR, proof="proof")
        unverified = unverify_fact(conn, fact.id, ACTOR, note="proof link is dead")
        assert unverified.status == "unverified"
        assert unverified.verified_at is None
        assert unverified.verified_by is None
        assert unverified.proof is None

        events = get_fact_events(conn, fact.id)
        assert events[-1]["kind"] == "unverified"
        assert events[-1]["note"] == "proof link is dead"


class TestRetractFact:
    def test_sets_status_retracted_and_clears_denormalized_fields(
        self, conn: sqlite3.Connection
    ) -> None:
        """Retracting sets status=retracted, clears the proof fields, and records the reason."""
        fact = insert_fact(conn, claim="claim", actor=ACTOR, proof="proof")
        retracted = retract_fact(conn, fact.id, ACTOR, reason="added by mistake")
        assert retracted.status == "retracted"
        assert retracted.verified_at is None
        assert retracted.proof is None

        events = get_fact_events(conn, fact.id)
        assert events[-1]["kind"] == "retracted"
        assert events[-1]["note"] == "added by mistake"

    def test_retracted_fact_can_be_verified_again(self, conn: sqlite3.Connection) -> None:
        """Retract is not a dead end: verify still works on a retracted fact."""
        fact = insert_fact(conn, claim="claim", actor=ACTOR)
        retract_fact(conn, fact.id, ACTOR)
        verified = verify_fact(conn, fact.id, "proof", ACTOR)
        assert verified.status == "verified"


class TestDeleteFact:
    def test_rejects_a_fact_that_is_not_retracted(self, conn: sqlite3.Connection) -> None:
        """delete_fact refuses an unverified or verified fact; retract must come first."""
        fact = insert_fact(conn, claim="claim", actor=ACTOR)
        with pytest.raises(GuardViolationError) as excinfo:
            delete_fact(conn, fact.id)
        assert excinfo.value.code == "fact_not_retracted"
        assert excinfo.value.exit_code == 5

    def test_removes_the_fact_and_its_events(self, conn: sqlite3.Connection) -> None:
        """Deleting a retracted fact removes both the facts row and its fact_events rows."""
        fact = insert_fact(conn, claim="claim", actor=ACTOR)
        retract_fact(conn, fact.id, ACTOR)
        deleted = delete_fact(conn, fact.id)
        assert deleted.id == fact.id
        assert deleted.status == "retracted"
        assert get_fact(conn, fact.id) is None
        assert get_fact_events(conn, fact.id) == []
