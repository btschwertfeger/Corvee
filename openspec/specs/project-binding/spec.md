# project-binding Specification

## Purpose

Defines how a directory is bound to a corvee project, where the database lives, and how every command finds it. The binding is a small config file, analogous to `.git`, with no task data in it.

## Requirements

### Requirement: `init` creates the project binding
`corvee init` SHALL create `.corvee/config.toml` in the current directory, with no repo-root auto-detection. The file SHALL hold a single key, `db_path`, defaulting to `.corvee/corvee.db` next to it. If a `.gitignore` already exists in that directory, `init` SHALL add a `.corvee/` entry to it. `init` SHALL NOT create a `.gitignore` that does not exist.

#### Scenario: Fresh directory with a `.gitignore`
- **WHEN** `corvee init` runs in a directory containing a `.gitignore` without a `.corvee/` entry
- **THEN** `.corvee/config.toml` exists with `db_path` set to the default
- **AND** `.gitignore` gains a `.corvee/` entry

#### Scenario: Fresh directory without a `.gitignore`
- **WHEN** `corvee init` runs in a directory with no `.gitignore`
- **THEN** no `.gitignore` is created

### Requirement: `init` is idempotent
Re-running `corvee init` in a directory that already has `.corvee/config.toml` SHALL leave the config and the database untouched, add the `.gitignore` entry only if the file exists and lacks it, and exit 0 reporting what it did and did not do. `init` SHALL NOT write over anything that exists.

Truncating an existing database on a second `init` would destroy a backlog through a command people run speculatively.

#### Scenario: Second init keeps the backlog
- **WHEN** `corvee init` runs a second time in an initialized project that holds tasks
- **THEN** the exit code is 0 and every existing task is still present

### Requirement: `config.toml` is the only declaration of the database location
The database location SHALL be declared only in `config.toml`. There SHALL be no environment override and no `--db` flag on `task` or `fact` commands, so two invocations from the same directory cannot disagree about which file they write to.

#### Scenario: No per-command database flag
- **WHEN** a user passes `--db` to `corvee task list`
- **THEN** the command fails with a usage error (exit 2)

### Requirement: Relative `db_path` resolves against the config's directory
A relative `db_path` SHALL resolve against the directory containing `config.toml`, never against the current working directory.

#### Scenario: Command run from a subdirectory
- **WHEN** a command runs from a subdirectory of a project whose `db_path` is the default
- **THEN** it opens the project's `.corvee/corvee.db`, not a path under the subdirectory

#### Scenario: Sibling checkout shares a database
- **WHEN** a sibling worktree's `db_path` is `../../main/.corvee/corvee.db`
- **THEN** it resolves to the same file regardless of where the command runs

### Requirement: `init --db-path` chooses the location at creation only
`corvee init --db-path <path>` SHALL write `<path>` into `config.toml` instead of the default, resolved against the config's own directory. The flag SHALL be consulted only while `config.toml` is being created and SHALL be inert on a re-run.

#### Scenario: Re-run with a different path
- **WHEN** `corvee init --db-path other.db` runs in an already initialized project
- **THEN** `config.toml` still holds its original `db_path`

### Requirement: `db_path` is written as an escaped TOML string
`init` SHALL write the `--db-path` value as a properly escaped TOML string, so a path holding a quote, a backslash, or a control character resolves back to the file the user named. A path that is not valid UTF-8 has no TOML spelling, so `init` SHALL refuse it with exit 2 and error code `invalid_db_path` before writing anything.

#### Scenario: Path with a quote
- **WHEN** `corvee init --db-path 'a"b.db'` runs
- **THEN** `config.toml` is valid TOML and the project opens `a"b.db`

#### Scenario: Non-UTF-8 path
- **WHEN** `corvee init --db-path` receives a path that is not valid UTF-8
- **THEN** the exit code is 2 with error code `invalid_db_path` and no files are written

### Requirement: Project resolution walks up from the current directory
The CLI SHALL resolve the project by walking up from the current directory to the nearest `.corvee/config.toml`, the way git walks up to find `.git`. A project with no resolvable config SHALL fail with exit 6 and error code `no_project` for commands that require a local project.

Each git worktree has its own `.corvee/config.toml` and therefore its own backlog by default.

#### Scenario: Subdirectory of a project
- **WHEN** `corvee task list` runs two directories below the one containing `.corvee/config.toml`
- **THEN** it lists that project's tasks without re-registering anything

#### Scenario: Outside any project
- **WHEN** `corvee task list --scope local` runs where no ancestor has `.corvee/config.toml`
- **THEN** the exit code is 6 with error code `no_project`
