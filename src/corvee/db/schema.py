#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

CURRENT_SCHEMA_VERSION = 3

# Each migration is (version, [individual DDL statements]). Kept as separate
# statements rather than one script so they can run inside one explicit
# BEGIN IMMEDIATE transaction — sqlite3's executescript() would commit
# on its own and break that guarantee.
MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            """
            CREATE TABLE schema_migrations (
                version    INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                type        TEXT NOT NULL DEFAULT 'task',
                priority    TEXT NOT NULL DEFAULT 'medium',
                state       TEXT NOT NULL DEFAULT 'todo',
                claimed_by  TEXT,
                claimed_at  TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_tasks_state ON tasks(state)",
            "CREATE INDEX idx_tasks_claimed_by ON tasks(claimed_by)",
            """
            CREATE TABLE labels (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
            """,
            """
            CREATE TABLE task_labels (
                task_id  INTEGER NOT NULL REFERENCES tasks(id),
                label_id INTEGER NOT NULL REFERENCES labels(id),
                PRIMARY KEY (task_id, label_id)
            )
            """,
            "CREATE INDEX idx_task_labels_label ON task_labels(label_id)",
            """
            CREATE TABLE task_links (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL REFERENCES tasks(id),
                target_id INTEGER NOT NULL REFERENCES tasks(id),
                relation  TEXT NOT NULL,
                CHECK (source_id <> target_id),
                UNIQUE (source_id, target_id, relation)
            )
            """,
            "CREATE INDEX idx_task_links_source ON task_links(source_id)",
            "CREATE INDEX idx_task_links_target ON task_links(target_id)",
            """
            CREATE UNIQUE INDEX idx_one_parent ON task_links(target_id)
                WHERE relation = 'parent_of'
            """,
            """
            CREATE TABLE task_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id    INTEGER NOT NULL REFERENCES tasks(id),
                kind       TEXT NOT NULL,
                field      TEXT,
                old_value  TEXT,
                new_value  TEXT,
                body       TEXT,
                actor      TEXT NOT NULL,
                session_id TEXT,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_task_events_task ON task_events(task_id)",
            """
            CREATE TABLE facts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                claim       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'unverified',
                verified_at TEXT,
                verified_by TEXT,
                proof       TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_facts_status ON facts(status)",
            """
            CREATE TABLE fact_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_id    INTEGER NOT NULL REFERENCES facts(id),
                kind       TEXT NOT NULL,
                old_value  TEXT,
                new_value  TEXT,
                proof      TEXT,
                note       TEXT,
                actor      TEXT NOT NULL,
                session_id TEXT,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_fact_events_fact ON fact_events(fact_id)",
        ],
    ),
    (
        2,
        [
            # The 'todo' state was renamed to 'open'; existing rows carry the
            # old literal on disk and need this data migration, unlike a new
            # value being added to the enum (see docs/spec.md §4.1).
            "UPDATE tasks SET state = 'open' WHERE state = 'todo'",
        ],
    ),
    (
        3,
        [
            # Advisory routing, distinct from claimed_by: who a task is
            # intended for, not who is working on it right now (GH#27).
            "ALTER TABLE tasks ADD COLUMN assigned_to TEXT",
            "CREATE INDEX idx_tasks_assigned_to ON tasks(assigned_to)",
        ],
    ),
]
