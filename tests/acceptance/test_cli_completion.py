#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Callable
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from corvee.cli.completion import complete_fact_ids, complete_labels, complete_task_ids
from corvee.cli.main import cli
from corvee.config import ProjectConfig
from corvee.db.schema import CURRENT_SCHEMA_VERSION

_CTX = click.Context(click.Command("dummy"))
_PARAM = click.Argument(["dummy"])


def _bump_schema_version(db_path: Path) -> None:
    """Make the project's db look like it was migrated by a newer binary."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (CURRENT_SCHEMA_VERSION + 1, "2026-01-01T00:00:00.000Z"),
    )
    conn.commit()
    conn.close()


class TestCompleteTaskIds:
    def test_matches_ids_by_prefix(
        self, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Only ids starting with the incomplete prefix are offered."""
        add_task("first task")
        add_task("second task")
        items = complete_task_ids(_CTX, _PARAM, "TASK-1")
        assert [item.value for item in items] == ["TASK-1"]

    def test_offers_the_title_as_help_text(
        self, project: ProjectConfig, add_task: Callable[[str], str]
    ) -> None:
        """Each completion carries the task's title, so an agent can tell ids apart."""
        add_task("fix the flaky auth test")
        items = complete_task_ids(_CTX, _PARAM, "")
        assert items[0].help == "fix the flaky auth test"

    def test_includes_done_tasks(
        self,
        project: ProjectConfig,
        runner: CliRunner,
        add_task: Callable[[str], str],
    ) -> None:
        """Completion isn't limited to open tasks -- a done id is still a valid argument."""
        task_id = add_task("finished already")
        runner.invoke(cli, ["task", "update", task_id, "--state", "done"])
        items = complete_task_ids(_CTX, _PARAM, "TASK-")
        assert [item.value for item in items] == [task_id]

    def test_outside_a_project_returns_no_completions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no .corvee/config.toml findable, completion is empty rather than raising."""
        empty_dir = tmp_path / "not-a-project"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)
        assert complete_task_ids(_CTX, _PARAM, "") == []

    def test_a_database_on_a_newer_schema_returns_no_completions(
        self, project: ProjectConfig
    ) -> None:
        """A database migrated by a newer binary raises a CorveeError while merging
        scopes; completion offers nothing rather than erroring into the shell.
        """
        _bump_schema_version(project.db_path)
        assert complete_task_ids(_CTX, _PARAM, "") == []


class TestCompleteFactIds:
    def test_matches_ids_by_prefix(
        self, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """Only ids starting with the incomplete prefix are offered."""
        add_fact("first claim")
        add_fact("second claim")
        items = complete_fact_ids(_CTX, _PARAM, "FACT-1")
        assert [item.value for item in items] == ["FACT-1"]

    def test_offers_the_claim_as_help_text(
        self, project: ProjectConfig, add_fact: Callable[[str], str]
    ) -> None:
        """Each completion carries the fact's claim text, so an agent can tell ids apart."""
        add_fact("package X is MIT-licensed")
        items = complete_fact_ids(_CTX, _PARAM, "")
        assert items[0].help == "package X is MIT-licensed"

    def test_a_database_on_a_newer_schema_returns_no_completions(
        self, project: ProjectConfig
    ) -> None:
        """The fact-group equivalent of the same check on task ids."""
        _bump_schema_version(project.db_path)
        assert complete_fact_ids(_CTX, _PARAM, "") == []


class TestCompleteLabels:
    def test_matches_labels_by_prefix(
        self, project: ProjectConfig, runner: CliRunner, add_task: Callable[[str], str]
    ) -> None:
        """Only labels starting with the incomplete prefix are offered."""
        task_id = add_task("task")
        runner.invoke(cli, ["task", "label", task_id, "--add", "api", "--add", "urgent"])
        items = complete_labels(_CTX, _PARAM, "a")
        assert [item.value for item in items] == ["api"]

    def test_outside_a_project_returns_no_completions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no .corvee/config.toml findable, completion is empty rather than raising."""
        empty_dir = tmp_path / "not-a-project"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)
        assert complete_labels(_CTX, _PARAM, "") == []
