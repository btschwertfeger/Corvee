#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from corvee.config import bootstrap_project
from corvee.db.connection import open_connection
from corvee.db.export_import import export_project, import_project
from corvee.db.facts import insert_fact, retract_fact, revise_fact
from corvee.db.labels import add_label
from corvee.db.links import link_tasks
from corvee.db.tasks import add_comment, insert_task
from corvee.errors import ConfigError, UsageError


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    result = bootstrap_project(tmp_path)
    connection = open_connection(result.db_path)
    yield connection
    connection.close()


def _populate(conn: sqlite3.Connection) -> None:
    parent = insert_task(conn, title="parent")
    child = insert_task(conn, title="child")
    add_label(conn, parent.id, "api", "agent:a", None)
    link_tasks(conn, parent.id, child.id, "parent_of", "agent:a", None)
    add_comment(conn, parent.id, "note", "agent:a", "s1")
    fact = insert_fact(conn, claim="package X is MIT-licensed", actor="agent:a")
    revise_fact(conn, fact.id, "package X is Apache-2.0", "agent:a")


class TestExportProject:
    def test_includes_all_tables(self, conn: sqlite3.Connection) -> None:
        """The export document includes every table's rows, tasks and facts alike, plus metadata."""
        _populate(conn)
        data = export_project(conn)
        assert len(data["tasks"]) == 2
        assert len(data["labels"]) == 1
        assert len(data["task_labels"]) == 1
        assert len(data["task_links"]) == 1
        assert len(data["task_events"]) >= 1
        assert len(data["facts"]) == 1
        assert len(data["fact_events"]) == 2
        assert "schema_version" in data
        assert "exported_at" in data


class TestImportProject:
    def test_refuses_nonempty_project(self, conn: sqlite3.Connection) -> None:
        """Importing into a project that already holds a task exits 2."""
        insert_task(conn, title="already here")
        data = export_project(conn)
        with pytest.raises(UsageError) as excinfo:
            import_project(conn, data)
        assert excinfo.value.exit_code == 2

    def test_refuses_project_with_only_facts(self, conn: sqlite3.Connection) -> None:
        """Importing into a project that holds a fact (but no task) still exits 2."""
        insert_fact(conn, claim="already here", actor="agent:a")
        data = export_project(conn)
        with pytest.raises(UsageError) as excinfo:
            import_project(conn, data)
        assert excinfo.value.exit_code == 2

    def test_refuses_project_with_a_retracted_fact(self, conn: sqlite3.Connection) -> None:
        """A retracted fact still counts as "holds data"; import is refused."""
        fact = insert_fact(conn, claim="already here", actor="agent:a")
        retract_fact(conn, fact.id, "agent:a")
        data = export_project(conn)
        with pytest.raises(UsageError) as excinfo:
            import_project(conn, data)
        assert excinfo.value.exit_code == 2

    def test_refuses_newer_schema_version(self, conn: sqlite3.Connection) -> None:
        """A dump whose schema_version exceeds this binary's raises ConfigError (exit 6)."""
        data = export_project(conn)
        data["schema_version"] = data["schema_version"] + 1
        with pytest.raises(ConfigError) as excinfo:
            import_project(conn, data)
        assert excinfo.value.exit_code == 6

    def test_refuses_older_schema_version(self, conn: sqlite3.Connection) -> None:
        """A dump captured at an older schema_version (e.g. one still carrying
        the pre-v2 'todo' task state, which is not a valid current State) is
        refused cleanly rather than inserted verbatim -- letting it through
        unmigrated would only surface later as a bare KeyError from
        guards/transitions.py the first time something tried to move that
        task out of its now-nonexistent state.
        """
        data = export_project(conn)
        data["schema_version"] = data["schema_version"] - 1
        with pytest.raises(ConfigError) as excinfo:
            import_project(conn, data)
        assert excinfo.value.exit_code == 6
        assert excinfo.value.code == "schema_too_old"

    def test_round_trip_preserves_ids_and_content(self, tmp_path: Path) -> None:
        """A full export/import round trip reproduces every table's content exactly."""
        source_project = bootstrap_project(tmp_path / "source")
        source_conn = open_connection(source_project.db_path)
        _populate(source_conn)
        dump = export_project(source_conn)
        source_conn.close()

        target_project = bootstrap_project(tmp_path / "target")
        target_conn = open_connection(target_project.db_path)
        import_project(target_conn, dump)
        restored = export_project(target_conn)
        target_conn.close()

        for table in (
            "tasks",
            "labels",
            "task_labels",
            "task_links",
            "task_events",
            "facts",
            "fact_events",
        ):
            assert restored[table] == dump[table]
