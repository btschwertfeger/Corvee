#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from collections.abc import Callable
from pathlib import Path

import pytest

from corvee.cli.scope import (
    fetch_merged,
    paginate_after,
    resolve_cursor,
    scopes_for,
    sort_facts,
    sort_tasks,
)
from corvee.config import ProjectConfig
from corvee.constants import Priority, ScopeFilter
from corvee.errors import NotFoundError
from corvee.models import FactRow, TaskRow


class TestScopesFor:
    @pytest.mark.parametrize(
        ("scope_filter", "expected"),
        [
            pytest.param("local", ("local",), id="local-never-touches-global"),
            pytest.param("global", (), id="global-empty-when-db-missing"),
            pytest.param("all", ("local",), id="all-skips-global-when-db-missing"),
        ],
    )
    def test_scopes_for_a_project_with_no_global_db(
        self, project: ProjectConfig, scope_filter: ScopeFilter, expected: tuple[str, ...]
    ) -> None:
        """On a project that has never used --global, --scope local/all resolve to
        just the local database and --scope global resolves to no scopes at all.
        """
        assert scopes_for(scope_filter) == expected

    def test_all_includes_global_once_the_file_exists(
        self, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """Once ~/.corvee/corvee.db exists, --scope all merges both (§3.3)."""
        global_dir = tmp_path / "home" / ".corvee"
        global_dir.mkdir(parents=True)
        (global_dir / "corvee.db").touch()
        assert scopes_for("all") == ("local", "global")
        assert scopes_for("global") == ("global",)

    def test_local_dropped_from_all_with_no_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Outside any project, --scope all silently drops local instead of raising (GH#23)."""
        monkeypatch.chdir(tmp_path)
        assert scopes_for("all") == ()

    def test_all_includes_global_with_no_local_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Outside any project, --scope all still reports the global side if it exists."""
        monkeypatch.chdir(tmp_path)
        global_dir = tmp_path / "home" / ".corvee"
        global_dir.mkdir(parents=True)
        (global_dir / "corvee.db").touch()
        assert scopes_for("all") == ("global",)

    def test_explicit_local_is_unaffected_by_a_missing_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--scope local, requested explicitly, still resolves to ("local",) — the caller
        that actually opens it is what raises the loud, expected ConfigError.
        """
        monkeypatch.chdir(tmp_path)
        assert scopes_for("local") == ("local",)

    def test_local_available_true_overrides_a_missing_ambient_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit `local_available=True` (the MCP surface's own
        already-resolved project, spec §10.1) wins over cwd having no
        project at all — the override is used verbatim, never re-derived.
        """
        monkeypatch.chdir(tmp_path)
        assert scopes_for("all", local_available=True) == ("local",)

    def test_local_available_false_overrides_a_real_ambient_project(
        self, project: ProjectConfig
    ) -> None:
        """The reverse: an explicit `local_available=False` drops local out
        of the merge even though the ambient cwd does have a real project.
        """
        assert scopes_for("all", local_available=False) == ()


class TestFetchMerged:
    def test_never_opens_a_connection_for_a_scope_it_does_not_select(
        self, project: ProjectConfig
    ) -> None:
        """A project with no global database gets an empty merge, not an error."""
        assert fetch_merged("all", lambda conn, scope: []) == []

    def test_concatenates_results_across_queried_scopes(
        self, project: ProjectConfig, tmp_path: Path
    ) -> None:
        """Each queried scope's fetch results are concatenated in scope order."""
        global_dir = tmp_path / "home" / ".corvee"
        global_dir.mkdir(parents=True)
        (global_dir / "corvee.db").touch()

        results = fetch_merged("all", lambda conn, scope: [scope])
        assert results == ["local", "global"]

    def test_all_yields_empty_with_no_project_and_no_global_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A purely-global merge outside any project, with nothing filed yet, is empty
        rather than an error (GH#23).
        """
        monkeypatch.chdir(tmp_path)
        assert fetch_merged("all", lambda conn, scope: [scope]) == []


class TestSortTasks:
    def _task(self, *, id: int, priority: Priority, created_at: str) -> TaskRow:
        return TaskRow(
            id=id,
            title="t",
            description="",
            type="task",
            priority=priority,
            state="open",
            claimed_by=None,
            claimed_at=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def test_sorts_by_priority_then_created_at_then_id_all_descending(self) -> None:
        """Priority desc, then created_at desc, then id desc — safe across a scope merge."""
        low = self._task(id=1, priority="low", created_at="2026-01-01T00:00:00.000Z")
        critical = self._task(id=2, priority="critical", created_at="2026-01-01T00:00:00.000Z")
        newer_medium = self._task(id=3, priority="medium", created_at="2026-01-02T00:00:00.000Z")
        older_medium = self._task(id=4, priority="medium", created_at="2026-01-01T00:00:00.000Z")

        result = sort_tasks([low, critical, newer_medium, older_medium])

        assert [t.id for t in result] == [2, 3, 4, 1]


class TestPaginateAfter:
    def _task(self, *, id: int, priority: Priority, created_at: str) -> TaskRow:
        return TaskRow(
            id=id,
            title="t",
            description="",
            type="task",
            priority=priority,
            state="open",
            claimed_by=None,
            claimed_at=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def test_drops_everything_up_to_and_including_the_cursor(self) -> None:
        """Only tasks strictly after the cursor in the fixed order survive."""
        first = self._task(id=1, priority="high", created_at="2026-01-03T00:00:00.000Z")
        second = self._task(id=2, priority="high", created_at="2026-01-02T00:00:00.000Z")
        third = self._task(id=3, priority="high", created_at="2026-01-01T00:00:00.000Z")

        result = paginate_after([first, second, third], cursor=first)

        assert [t.id for t in result] == [2, 3]

    def test_cursor_need_not_be_in_the_candidate_list(self) -> None:
        """A cursor filtered out of the candidate set (e.g. by state) still
        anchors the position correctly.
        """
        cursor = self._task(id=5, priority="medium", created_at="2026-01-02T00:00:00.000Z")
        after = self._task(id=4, priority="medium", created_at="2026-01-01T00:00:00.000Z")
        before = self._task(id=6, priority="medium", created_at="2026-01-03T00:00:00.000Z")

        result = paginate_after([before, after], cursor=cursor)

        assert [t.id for t in result] == [4]

    def test_higher_priority_rows_never_appear_after_a_lower_priority_cursor(self) -> None:
        """A critical-priority row always sorts before a medium cursor, so it
        never survives the after-filter regardless of created_at/id.
        """
        cursor = self._task(id=1, priority="medium", created_at="2026-01-01T00:00:00.000Z")
        critical = self._task(id=2, priority="critical", created_at="2020-01-01T00:00:00.000Z")

        assert paginate_after([critical], cursor=cursor) == []


class TestResolveCursor:
    def test_fetches_the_task_named_by_the_ref(
        self, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        task_id = add_task("t")
        cursor = resolve_cursor(task_id)
        assert cursor.id == 1

    def test_missing_id_raises_not_found(self, project: ProjectConfig) -> None:
        with pytest.raises(NotFoundError):
            resolve_cursor("TASK-999")


class TestSortFacts:
    def _fact(self, *, id: int, created_at: str) -> FactRow:
        return FactRow(
            id=id,
            claim="c",
            status="unverified",
            verified_at=None,
            verified_by=None,
            proof=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def test_sorts_by_created_at_then_id_descending(self) -> None:
        """Newest first, id as the final tiebreak — safe across a scope merge."""
        older = self._fact(id=1, created_at="2026-01-01T00:00:00.000Z")
        newer = self._fact(id=2, created_at="2026-01-02T00:00:00.000Z")

        result = sort_facts([older, newer])

        assert [f.id for f in result] == [2, 1]
