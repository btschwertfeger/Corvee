#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import pytest

from corvee.errors import UsageError
from corvee.models import (
    FactRow,
    TaskRow,
    fact_ref,
    parse_fact_ref,
    parse_fact_refs,
    parse_task_ref,
    parse_task_refs,
    task_ref,
)


class TestTaskRef:
    def test_formats_task_prefix(self) -> None:
        """task_ref renders an integer id as the external TASK-<n> string form."""
        assert task_ref(14) == "TASK-14"

    def test_formats_global_task_prefix(self) -> None:
        """task_ref renders a global-scoped id as TASK-GLOBAL-<n> (§3.3)."""
        assert task_ref(14, "global") == "TASK-GLOBAL-14"


class TestParseTaskRef:
    @pytest.mark.parametrize(("value", "expected"), [("TASK-14", 14), ("14", 14), ("task-14", 14)])
    def test_accepts_both_forms(self, value: str, expected: int) -> None:
        """A prefixed, bare, or lowercase-prefixed id string all normalize to the same integer,
        scoped local."""
        parsed = parse_task_ref(value)
        assert parsed.id == expected
        assert parsed.scope == "local"

    @pytest.mark.parametrize("value", ["TASK-GLOBAL-14", "task-global-14"])
    def test_accepts_the_global_form(self, value: str) -> None:
        """TASK-GLOBAL-<n> normalizes to the integer id, scoped global (§3.3)."""
        parsed = parse_task_ref(value)
        assert parsed.id == 14
        assert parsed.scope == "global"

    @pytest.mark.parametrize("value", ["", "TASK-", "abc", "TASK-abc", "-1", "TASK-GLOBAL-"])
    def test_rejects_invalid_input(self, value: str) -> None:
        """Malformed task id input exits 2 rather than raising an unhandled error."""
        with pytest.raises(UsageError) as excinfo:
            parse_task_ref(value)
        assert excinfo.value.exit_code == 2

    @pytest.mark.parametrize("value", ["²", "TASK-²", "١٤", "TASK-١٤", "TASK-GLOBAL-١٤"])
    def test_rejects_non_ascii_digits(self, value: str) -> None:
        """Only ASCII 0-9 form an id; a superscript or Arabic-Indic digit exits 2."""
        with pytest.raises(UsageError) as excinfo:
            parse_task_ref(value)
        assert excinfo.value.exit_code == 2
        assert excinfo.value.code == "invalid_task_id"

    @pytest.mark.parametrize(
        "value", ["9" * 23, "9" * 5000, f"TASK-{'9' * 23}", f"TASK-GLOBAL-{'9' * 5000}"]
    )
    def test_rejects_ids_above_the_sqlite_integer_range(self, value: str) -> None:
        """An id SQLite cannot store exits 2 instead of failing inside the driver."""
        with pytest.raises(UsageError) as excinfo:
            parse_task_ref(value)
        assert excinfo.value.exit_code == 2
        assert excinfo.value.code == "invalid_task_id"

    def test_accepts_the_largest_storable_id(self) -> None:
        """2**63-1 is the largest id SQLite stores, so it still parses."""
        assert parse_task_ref(str(2**63 - 1)).id == 2**63 - 1

    def test_rejects_a_fact_id_pointing_at_fact_show(self) -> None:
        """A FACT-<n> value given to the task id parser is rejected, not silently misread."""
        with pytest.raises(UsageError) as excinfo:
            parse_task_ref("FACT-7")
        assert excinfo.value.exit_code == 2
        assert excinfo.value.code == "wrong_id_namespace"
        assert "corvee fact show" in excinfo.value.message

    def test_rejects_a_global_fact_id(self) -> None:
        """FACT-GLOBAL-<n> is still a fact id, rejected the same as FACT-<n>."""
        with pytest.raises(UsageError) as excinfo:
            parse_task_ref("FACT-GLOBAL-7")
        assert excinfo.value.code == "wrong_id_namespace"


class TestParseTaskRefs:
    def test_returns_ids_and_the_shared_scope(self) -> None:
        """Multiple local refs return their ids and the one scope they share."""
        ids, scope = parse_task_refs(["TASK-1", "2", "TASK-3"])
        assert ids == [1, 2, 3]
        assert scope == "local"

    def test_rejects_mixed_scope(self) -> None:
        """Mixing a local and a global id in one call is a usage error (§3.3)."""
        with pytest.raises(UsageError) as excinfo:
            parse_task_refs(["TASK-1", "TASK-GLOBAL-2"])
        assert excinfo.value.exit_code == 2
        assert excinfo.value.code == "mixed_scope"

    def test_deduplicates_repeated_ids_preserving_order(self) -> None:
        """A repeated id collapses to one entry, in first-seen order -- a caller
        listing the same id twice almost certainly means "operate on it once,"
        not "give me it back twice."
        """
        ids, scope = parse_task_refs(["TASK-3", "TASK-1", "TASK-3", "1"])
        assert ids == [3, 1]
        assert scope == "local"


class TestFactRef:
    def test_formats_fact_prefix(self) -> None:
        """fact_ref renders an integer id as the external FACT-<n> string form."""
        assert fact_ref(7) == "FACT-7"

    def test_formats_global_fact_prefix(self) -> None:
        """fact_ref renders a global-scoped id as FACT-GLOBAL-<n> (§3.3)."""
        assert fact_ref(7, "global") == "FACT-GLOBAL-7"


class TestParseFactRef:
    @pytest.mark.parametrize(("value", "expected"), [("FACT-7", 7), ("7", 7), ("fact-7", 7)])
    def test_accepts_both_forms(self, value: str, expected: int) -> None:
        """A prefixed, bare, or lowercase-prefixed id string all normalize to the same integer,
        scoped local."""
        parsed = parse_fact_ref(value)
        assert parsed.id == expected
        assert parsed.scope == "local"

    @pytest.mark.parametrize("value", ["FACT-GLOBAL-7", "fact-global-7"])
    def test_accepts_the_global_form(self, value: str) -> None:
        """FACT-GLOBAL-<n> normalizes to the integer id, scoped global (§3.3)."""
        parsed = parse_fact_ref(value)
        assert parsed.id == 7
        assert parsed.scope == "global"

    @pytest.mark.parametrize("value", ["", "FACT-", "abc", "FACT-abc", "-1", "FACT-GLOBAL-"])
    def test_rejects_invalid_input(self, value: str) -> None:
        """Malformed fact id input exits 2 rather than raising an unhandled error."""
        with pytest.raises(UsageError) as excinfo:
            parse_fact_ref(value)
        assert excinfo.value.exit_code == 2

    @pytest.mark.parametrize("value", ["²", "FACT-²", "١٤", "FACT-١٤", "FACT-GLOBAL-١٤"])
    def test_rejects_non_ascii_digits(self, value: str) -> None:
        """Only ASCII 0-9 form an id; a superscript or Arabic-Indic digit exits 2."""
        with pytest.raises(UsageError) as excinfo:
            parse_fact_ref(value)
        assert excinfo.value.exit_code == 2
        assert excinfo.value.code == "invalid_fact_id"

    @pytest.mark.parametrize(
        "value", ["9" * 23, "9" * 5000, f"FACT-{'9' * 23}", f"FACT-GLOBAL-{'9' * 5000}"]
    )
    def test_rejects_ids_above_the_sqlite_integer_range(self, value: str) -> None:
        """An id SQLite cannot store exits 2 instead of failing inside the driver."""
        with pytest.raises(UsageError) as excinfo:
            parse_fact_ref(value)
        assert excinfo.value.exit_code == 2
        assert excinfo.value.code == "invalid_fact_id"

    def test_rejects_a_task_id_pointing_at_task_show(self) -> None:
        """A TASK-<n> value given to the fact id parser is rejected, not silently misread."""
        with pytest.raises(UsageError) as excinfo:
            parse_fact_ref("TASK-14")
        assert excinfo.value.exit_code == 2
        assert excinfo.value.code == "wrong_id_namespace"
        assert "corvee task show" in excinfo.value.message

    def test_rejects_a_global_task_id(self) -> None:
        """TASK-GLOBAL-<n> is still a task id, rejected the same as TASK-<n>."""
        with pytest.raises(UsageError) as excinfo:
            parse_fact_ref("TASK-GLOBAL-14")
        assert excinfo.value.code == "wrong_id_namespace"


class TestParseFactRefs:
    def test_returns_ids_and_the_shared_scope(self) -> None:
        """Multiple global refs return their ids and the one scope they share."""
        ids, scope = parse_fact_refs(["FACT-GLOBAL-1", "FACT-GLOBAL-2"])
        assert ids == [1, 2]
        assert scope == "global"

    def test_rejects_mixed_scope(self) -> None:
        """Mixing a local and a global id in one call is a usage error (§3.3)."""
        with pytest.raises(UsageError) as excinfo:
            parse_fact_refs(["FACT-1", "FACT-GLOBAL-2"])
        assert excinfo.value.exit_code == 2
        assert excinfo.value.code == "mixed_scope"


class TestTaskRow:
    def test_to_dict_uses_task_ref_id(self) -> None:
        """to_dict's "id" is the TASK-<n> string, and the shape is exactly the documented fields."""
        row = TaskRow(
            id=14,
            title="t",
            description="",
            type="task",
            priority="medium",
            state="open",
            claimed_by=None,
            claimed_at=None,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )
        d = row.to_dict()
        assert d["id"] == "TASK-14"
        assert d["title"] == "t"
        assert d["scope"] == "local"
        assert set(d.keys()) == {
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
        }

    def test_to_dict_uses_the_global_task_ref_id_when_scoped_global(self) -> None:
        """A global-scoped row renders id as TASK-GLOBAL-<n> and scope as "global" (§3.3)."""
        row = TaskRow(
            id=14,
            title="t",
            description="",
            type="task",
            priority="medium",
            state="open",
            claimed_by=None,
            claimed_at=None,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
            scope="global",
        )
        d = row.to_dict()
        assert d["id"] == "TASK-GLOBAL-14"
        assert d["scope"] == "global"


class TestFactRow:
    def test_to_dict_uses_fact_ref_id(self) -> None:
        """to_dict's "id" is the FACT-<n> string, and the shape is exactly the documented fields."""
        row = FactRow(
            id=7,
            claim="package X is MIT-licensed",
            status="unverified",
            verified_at=None,
            verified_by=None,
            proof=None,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
        )
        d = row.to_dict()
        assert d["id"] == "FACT-7"
        assert d["claim"] == "package X is MIT-licensed"
        assert d["scope"] == "local"
        assert set(d.keys()) == {
            "id",
            "claim",
            "status",
            "verified_at",
            "verified_by",
            "proof",
            "created_at",
            "updated_at",
            "scope",
        }

    def test_to_dict_uses_the_global_fact_ref_id_when_scoped_global(self) -> None:
        """A global-scoped row renders id as FACT-GLOBAL-<n> and scope as "global" (§3.3)."""
        row = FactRow(
            id=7,
            claim="c",
            status="unverified",
            verified_at=None,
            verified_by=None,
            proof=None,
            created_at="2026-01-01T00:00:00.000Z",
            updated_at="2026-01-01T00:00:00.000Z",
            scope="global",
        )
        d = row.to_dict()
        assert d["id"] == "FACT-GLOBAL-7"
        assert d["scope"] == "global"
