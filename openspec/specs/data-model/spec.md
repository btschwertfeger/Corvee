# data-model Specification

## Purpose

Defines the SQLite schema that holds tasks, labels, links, facts, and their event histories, how the schema evolves through migrations, and the conventions every row follows. Both the local and the global database use this schema.

## Requirements

### Requirement: Schema v1 tables and indexes
A new database SHALL start from this v1 schema.

```sql
CREATE TABLE schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL DEFAULT 'task',    -- task|bug|feature|epic|chore|spike
    priority    TEXT NOT NULL DEFAULT 'medium',  -- low|medium|high|critical
    state       TEXT NOT NULL DEFAULT 'todo',    -- v1 value, see v2 below
    claimed_by  TEXT,                            -- actor string, NULL = unclaimed
    claimed_at  TEXT,                            -- claim last asserted
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX idx_tasks_state ON tasks(state);
CREATE INDEX idx_tasks_claimed_by ON tasks(claimed_by);

CREATE TABLE labels (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE task_labels (
    task_id  INTEGER NOT NULL REFERENCES tasks(id),
    label_id INTEGER NOT NULL REFERENCES labels(id),
    PRIMARY KEY (task_id, label_id)
);
CREATE INDEX idx_task_labels_label ON task_labels(label_id);

CREATE TABLE task_links (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES tasks(id),
    target_id INTEGER NOT NULL REFERENCES tasks(id),
    relation  TEXT NOT NULL,    -- blocks|relates_to|duplicates|parent_of
    CHECK (source_id <> target_id),
    UNIQUE (source_id, target_id, relation)
);
CREATE INDEX idx_task_links_source ON task_links(source_id);
CREATE INDEX idx_task_links_target ON task_links(target_id);
CREATE UNIQUE INDEX idx_one_parent ON task_links(target_id)
    WHERE relation = 'parent_of';

CREATE TABLE task_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES tasks(id),
    kind       TEXT NOT NULL,    -- created|comment|field_change
    field      TEXT,             -- set when kind=field_change
    old_value  TEXT,
    new_value  TEXT,             -- title when kind=created
    body       TEXT,             -- set when kind=comment
    actor      TEXT NOT NULL,
    session_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_task_events_task ON task_events(task_id);

CREATE TABLE facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    claim       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'unverified',  -- unverified|verified|retracted
    verified_at TEXT,             -- NULL unless status='verified'
    verified_by TEXT,             -- actor who last verified
    proof       TEXT,             -- NULL unless status='verified'
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX idx_facts_status ON facts(status);

CREATE TABLE fact_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id    INTEGER NOT NULL REFERENCES facts(id),
    kind       TEXT NOT NULL,   -- created|revised|verified|unverified|retracted
    old_value  TEXT,            -- old claim text, for 'revised'
    new_value  TEXT,            -- new claim text, for 'created'/'revised'
    proof      TEXT,            -- for 'verified'
    note       TEXT,            -- free-text reason, for 'unverified'/'retracted'
    actor      TEXT NOT NULL,
    session_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_fact_events_fact ON fact_events(fact_id);
```

#### Scenario: Fresh database
- **WHEN** a database is created from nothing
- **THEN** every table above exists and `schema_migrations` records each applied version

### Requirement: Schema v2 renames the `todo` state to `open`
Migration v2 SHALL run `UPDATE tasks SET state = 'open' WHERE state = 'todo'`. The v1 DDL SHALL stay exactly as written, so this section documents migration history rather than a live snapshot. A database still at v1 SHALL pick up the rename the next time any command opens it.

#### Scenario: Old database upgraded
- **WHEN** a v1 database holds a task with state `todo` and any command opens it
- **THEN** the task's state is `open` and `schema_migrations` holds version 2

### Requirement: Schema v3 adds `assigned_to`
Migration v3 SHALL run `ALTER TABLE tasks ADD COLUMN assigned_to TEXT` and `CREATE INDEX idx_tasks_assigned_to ON tasks(assigned_to)`. The column carries advisory routing, distinct from `claimed_by` (see `claims-and-assignment`).

#### Scenario: Old database upgraded
- **WHEN** a v2 database is opened by this binary
- **THEN** `tasks.assigned_to` exists and is NULL for every existing row

### Requirement: Timestamps are fixed-width UTC
Every timestamp SHALL be fixed-width UTC ISO-8601 with milliseconds, such as `2026-09-11T14:03:22.123Z`, so plain text sorting matches chronological order. Ties SHALL break on `id` or rowid. Every timestamp SHALL come from one shared helper, because `datetime.isoformat()` emits microseconds and a `+00:00` offset, which break the fixed width.

#### Scenario: Text order equals time order
- **WHEN** two rows are created a millisecond apart
- **THEN** sorting their `created_at` values as text puts the earlier row first

### Requirement: `updated_at` advances on any recorded activity
`tasks.updated_at` SHALL advance on any write that produces a `task_events` row for that task, including comments and label and link changes. `facts.updated_at` SHALL follow the same rule against `fact_events`.

#### Scenario: Comment touches the task
- **WHEN** a comment is added to a task
- **THEN** that task's `updated_at` moves to the comment's timestamp

### Requirement: Enumerated values are free text validated in the CLI layer
`state`, `priority`, `type`, `relation`, and `status` SHALL be free `TEXT` columns without SQL `CHECK` enums, and the CLI layer SHALL validate allowed values from one shared constants module. Adding a value SHALL need no migration. Renaming or removing a value SHALL need a data migration that bumps `CURRENT_SCHEMA_VERSION`, since rows on disk carry the old literal.

SQLite cannot cheaply alter a `CHECK` constraint, and the schema is expected to evolve.

#### Scenario: Invalid state rejected
- **WHEN** `corvee task update TASK-1 --state nonsense` runs
- **THEN** the exit code is 2 and no row changes

### Requirement: Task timeline is one table with three event kinds
`task_events` SHALL hold three kinds of row. A `created` row is written once when the task is made, with the title in `new_value`. A `comment` row is a manual note in `body`. A `field_change` row is written by corvee on every mutation, including claim, unclaim, label, and link changes, where `field` is `label` or `link:<relation>` and the value sits in `new_value` or `old_value`. An unlink SHALL NOT be silent.

#### Scenario: Unlink leaves a trace
- **WHEN** a `blocks` link is removed with `corvee task unlink`
- **THEN** a `field_change` event with field `link:blocks` and the removed value in `old_value` exists

### Requirement: Facts reference no task
The `facts` table SHALL have no foreign key toward `tasks`. Connecting a fact to a task is a convention, such as a fact id in a task comment, and never a schema relationship.

#### Scenario: Task deleted by purge
- **WHEN** a task whose comments mention a fact is purged
- **THEN** the fact remains unchanged
