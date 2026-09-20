#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
import time
from pathlib import Path

from corvee.db.schema import CURRENT_SCHEMA_VERSION, MIGRATIONS
from corvee.errors import ConfigError
from corvee.timeutil import timestamp

BUSY_TIMEOUT_MS = 5000


def _set_wal_mode_with_retry(conn: sqlite3.Connection, *, attempts: int = 5) -> None:
    """Set WAL mode, retrying "database is locked" a few times.

    Converting a brand-new database file to WAL for the first time needs an
    exclusive lock; several connections racing to do that simultaneously can
    get SQLITE_BUSY on this one statement without going through the normal
    busy_timeout retry loop (busy_timeout also isn't set yet at this point).
    This only matters for that one-time conversion — every other statement
    in this module is covered by busy_timeout once it's set below.
    """
    delay = 0.01
    for attempt in range(attempts):
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


# sqlite3 error codes that mean "this file cannot be used as a corvee
# database": missing or unopenable, not a database at all, malformed, or not
# writable (SQLITE_PERM is the Windows-ACL spelling of the same condition).
# Deliberately absent: SQLITE_BUSY, which busy_timeout already retries and
# whose exhaustion is still an open question (§3.2, TASK-68), and SQLITE_IOERR,
# which covers a failing device as readily as a file that cannot be read, with
# nothing here to tell those apart.
_UNUSABLE_DB_CODES = frozenset(
    {
        sqlite3.SQLITE_CANTOPEN,
        sqlite3.SQLITE_NOTADB,
        sqlite3.SQLITE_READONLY,
        sqlite3.SQLITE_PERM,
        sqlite3.SQLITE_CORRUPT,
    },
)


def unusable_database_error(error: sqlite3.Error, db_path: Path) -> ConfigError | None:
    """`error` as the ConfigError (exit 6) saying `db_path` cannot be used, or None.

    A database file that cannot be read, written or parsed as a schema is a
    project problem (spec §5): no `corvee` command succeeds until the file or
    its permissions change. Every other sqlite3 failure keeps its own shape, so
    a lock timeout or a bug in corvee never masquerades as something the user
    can fix in a file.
    """
    # sqlite_errorcode is an *extended* code (SQLITE_READONLY_DBMOVED is 1032,
    # say); its low byte is the primary code the set above names. A hand-built
    # sqlite3.Error carries no code at all, and is left alone.
    code = getattr(error, "sqlite_errorcode", None)
    if code is None or (code & 0xFF) not in _UNUSABLE_DB_CODES:
        return None
    return ConfigError(
        "unusable_database",
        f"cannot use database {db_path}: {error}",
        path=str(db_path),
    )


def _read_schema_version(conn: sqlite3.Connection) -> int:
    """Plain read of MAX(version), taking no lock. 0 if unmigrated."""
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    except sqlite3.OperationalError:
        return 0
    version = row[0]
    return int(version) if version is not None else 0


def _apply_missing_migrations(conn: sqlite3.Connection) -> None:
    """Re-read the version under BEGIN IMMEDIATE and apply what's missing.

    Two processes racing to migrate serialize on this transaction instead of
    double-applying one.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = _read_schema_version(conn)
        for version, statements in MIGRATIONS:
            if version <= current:
                continue
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, timestamp()),
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def open_connection(db_path: Path) -> sqlite3.Connection:
    """Open `db_path`, applying pragmas and bootstrapping/migrating the schema.

    Refuses (ConfigError, exit 6) if the file cannot be used as a database at
    all, or if its schema is newer than this binary supports.
    """
    try:
        return _open_connection(db_path)
    except sqlite3.Error as error:
        # Whichever statement first touches the file is the one that reports it
        # (`connect` for a directory, the WAL pragma for a path SQLite cannot
        # create), so this wraps the whole body rather than each of them.
        unusable = unusable_database_error(error, db_path)
        if unusable is not None:
            raise unusable from error
        raise


def _open_connection(db_path: Path) -> sqlite3.Connection:
    """`open_connection`'s body, leaving raw sqlite3 failures to its caller."""
    conn = sqlite3.connect(db_path)
    conn.isolation_level = None  # manual BEGIN/COMMIT control, see _apply_missing_migrations
    conn.row_factory = sqlite3.Row
    _set_wal_mode_with_retry(conn)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")

    current = _read_schema_version(conn)
    if current > CURRENT_SCHEMA_VERSION:
        conn.close()
        raise ConfigError(
            "schema_too_new",
            f"database schema version {current} is newer than this binary supports "
            f"(version {CURRENT_SCHEMA_VERSION}); upgrade corvee",
            db_schema_version=current,
            binary_schema_version=CURRENT_SCHEMA_VERSION,
        )
    if current < CURRENT_SCHEMA_VERSION:
        try:
            _apply_missing_migrations(conn)
        except BaseException:
            conn.close()
            raise
    return conn
