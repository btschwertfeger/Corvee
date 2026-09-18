#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from corvee.constants import (
    FACT_LIST_FIELDS,
    FACT_LIST_TABLE_DEFAULT_FIELDS,
    FACT_STATUSES,
    LABEL_PATTERN,
    LIST_FIELDS,
    LIST_TABLE_DEFAULT_FIELDS,
    OPEN_STATES,
    PRIORITIES,
    RELATIONS,
    STATES,
    TASK_TYPES,
    TRANSITIONS,
)


class TestValueSets:
    def test_states_cover_all_documented_values(self) -> None:
        """STATES matches the exact set/order the spec documents for task state."""
        assert STATES == ("open", "in_progress", "blocked", "review", "done", "cancelled")

    def test_priorities_cover_all_documented_values(self) -> None:
        """PRIORITIES matches the exact set/order the spec documents for priority."""
        assert PRIORITIES == ("low", "medium", "high", "critical")

    def test_task_types_cover_all_documented_values(self) -> None:
        """TASK_TYPES matches the exact set the spec documents for task type."""
        assert TASK_TYPES == ("task", "bug", "feature", "epic", "chore", "spike")

    def test_relations_cover_all_documented_values(self) -> None:
        """RELATIONS matches the exact set the spec documents for task links."""
        assert RELATIONS == ("blocks", "relates_to", "duplicates", "parent_of")

    def test_fact_statuses_cover_all_documented_values(self) -> None:
        """FACT_STATUSES matches the exact set the spec documents for fact status."""
        assert FACT_STATUSES == ("unverified", "verified", "retracted")

    def test_open_states_excludes_done_and_cancelled(self) -> None:
        """OPEN_STATES excludes exactly the two terminal states, matching the "open" filter rule."""
        assert frozenset(STATES) - {"done", "cancelled"} == OPEN_STATES
        assert "done" not in OPEN_STATES
        assert "cancelled" not in OPEN_STATES

    def test_list_fields_is_the_documented_flat_column_allowlist(self) -> None:
        """LIST_FIELDS matches the exact --fields allow-list the spec documents for tasks."""
        assert LIST_FIELDS == (
            "id",
            "title",
            "description",
            "type",
            "priority",
            "state",
            "claimed_by",
            "claimed_at",
            "assigned_to",
            "created_at",
            "updated_at",
            "scope",
        )

    def test_fact_list_fields_is_the_documented_flat_column_allowlist(self) -> None:
        """FACT_LIST_FIELDS matches the exact --fields allow-list the spec documents for facts."""
        assert FACT_LIST_FIELDS == (
            "id",
            "claim",
            "status",
            "verified_at",
            "verified_by",
            "proof",
            "created_at",
            "updated_at",
            "scope",
        )

    def test_list_table_default_fields_is_list_fields_minus_description(self) -> None:
        """The table's default column set is LIST_FIELDS with the long free-text
        description column dropped, in the same order.
        """
        assert tuple(f for f in LIST_FIELDS if f != "description") == LIST_TABLE_DEFAULT_FIELDS

    def test_fact_list_table_default_fields_is_fact_list_fields_minus_proof(self) -> None:
        """The fact table's default column set is FACT_LIST_FIELDS with the long
        free-text proof column dropped, in the same order.
        """
        assert tuple(f for f in FACT_LIST_FIELDS if f != "proof") == FACT_LIST_TABLE_DEFAULT_FIELDS


class TestTransitions:
    def test_matches_documented_table(self) -> None:
        """TRANSITIONS matches the exact state machine the spec's transition table documents."""
        assert {
            "open": frozenset({"in_progress", "blocked", "done", "cancelled"}),
            "in_progress": frozenset({"open", "blocked", "review", "done", "cancelled"}),
            "blocked": frozenset({"open", "in_progress", "cancelled"}),
            "review": frozenset({"in_progress", "blocked", "done", "cancelled"}),
            "done": frozenset({"open", "in_progress"}),
            "cancelled": frozenset({"open"}),
        } == TRANSITIONS

    def test_has_an_entry_for_every_state(self) -> None:
        """Every state has a (possibly empty) transitions entry, so a lookup never KeyErrors."""
        assert set(TRANSITIONS.keys()) == set(STATES)


class TestLabelPattern:
    def test_accepts_documented_examples(self) -> None:
        """LABEL_PATTERN accepts the lowercase/dotted/slashed forms the spec allows."""
        assert LABEL_PATTERN.fullmatch("api")
        assert LABEL_PATTERN.fullmatch("api-urgent")
        assert LABEL_PATTERN.fullmatch("a.b_c/d-9")
        assert LABEL_PATTERN.fullmatch("a" * 50)

    def test_rejects_invalid_examples(self) -> None:
        """LABEL_PATTERN rejects empty, leading-punct, spaced, uppercase, or too-long names."""
        assert LABEL_PATTERN.fullmatch("") is None
        assert LABEL_PATTERN.fullmatch("-leading") is None
        assert LABEL_PATTERN.fullmatch("has space") is None
        assert LABEL_PATTERN.fullmatch("UPPER") is None
        assert LABEL_PATTERN.fullmatch("a" * 51) is None
