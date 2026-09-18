#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import pytest

from corvee.constants import Scope
from corvee.errors import GuardViolationError, UsageError
from corvee.guards.ancestry import creates_cycle, is_reachable
from corvee.guards.fields import validate_fields
from corvee.guards.labels import normalize_label
from corvee.guards.parent_child import assert_no_open_children
from corvee.guards.scope import assert_same_scope
from corvee.guards.transitions import validate_transition


class TestValidateTransition:
    def test_same_state_transition_is_a_no_op(self) -> None:
        """Setting a task to the state it already holds never raises."""
        validate_transition("open", "open")  # must not raise

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("open", "in_progress"),
            ("in_progress", "review"),
            ("blocked", "cancelled"),
            ("review", "done"),
            ("done", "open"),
            ("cancelled", "open"),
        ],
    )
    def test_permitted_transitions_do_not_raise(self, current: str, target: str) -> None:
        """Every edge in the documented transition table is accepted without raising."""
        validate_transition(current, target)  # ty: ignore[invalid-argument-type]

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("blocked", "done"),
            ("blocked", "review"),
            ("done", "cancelled"),
            ("cancelled", "in_progress"),
            ("cancelled", "done"),
        ],
    )
    def test_rejected_transitions_raise_guard_violation(self, current: str, target: str) -> None:
        """A transition absent from the table exits 5 and names both states plus the allowed set."""
        with pytest.raises(GuardViolationError) as excinfo:
            validate_transition(current, target)  # ty: ignore[invalid-argument-type]
        assert excinfo.value.exit_code == 5
        assert excinfo.value.extra["current_state"] == current
        assert excinfo.value.extra["target_state"] == target
        assert "allowed_states" in excinfo.value.extra


class TestIsReachable:
    def test_finds_direct_edge(self) -> None:
        """A single-edge path from start to target is reachable."""
        adjacency = {1: [2], 2: []}
        assert is_reachable(adjacency.get, 1, 2) is True

    def test_finds_transitive_edge(self) -> None:
        """A multi-hop path from start to target is still found."""
        adjacency = {1: [2], 2: [3], 3: []}
        assert is_reachable(adjacency.get, 1, 3) is True

    def test_false_when_no_path(self) -> None:
        """Two disconnected nodes are correctly reported as unreachable."""
        adjacency = {1: [2], 2: [], 3: []}
        assert is_reachable(adjacency.get, 1, 3) is False

    def test_terminates_on_existing_cycle(self) -> None:
        """A cycle already present in the graph terminates the walk instead of hanging it."""
        adjacency = {1: [2], 2: [1]}
        assert is_reachable(adjacency.get, 1, 3) is False


class TestCreatesCycle:
    @pytest.mark.parametrize(
        ("adjacency", "new_source", "new_target", "expected"),
        [
            # A parent_of B, B parent_of C already exist (source parent_of
            # target). Attempting `corvee link C A --relation parent_of` ->
            # new edge 3 -> 1 closes the A-B-C chain into a cycle.
            pytest.param({1: [2], 2: [3], 3: []}, 3, 1, True, id="parent_of-chain-cycle"),
            # B blocks A already exists; attempting "A blocks B" -> new edge
            # 1 -> 2 closes a two-node cycle.
            pytest.param({2: [1], 1: []}, 1, 2, True, id="two-node-blocks-cycle"),
            # No existing path between the nodes, so the new edge is not a cycle.
            pytest.param({1: [2], 3: []}, 3, 1, False, id="independent-edge"),
        ],
    )
    def test_creates_cycle(
        self,
        adjacency: dict[int, list[int]],
        new_source: int,
        new_target: int,
        expected: bool,
    ) -> None:
        """creates_cycle flags a new edge that would close a path back to its own
        source, and only that case.
        """
        result = creates_cycle(adjacency.get, new_source=new_source, new_target=new_target)
        assert result is expected


class TestValidateFields:
    def test_accepts_documented_columns(self) -> None:
        """Requesting only documented task columns returns them as a tuple, in order."""
        assert validate_fields(["id", "title"]) == ("id", "title")

    def test_rejects_unknown_field(self) -> None:
        """An unknown field name exits 2 and names both the bad field and the valid list."""
        with pytest.raises(UsageError) as excinfo:
            validate_fields(["id", "bogus"])
        assert excinfo.value.exit_code == 2
        assert excinfo.value.extra["field"] == "bogus"
        assert "valid_fields" in excinfo.value.extra

    def test_accepts_a_custom_allowlist(self) -> None:
        """Passing `allowed=` (e.g. the fact column set) validates against that list instead."""
        assert validate_fields(["id", "claim"], allowed=("id", "claim", "status")) == (
            "id",
            "claim",
        )

    def test_rejects_field_not_in_custom_allowlist(self) -> None:
        """A field valid for tasks but absent from a custom allow-list is still rejected."""
        with pytest.raises(UsageError) as excinfo:
            validate_fields(["title"], allowed=("id", "claim", "status"))
        assert excinfo.value.extra["valid_fields"] == ["id", "claim", "status"]


class TestNormalizeLabel:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("API", "api"),
            ("  urgent  ", "urgent"),
            ("Api-Urgent", "api-urgent"),
        ],
    )
    def test_lowercases_and_trims(self, raw: str, expected: str) -> None:
        """Mixed-case and surrounding-whitespace label input normalizes to lowercase/trimmed."""
        assert normalize_label(raw) == expected

    @pytest.mark.parametrize("raw", ["", "-leading", "has space", "a" * 51])
    def test_rejects_invalid_names(self, raw: str) -> None:
        """A label that fails LABEL_PATTERN after normalization exits 2."""
        with pytest.raises(UsageError) as excinfo:
            normalize_label(raw)
        assert excinfo.value.exit_code == 2


class TestAssertNoOpenChildren:
    def test_passes_when_all_terminal(self) -> None:
        """Children that are all done/cancelled never raise."""
        assert_no_open_children([(2, "done"), (3, "cancelled")])  # must not raise

    def test_raises_and_lists_blocking_ids(self) -> None:
        """Any non-terminal child raises and lists exactly the blocking child ids, in order."""
        with pytest.raises(GuardViolationError) as excinfo:
            assert_no_open_children([(2, "done"), (3, "in_progress"), (4, "open")])
        assert excinfo.value.exit_code == 5
        assert excinfo.value.extra["blocking_ids"] == ["TASK-3", "TASK-4"]

    def test_formats_blocking_ids_for_global_scope(self) -> None:
        """blocking_ids uses the TASK-GLOBAL-<n> ref form when scope is global."""
        with pytest.raises(GuardViolationError) as excinfo:
            assert_no_open_children([(3, "open")], scope="global")
        assert excinfo.value.extra["blocking_ids"] == ["TASK-GLOBAL-3"]


class TestAssertSameScope:
    @pytest.mark.parametrize("scope", ["local", "global"])
    def test_passes_when_scopes_match(self, scope: Scope) -> None:
        """Two refs sharing one scope never raise (§3.3)."""
        assert_same_scope(scope, scope)  # must not raise

    def test_raises_on_a_local_global_mismatch(self) -> None:
        """Linking across the local/global split is a guard violation (§3.3)."""
        with pytest.raises(GuardViolationError) as excinfo:
            assert_same_scope("local", "global")
        assert excinfo.value.exit_code == 5
        assert excinfo.value.code == "cross_scope_link"
