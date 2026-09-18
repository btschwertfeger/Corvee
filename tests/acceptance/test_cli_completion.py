#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

from collections.abc import Callable
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from corvee.cli.completion import complete_fact_ids, complete_labels, complete_task_ids
from corvee.cli.main import cli
from corvee.config import ProjectConfig

_CTX = click.Context(click.Command("dummy"))
_PARAM = click.Argument(["dummy"])


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
