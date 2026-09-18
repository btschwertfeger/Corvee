#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from corvee.cli.main import cli
from corvee.config import ProjectConfig, bootstrap_project
from corvee.db.connection import open_connection

# Every test gets its `unit`/`acceptance`/`e2e` marker from the directory it
# lives in, rather than a per-test decorator repeated ~300 times — the
# directory *is* the classification, so `pytest -m unit` and the layout on
# disk can never disagree.
_MARKER_DIRS = ("unit", "acceptance", "e2e")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        for part in item.path.parts:
            if part in _MARKER_DIRS:
                item.add_marker(getattr(pytest.mark, part))
                break


@pytest.fixture(autouse=True)
def _fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point $HOME at an isolated directory so the global database (§3.3) never
    touches the real ~/.corvee, in-process or in an e2e subprocess (which
    inherits os.environ).
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectConfig:
    """An initialized project: config + migrated DB, cwd inside it, CORVEE_ACTOR set."""
    result = bootstrap_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CORVEE_ACTOR", "agent:test")
    monkeypatch.delenv("CORVEE_SESSION_ID", raising=False)
    return ProjectConfig(config_path=result.config_path, db_path=result.db_path)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def conn(project: ProjectConfig) -> Iterator[sqlite3.Connection]:
    """A connection to the current test project's local database, closed on teardown.

    Shared across the db-layer acceptance tests, which all open the same
    project database directly rather than going through the CLI.
    """
    connection = open_connection(project.db_path)
    yield connection
    connection.close()


@pytest.fixture
def add_task(runner: CliRunner) -> Callable[[str], str]:
    """Create a task via the CLI (`title`, a fixed placeholder description) and
    return its id -- the common setup step for acceptance tests exercising
    claim/update/label/link/ready/search/etc. rather than `task add` itself.
    """

    def _add(title: str) -> str:
        result = runner.invoke(cli, ["task", "add", title, "--description", "test task", "--json"])
        return str(json.loads(result.output)[0]["id"])

    return _add


@pytest.fixture
def add_fact(runner: CliRunner) -> Callable[[str], str]:
    """Create a fact via the CLI and return its id -- the fact-group equivalent
    of `add_task`.
    """

    def _add(claim: str) -> str:
        result = runner.invoke(cli, ["fact", "add", claim, "--json"])
        return str(json.loads(result.output)[0]["id"])

    return _add
