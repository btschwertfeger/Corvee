# backup-restore Specification

## Purpose

Both databases are git-ignored and live outside any repository, so a project's decision history would otherwise depend on one file surviving on one machine. `export` and `import` give a verbatim, id-preserving backup of either database.

## Requirements

### Requirement: `export` writes one JSON dump
`corvee export` SHALL write one JSON object containing `schema_version`, `exported_at`, and the full contents of `tasks`, `labels`, `task_labels`, `task_links`, `task_events`, `facts`, and `fact_events`, to stdout or to the file named by `-o`/`--output`. Integer ids SHALL be preserved verbatim, so `TASK-14` and `FACT-7` mean the same row after a restore.

#### Scenario: Dump keys
- **WHEN** `corvee export` runs in a project with tasks and facts
- **THEN** stdout is one JSON object holding `schema_version`, `exported_at`, and the seven table arrays

### Requirement: `export` selects exactly one database
`corvee export [--scope local|global]` SHALL default to `local` and SHALL select exactly one database, never a merged dump, because local and global ids both start at 1 and would collide.

#### Scenario: Global export
- **WHEN** `corvee export --scope global` runs
- **THEN** the dump holds only the global database's rows

### Requirement: `import` restores only into an empty database
`corvee import <file> [--scope local|global]` SHALL refuse to run against a database that already holds tasks, facts, or labels, exiting 2. Labels count because a label survives a `task purge` after every task wearing it is gone, so it is the one row an otherwise-empty project can still carry.

#### Scenario: Non-empty target
- **WHEN** `corvee import backup.json` runs in a project that already has a task
- **THEN** the exit code is 2 and nothing is written

### Requirement: `import` requires a matching schema version
`import` SHALL reject a dump whose `schema_version` differs from the binary's, with exit 6. Rows are inserted verbatim with no migration, and a value valid under an older schema, such as the pre-v2 state `todo`, may be invalid under the current one. A dump missing `schema_version` or carrying a non-integer one SHALL exit 2.

#### Scenario: Older dump
- **WHEN** a dump with `schema_version` 2 is imported by a binary at version 3
- **THEN** the exit code is 6

### Requirement: `import` validates dump rows
`import` SHALL validate each row's keys against that table's real columns before inserting, exiting 2 on a foreign or crafted key rather than surfacing a raw SQLite error. Malformed JSON SHALL also exit 2.

#### Scenario: Unknown column
- **WHEN** a dump's `tasks` row carries a key `evil`
- **THEN** the exit code is 2 and nothing is written

### Requirement: `import` scope must match the dump
`--scope` SHALL default to `local` and SHALL name the database receiving the rows. A dump has no scope marker, so restoring a local dump with `--scope global` SHALL succeed and land the same rows, verbatim ids included, in the global database.

#### Scenario: Cross-scope restore
- **WHEN** a local dump is imported with `--scope global` into an empty global database
- **THEN** the rows exist there with their original ids

### Requirement: Round trip is lossless
Exporting a populated database and importing the dump into a freshly initialized one SHALL reproduce the same content, ids included, for tasks and facts.

#### Scenario: Round trip
- **WHEN** a project with tasks, labels, links, facts, and events is exported and imported into a new project
- **THEN** a second export of the new project equals the first apart from `exported_at`
