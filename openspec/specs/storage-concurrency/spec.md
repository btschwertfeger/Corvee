# storage-concurrency Specification

## Purpose

Defines how each corvee invocation opens SQLite, wraps its work in a transaction, and checks the schema version. These rules make concurrent use by several agents on one machine safe without a daemon.

## Requirements

### Requirement: Connect, work, close
Each `corvee` invocation SHALL open the SQLite file named by the project binding, do its work, and close it. No daemon or shared process SHALL be required.

#### Scenario: Two CLI processes at once
- **WHEN** two `corvee` processes run against one database at the same time
- **THEN** each opens its own connection and neither depends on a long-lived process

### Requirement: WAL mode and busy timeout on every connection
Every connection SHALL run SQLite in WAL mode, so readers block neither writers nor each other. Every connection SHALL set `PRAGMA busy_timeout = 5000`, so a writer waits for another writer to finish instead of failing immediately with `SQLITE_BUSY`.

#### Scenario: Reader during a write
- **WHEN** a read command runs while another process holds a write transaction
- **THEN** the read completes without waiting for the writer

### Requirement: Foreign keys enforced
Every connection SHALL set `PRAGMA foreign_keys = ON`, since SQLite leaves it off by default and every `REFERENCES` in the schema is otherwise decorative.

#### Scenario: Orphaning insert
- **WHEN** a statement inserts a `task_events` row referencing a nonexistent task
- **THEN** SQLite rejects it with a foreign key error

### Requirement: Writing commands take the write lock up front
Each invocation SHALL wrap its work in one transaction. A command that writes SHALL use `BEGIN IMMEDIATE`, taking the write lock before its first read pins a WAL snapshot, so a later write cannot fail with `SQLITE_BUSY_SNAPSHOT`, which `busy_timeout` does not retry.

#### Scenario: Multi-id write fails midway
- **WHEN** `corvee task update 4 7 9 --state done` fails on task 7
- **THEN** the transaction rolls back and no task changed

### Requirement: Read-only commands never take a write lock
A command that only reads SHALL use a plain `BEGIN`, so it never takes a write lock and never blocks a writer. The read-only commands are `task list`, `task show`, `task ready`, `task search`, `task mine`, `task claims`, `task tree`, `task labels`, `fact list`, `fact search`, `fact show`, `export`, `doctor`, and `brief`.

#### Scenario: Read during a write transaction
- **WHEN** `corvee task list` runs while another process holds `BEGIN IMMEDIATE`
- **THEN** the list returns without waiting for the writer to commit

### Requirement: Schema version is checked before any lock
Every invocation SHALL begin by reading `MAX(version)` from `schema_migrations` as a plain read that takes no lock. A version equal to the one the binary ships SHALL proceed. This keeps read commands off the write path, so they work against a read-only database.

#### Scenario: Read command on a read-only database
- **WHEN** `corvee task list` runs against a read-only database at the current schema version
- **THEN** it succeeds without attempting a write

### Requirement: Older schemas migrate under one lock
If the stored version is lower than the binary's, the command SHALL re-read the version under `BEGIN IMMEDIATE` and apply the missing migrations. Two processes racing to migrate SHALL serialize on that transaction, so no migration applies twice.

#### Scenario: Two processes migrate a fresh database
- **WHEN** two processes open a database at an older schema version at the same moment
- **THEN** each missing migration is applied exactly once

### Requirement: Newer schemas are refused
If the stored version is higher than the binary's, the command SHALL refuse and exit 6, with a message naming both versions and telling the user to upgrade. An older binary writing to a schema it does not understand corrupts data a newer binary wrote.

#### Scenario: Database from a newer binary
- **WHEN** the database holds schema version 5 and the binary ships version 3
- **THEN** the exit code is 6 and the message names versions 5 and 3

### Requirement: Fact writes are last-write-wins
Facts SHALL have no claim mechanism. When two actors revise the same fact at the same moment, both writes SHALL succeed, the second SHALL win, and `fact_events` SHALL keep both attempts as separate rows.

A fact converges on one current claim, which last-write-wins reaches without coordination. Task edits, unlike fact revisions, genuinely conflict.

#### Scenario: Concurrent revisions
- **WHEN** two actors revise one fact concurrently
- **THEN** the fact holds the later claim text and `fact_events` holds two `revised` rows
