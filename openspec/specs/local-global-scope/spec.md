# local-global-scope Specification

## Purpose

Every task and fact lives in exactly one of two databases. The local project database holds one project's work. One global database, shared across every project on the machine, holds machine-wide chores and facts. This capability defines how scope is chosen, merged for reads, and kept apart for writes.

## Requirements

### Requirement: Two independent databases
Each task and fact SHALL live in exactly one database. The local database SHALL be the one resolved by `project-binding`. The global database SHALL be at `~/.corvee/corvee.db` and SHALL have no `config.toml`. Each database SHALL keep its own connection, transaction, and migration lifecycle.

#### Scenario: Row lives in one database
- **WHEN** a task is filed without `--global`
- **THEN** it exists only in the local database and never in the global one

### Requirement: Global database path override
If `$CORVEE_GLOBAL_DB` is set, it SHALL replace the fixed global path, taken as-is against the current directory with no `expanduser()` or `resolve()`. It is an internal escape hatch for tests and agent tooling and SHALL NOT be part of the documented CLI or config surface.

#### Scenario: Global path redirected
- **WHEN** `CORVEE_GLOBAL_DB=/tmp/scratch.db` is set and `corvee task add ... --global` runs
- **THEN** the task is written to `/tmp/scratch.db` and `~/.corvee/corvee.db` is untouched

### Requirement: Global database is created lazily
`corvee init` SHALL NOT create or touch the global database. The first command that needs to write to it SHALL create `~/.corvee/` and the database file, using the same schema bootstrap as a fresh local database. Those commands are `task add --global`, `fact add --global`, and any mutating command given a `TASK-GLOBAL-<n>` or `FACT-GLOBAL-<n>` id. A read-only command SHALL NOT create it, and when the file does not exist the global side of a merged query SHALL be empty.

#### Scenario: Listing never creates the global database
- **WHEN** `corvee task list` runs on a machine where `~/.corvee/corvee.db` does not exist
- **THEN** the file still does not exist afterward

#### Scenario: First global write
- **WHEN** `corvee fact add "x" --global` runs on a machine with no `~/.corvee/`
- **THEN** `~/.corvee/corvee.db` is created with the current schema and holds the fact

### Requirement: Scope is fixed at creation and encoded in the id
`--global` on `task add` and `fact add` SHALL mark the new row as global. No command SHALL move an existing row between scopes. Every other command that takes an id SHALL infer scope from the id (see `identifiers`) and SHALL NOT need a `--global` flag.

#### Scenario: Operating on a global task
- **WHEN** `corvee task comment TASK-GLOBAL-3 "note"` runs
- **THEN** the comment is written to the global database without any scope flag

### Requirement: Listing merges both databases
Commands whose `--scope` defaults to `all` (`task list`, `task ready`, `task search`, `task mine`, `task claims`, `fact list`, `fact search`, `brief`) SHALL merge local and global results by default. `--scope local|global|all` SHALL narrow it. Each returned task or fact SHALL carry a `scope` key of `"local"` or `"global"` alongside its namespaced `id`.

#### Scenario: Default merge
- **WHEN** one local and one global task are open and `corvee task list -o json` runs
- **THEN** both are returned, with `scope` values `"local"` and `"global"`

#### Scenario: Narrowed to local
- **WHEN** `corvee task list --scope local -o json` runs
- **THEN** only local tasks are returned

### Requirement: Merged reads never span one transaction
A merged read SHALL open and close one ordinary connection per database in turn, never a cross-database transaction. A command that mutates SHALL touch exactly one database.

#### Scenario: Mutation touches one database
- **WHEN** `corvee task update TASK-GLOBAL-3 --state done` runs
- **THEN** only the global database is opened for writing

### Requirement: `--limit` applies to the merged result
`--limit` SHALL apply after the merged result is fetched from both databases and sorted once, never to each database independently. `--limit` SHALL require a positive integer, and `0` or a negative value SHALL be a usage error (exit 2).

Asking each database for `--limit` rows first and concatenating could drop a row that belonged in the top `n` because it came from whichever database was queried second.

#### Scenario: Top row lives in the second database
- **WHEN** the highest-ranked task is global and `corvee task list --limit 1` runs
- **THEN** that global task is the one returned

#### Scenario: Zero limit
- **WHEN** `corvee task list --limit 0` runs
- **THEN** the exit code is 2

### Requirement: A missing project or global database drops out of merged reads
Every command whose `--scope` defaults to `all`, and `doctor`, SHALL check whether a local project resolves and whether the global database exists before querying, and SHALL silently omit whichever is missing. Global tasks and facts SHALL be usable from any directory, including one that has never seen `corvee init`. An explicit `--scope local` SHALL fail with exit 6 and error code `no_project` when no project resolves.

#### Scenario: Global backlog from an uninitialized directory
- **WHEN** `corvee task add "renew the CA cert" --description "..." --global` runs in `/tmp`, then `corvee task mine` runs in another uninitialized directory
- **THEN** both succeed and `task mine` can show the global task

#### Scenario: Explicit local scope without a project
- **WHEN** `corvee task list --scope local` runs where no project resolves
- **THEN** the exit code is 6 with error code `no_project`

### Requirement: Cross-scope links are rejected
`task link` SHALL operate within one database's foreign keys. A local task SHALL NOT be linked to a global task in either direction. Attempting it SHALL be a guard violation, exit 5, with error code `cross_scope_link`.

#### Scenario: Local blocks global
- **WHEN** `corvee task link TASK-1 TASK-GLOBAL-2 --relation blocks` runs
- **THEN** the exit code is 5 with error code `cross_scope_link`
