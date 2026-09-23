#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from typing import Any

from corvee.db.schema import CURRENT_SCHEMA_VERSION
from corvee.errors import ConfigError, UsageError
from corvee.timeutil import timestamp

_TABLES = (
    "tasks",
    "labels",
    "task_labels",
    "task_links",
    "task_events",
    "facts",
    "fact_events",
)


def export_project(conn: sqlite3.Connection) -> dict[str, Any]:
    """Dump the whole project as one JSON-serializable document."""
    data: dict[str, Any] = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "exported_at": timestamp(),
    }
    for table in _TABLES:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        data[table] = [dict(row) for row in rows]
    return data


def import_project(conn: sqlite3.Connection, data: dict[str, Any]) -> None:
    """Restore a dump into an empty project.

    Refuses a database that already holds tasks or facts, a dump whose
    schema_version is higher than this binary supports (the same reason an
    older binary refuses a newer live schema), and a dump whose
    schema_version is lower: rows from an older schema can carry values no
    longer valid under the current one (e.g. the pre-v2 task state
    `'todo'`, renamed to `'open'`) and are inserted verbatim with no
    migration applied, which would otherwise surface later as a bare,
    uncaught error the first time something tried to act on that row.
    """
    if "schema_version" not in data:
        raise UsageError(
            "missing_schema_version",
            "dump is missing the required schema_version key; is this a corvee dump?",
        )
    schema_version = data["schema_version"]
    if schema_version > CURRENT_SCHEMA_VERSION:
        raise ConfigError(
            "schema_too_new",
            f"dump schema version {schema_version} is newer than this binary supports "
            f"(version {CURRENT_SCHEMA_VERSION}); upgrade corvee",
            dump_schema_version=schema_version,
            binary_schema_version=CURRENT_SCHEMA_VERSION,
        )
    if schema_version < CURRENT_SCHEMA_VERSION:
        raise ConfigError(
            "schema_too_old",
            f"dump schema version {schema_version} is older than this binary's schema "
            f"(version {CURRENT_SCHEMA_VERSION}); importing a dump from an older schema "
            "version is not supported",
            dump_schema_version=schema_version,
            binary_schema_version=CURRENT_SCHEMA_VERSION,
        )

    existing_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    existing_facts = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    existing_labels = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
    if existing_tasks > 0 or existing_facts > 0 or existing_labels > 0:
        raise UsageError(
            "import_into_nonempty_project",
            "cannot import into a project that already holds tasks, facts, or labels;"
            " restore into a freshly initialized project",
        )

    for table in _TABLES:
        valid_columns = {info[1] for info in conn.execute(f"PRAGMA table_info({table})")}
        for row in data.get(table, []):
            unknown = sorted(set(row) - valid_columns)
            if unknown:
                raise UsageError(
                    "invalid_dump_column",
                    f"{table} row in the dump has unknown column(s): {', '.join(unknown)}",
                    table=table,
                    columns=unknown,
                )
            columns = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                list(row.values()),
            )
