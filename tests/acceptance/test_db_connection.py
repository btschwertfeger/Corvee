#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from pathlib import Path

import pytest

from corvee.db.connection import _set_wal_mode_with_retry, open_connection
from corvee.db.schema import CURRENT_SCHEMA_VERSION, MIGRATIONS
from corvee.errors import ConfigError


class _FlakyExecute:
    """Stands in for a sqlite3.Connection whose first `failures` executes raise
    "database is locked", simulating several processes racing to convert a
    brand-new database to WAL mode at once.
    """

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0
        self.last_sql: str | None = None

    def execute(self, sql: str) -> None:
        self.calls += 1
        self.last_sql = sql
        if self.calls <= self.failures:
            raise sqlite3.OperationalError("database is locked")


class TestSetWalModeWithRetry:
    def test_succeeds_after_transient_lock_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Retries through SQLITE_BUSY and succeeds once the lock clears, still issuing
        the real WAL pragma on the successful attempt, not just any statement.
        """
        monkeypatch.setattr("corvee.db.connection.time.sleep", lambda _seconds: None)
        conn = _FlakyExecute(failures=2)
        _set_wal_mode_with_retry(conn)  # ty: ignore[invalid-argument-type]
        assert conn.calls == 3
        assert conn.last_sql == "PRAGMA journal_mode = WAL"

    def test_reraises_once_attempts_are_exhausted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A lock that never clears within `attempts` tries propagates, not swallowed."""
        monkeypatch.setattr("corvee.db.connection.time.sleep", lambda _seconds: None)
        conn = _FlakyExecute(failures=10)
        with pytest.raises(sqlite3.OperationalError):
            _set_wal_mode_with_retry(conn, attempts=3)  # ty: ignore[invalid-argument-type]
        assert conn.calls == 3


class TestOpenConnection:
    def test_opening_a_fresh_db_bootstraps_the_schema(self, tmp_path: Path) -> None:
        """Opening a nonexistent db file creates and migrates it to the current schema version."""
        conn = open_connection(tmp_path / "corvee.db")
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert tables >= {
            "schema_migrations",
            "tasks",
            "labels",
            "task_labels",
            "task_links",
            "task_events",
        }
        version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION
        conn.close()

    def test_sets_wal_busy_timeout_and_foreign_keys(self, tmp_path: Path) -> None:
        """Every connection is opened in WAL mode with busy_timeout and foreign_keys enabled."""
        conn = open_connection(tmp_path / "corvee.db")
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        conn.close()

    def test_reopening_an_already_migrated_db_is_a_no_op(self, tmp_path: Path) -> None:
        """Opening an already-migrated database does not re-apply any migration."""
        db_path = tmp_path / "corvee.db"
        open_connection(db_path).close()
        conn = open_connection(db_path)
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count == len(MIGRATIONS)
        conn.close()

    def test_foreign_keys_are_enforced(self, tmp_path: Path) -> None:
        """A REFERENCES violation raises IntegrityError, confirming foreign_keys is really on."""
        conn = open_connection(tmp_path / "corvee.db")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO task_labels (task_id, label_id) VALUES (999, 999)",
            )
        conn.close()

    def test_migration_2_renames_todo_rows_to_open(self, tmp_path: Path) -> None:
        """A database left at schema v1 with a task still in the old 'todo' state
        gets that row renamed to 'open' when opened by a binary that ships v2 --
        a bare code rename would otherwise orphan it.
        """
        db_path = tmp_path / "corvee.db"
        conn = sqlite3.connect(db_path)
        version_1_statements = next(
            statements for version, statements in MIGRATIONS if version == 1
        )
        for statement in version_1_statements:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) "
            "VALUES (1, '2026-01-01T00:00:00.000Z')"
        )
        conn.execute(
            "INSERT INTO tasks (title, description, state, created_at, updated_at) "
            "VALUES ('legacy task', '', 'todo', '2026-01-01T00:00:00.000Z', "
            "'2026-01-01T00:00:00.000Z')"
        )
        conn.commit()
        conn.close()

        conn = open_connection(db_path)
        state = conn.execute("SELECT state FROM tasks WHERE title = 'legacy task'").fetchone()[0]
        assert state == "open"
        conn.close()

    def test_a_db_with_a_newer_schema_version_refuses(self, tmp_path: Path) -> None:
        """A database migrated by a newer binary refuses to open, naming both schema versions."""
        db_path = tmp_path / "corvee.db"
        open_connection(db_path).close()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (CURRENT_SCHEMA_VERSION + 1, "2026-01-01T00:00:00.000Z"),
        )
        conn.commit()
        conn.close()

        with pytest.raises(ConfigError) as excinfo:
            open_connection(db_path)
        assert excinfo.value.exit_code == 6
        assert excinfo.value.extra["db_schema_version"] == CURRENT_SCHEMA_VERSION + 1
        assert excinfo.value.extra["binary_schema_version"] == CURRENT_SCHEMA_VERSION

    def test_a_failing_migration_rolls_back_instead_of_partially_applying(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broken migration statement rolls back the whole batch, including
        every earlier migration applied in the same transaction, instead of
        leaving the database half-migrated.
        """
        db_path = tmp_path / "corvee.db"
        broken_migrations = [*MIGRATIONS, (CURRENT_SCHEMA_VERSION + 1, ["NOT VALID SQL"])]
        monkeypatch.setattr("corvee.db.connection.MIGRATIONS", broken_migrations)

        with pytest.raises(sqlite3.OperationalError):
            open_connection(db_path)

        conn = sqlite3.connect(db_path)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert tables == set()
        conn.close()

    def test_a_failing_migration_closes_the_connection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broken migration statement closes the connection it opened instead
        of leaking it, matching what the schema_too_new path already does.
        """
        db_path = tmp_path / "corvee.db"
        broken_migrations = [*MIGRATIONS, (CURRENT_SCHEMA_VERSION + 1, ["NOT VALID SQL"])]
        monkeypatch.setattr("corvee.db.connection.MIGRATIONS", broken_migrations)

        real_connect = sqlite3.connect
        opened: list[sqlite3.Connection] = []
        monkeypatch.setattr(
            "corvee.db.connection.sqlite3.connect",
            lambda *args, **kwargs: opened.append(real_connect(*args, **kwargs)) or opened[-1],
        )

        with pytest.raises(sqlite3.OperationalError):
            open_connection(db_path)

        assert len(opened) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            opened[0].execute("SELECT 1")
