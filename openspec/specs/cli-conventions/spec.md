# cli-conventions Specification

## Purpose

Defines what every corvee command shares: the command tree, output formats, JSON shapes, the error object, exit codes, text input, multi-id transactions, help examples, and short option aliases. Agents parse this surface, so its shapes are stable and uniform.

## Requirements

### Requirement: Command tree
corvee SHALL expose `task`, `fact`, and `mcp` subcommand groups plus the top-level commands `init`, `brief`, `explain`, `export`, `import`, `doctor`, `completion`, and `--version`.

```
corvee
├── --version
├── init / brief / explain / export / import / doctor / completion
├── task
│   ├── add / list / ready / search / mine / show / update
│   ├── claim / unclaim / start / assign / unassign / claims
│   ├── label / labels / comment / link / unlink / tree
│   └── purge
├── fact
│   ├── add / revise / verify / unverify / retract / delete
│   └── list / search / show
└── mcp
    └── serve
```

#### Scenario: Unknown command
- **WHEN** `corvee task frobnicate` runs
- **THEN** the exit code is 2 and stderr holds a JSON error object

### Requirement: `--version` reports both versions
`corvee --version` SHALL print the package version and the schema version the binary supports, so the refusal for a newer schema can be diagnosed without guessing which install is stale.

#### Scenario: Version output
- **WHEN** `corvee --version` runs
- **THEN** the output contains the package version and the supported schema version

### Requirement: Output formats
Every command except `explain`, `completion`, and `mcp serve` SHALL accept `-o`/`--output` with `table` (default), `wide`, or `json`. `export` accepts `-o` as a destination file path instead (see below) and always writes JSON. `wide` SHALL be accepted only by `task list`, `ready`, `search`, `mine`, `claim`, `unclaim`, `start`, `assign`, `unassign`, `fact list`, `fact search`, and `brief`. Every other command SHALL reject `wide` as a usage error (exit 2).

#### Scenario: Wide on a non-listing command
- **WHEN** `corvee task show TASK-1 -o wide` runs
- **THEN** the exit code is 2

### Requirement: Success output is a uniform JSON array
With `-o json`, a command's success output SHALL be a JSON array of objects on stdout, one element per affected row, whether the command read or wrote. Commands that match nothing SHALL return `[]`. Every task and fact object SHALL carry a `scope` key (`"local"` or `"global"`), and every task object SHALL carry `blocked_by`, in every command and not only listings.

#### Scenario: Add returns the new task
- **WHEN** `corvee task add "t" --description "d" -o json` runs
- **THEN** stdout is an array with one task object whose `id` is the new `TASK-<n>`

#### Scenario: No match
- **WHEN** `corvee task list --label nosuchlabel -o json` runs
- **THEN** stdout is `[]`

### Requirement: Mutations return post-mutation state
`task claim`, `update`, `label`, and `comment` SHALL return the affected task after the mutation, and `task link` and `unlink` SHALL return both endpoints. `fact verify`, `unverify`, `revise`, and `retract` SHALL return the affected fact after the mutation. `fact delete` and `task purge` SHALL return the row's last state, since no row remains afterward.

#### Scenario: Claim result
- **WHEN** `corvee task claim TASK-1 -o json` runs
- **THEN** the returned object has `claimed_by` set to the actor

### Requirement: Detail commands return supersets
`task show -o json` SHALL return the common task object plus `labels`, `links`, `subtasks`, `events`, `events_omitted`, and `referenced`. `task mine` SHALL add `last_comment`, null when the task has none. `fact show` SHALL add `events` and `referenced`. These SHALL be supersets of the common shape, never second shapes.

#### Scenario: Show keys
- **WHEN** `corvee task show TASK-1 -o json` runs
- **THEN** each object has the six extra keys

### Requirement: Optional `warnings`
A task object SHALL carry a `warnings` list of strings only when `task update` or `task link` flags an advisory oddity, such as reopening a child under a `done` parent. A warning SHALL NOT cause a rejection.

#### Scenario: No oddity
- **WHEN** a plain `task update` runs
- **THEN** the object has no `warnings` key

### Requirement: Document-shaped commands return one object
`export`, `doctor`, `brief`, `init`, and `task tree` SHALL return a single JSON object with `-o json`, since a backup, a report, a snapshot, a bootstrap report, and a subtree are documents. `task labels` SHALL return an array of `{"name", "task_count"}`. `task claims` SHALL return an array of `{"actor", "scope", "count", "oldest_claimed_at"}`, oldest first.

#### Scenario: Doctor shape
- **WHEN** `corvee doctor -o json` runs
- **THEN** stdout is one JSON object, not an array

### Requirement: Failures write a JSON error to stderr
On failure a command SHALL write `{"error": {"code": "<stable-slug>", "message": "<human text>", ...}}` to stderr and nothing to stdout. `code` SHALL be stable and `message` MAY change. Extra keys SHALL carry recovery detail, such as `claimed_by` on a claim conflict and `blocking_ids` on a parent and child guard violation.

#### Scenario: Not found
- **WHEN** `corvee task show TASK-99999 -o json` runs
- **THEN** stdout is empty and stderr holds an object with code `task_not_found`

### Requirement: Exit codes
Every command SHALL exit with one of these codes.

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unexpected or internal error |
| 2 | Usage or validation error |
| 3 | Task or fact not found |
| 4 | Claim conflict (task held by another actor) |
| 5 | Guard violation |
| 6 | Project or config problem |

#### Scenario: Usage error
- **WHEN** `corvee task list --state nonsense` runs
- **THEN** the exit code is 2

### Requirement: Exit 2 covers invalid input
Exit 2 SHALL cover a bad flag, an unknown `--fields` name, an invalid state, a cross-namespace id, an id outside the `identifiers` grammar, a malformed `--stale` or `--since` duration, `import` of malformed JSON, a dump missing `schema_version` or carrying a non-integer one, and a dump row with an unknown column.

#### Scenario: Bad duration
- **WHEN** `corvee task list --stale banana` runs
- **THEN** the exit code is 2

### Requirement: Exit 5 covers guard violations
Exit 5 SHALL cover open children, a `parent_of` or `blocks` cycle, a self-link, a second parent, a rejected transition, claiming a terminal task, `fact delete` on a non-retracted fact, `task purge` on a non-cancelled or linked task, and a cross-scope link.

#### Scenario: Rejected transition
- **WHEN** `corvee task update TASK-1 --state cancelled` runs on a `done` task
- **THEN** the exit code is 5

### Requirement: Exit 6 covers project and config problems
Exit 6 SHALL cover no or unreadable `.corvee/config.toml`, a database that cannot be opened or written, a `.corvee/` or database directory that cannot be created, a schema newer than the binary, and `import` of a dump whose `schema_version` differs from the binary's.

#### Scenario: Unreadable config
- **WHEN** `corvee task list --scope local` runs against a corrupt `config.toml`
- **THEN** the exit code is 6

### Requirement: Free-text options read stdin with `-`
Any free-text option SHALL accept `-` to read its value from stdin. That covers `task add` description and title, `task update --description`, `task comment`, and the fact commands' `claim`, `new-claim`, `--proof`, `--note`, and `--reason`. At most one `-` SHALL appear per invocation, and a second SHALL exit 2.

Agent-written text is multi-line and holds quotes, backticks, and dollar signs, which break shell arguments.

#### Scenario: Description from stdin
- **WHEN** a multi-line string is piped to `corvee task add "t" --description -`
- **THEN** the task's description is that string verbatim

#### Scenario: Two stdin markers
- **WHEN** `corvee task add - --description -` runs
- **THEN** the exit code is 2

### Requirement: Tables collapse newlines and measure terminal cells
The plain-text table SHALL collapse an embedded newline in a cell to a single space, so each row stays on one physical line. It SHALL pad columns by terminal cell width, counting East Asian wide characters as two cells and combining marks as none. `-o json` SHALL keep the raw value.

#### Scenario: CJK title
- **WHEN** a task titled with East Asian wide characters is listed
- **THEN** later columns stay aligned under their headers

### Requirement: Default table columns are narrow
Without `--fields`, `-o table` on `task list`, `ready`, `search`, `mine`, `fact list`, `fact search`, and `brief` SHALL show `id`, `title`, `type`, `priority`, `state` for tasks and `id`, `claim`, `status` for facts. `scope` SHALL be omitted because the id encodes it.

#### Scenario: Narrow default
- **WHEN** `corvee task list` runs
- **THEN** the columns are `ID`, `TITLE`, `TYPE`, `PRIORITY`, `STATE`

### Requirement: `-o wide` restores more columns
`-o wide` SHALL restore the rest of the `--fields` allow-list except `description` and `proof`. For tasks that adds `claimed_by`, `claimed_at`, `assigned_to`, `created_at`, `updated_at`, `scope`, and `blocked_by`. For facts it adds `verified_at`, `verified_by`, `created_at`, `updated_at`, and `scope`. `-o json` SHALL always return the full row shape.

#### Scenario: Wide task columns
- **WHEN** `corvee task list -o wide` runs
- **THEN** `CLAIMED_BY` and `ASSIGNED_TO` columns appear and `DESCRIPTION` does not

### Requirement: `--fields` wins over `-o`
When `--fields` is given, the output SHALL contain exactly those fields, in a still-uniform array of objects under `-o json`, whatever `-o` says. An unknown field name SHALL exit 2 with the valid list. `--fields description` and `--fields proof` SHALL show the long text on request.

#### Scenario: Fields beat wide
- **WHEN** `corvee task list -o wide --fields id,title` runs
- **THEN** only `id` and `title` are shown

### Requirement: Fact claims truncate in the default table
In `-o table` without `--fields`, a fact `claim` wider than 60 terminal cells SHALL be cut to 60 cells, the last three being `...`. `-o wide`, `--fields claim`, `-o json`, and `fact show` SHALL carry the full claim.

#### Scenario: Long claim
- **WHEN** a 100-character claim is listed with `corvee fact list`
- **THEN** the cell is 60 cells wide and ends in `...`

### Requirement: `show` renders one record as labeled lines
`task show` and `fact show` plain-text output SHALL print `field: value` lines, one per flat column, with `description` or `proof` in its own labeled block beneath. Lowercase `labels:`, `links:`, `subtasks:`, and `events:` blocks SHALL follow for tasks, and `events:` for facts. Several ids SHALL repeat the whole block per id in the order given, separated by a blank line.

#### Scenario: Two ids
- **WHEN** `corvee task show TASK-1 TASK-2` runs
- **THEN** two blocks appear in that order, each opening with `id:`

### Requirement: Multi-id commands are all-or-nothing
`task update`, `claim`, `unclaim`, `start`, `assign`, `unassign`, `label`, and `purge` over several ids SHALL run in one transaction. If any id fails, nothing SHALL be written, the error SHALL name the failing task, and the exit code SHALL be that task's.

A partial batch would leave the caller to work out which half landed.

#### Scenario: Failure rolls back
- **WHEN** `corvee task update 4 7 9 --state done` runs and task 7 fails the transition table
- **THEN** no task changed, the error names `TASK-7`, and the exit code is 5

### Requirement: Repeated ids collapse
A repeated id in one multi-id call SHALL be deduplicated in first-seen order for `update`, `claim`, `unclaim`, `label`, and `show` and their `fact` equivalents. An id also reached by a `--cascade` side effect and named explicitly MAY appear twice, and the second pass SHALL be a no-op that takes no claim and writes no event.

#### Scenario: Duplicate id
- **WHEN** `corvee task show TASK-1 TASK-1` runs
- **THEN** `TASK-1` appears once

### Requirement: Every `--help` ends with examples
Every subcommand's `--help` SHALL end with an `Examples:` section carrying at least three runnable `corvee ...` invocations, held in the click `epilog` inside a `\b` block. They SHALL cover the plain form, a form combining usual flags, and an awkward case otherwise learned from an error. A test SHALL fail any registered command with fewer than three.

#### Scenario: New command
- **WHEN** a subcommand is registered with fewer than three epilog example lines
- **THEN** the test suite fails

### Requirement: Every option has a short alias
Every option SHALL have a one-character alias shown in `--help`. The same option name SHALL carry the same letter in every command, except that a letter MAY serve two option names that never share a command (`-f` is `--fields` on listings and `--force` on claim-like commands, `-p` is `--priority` on `task`, `--proof` on `fact`, and `--project-root` on `mcp serve`). Within one command every alias SHALL be unique.

#### Scenario: Aliases within one command
- **WHEN** `corvee task update --help` lists its options
- **THEN** every option shows a distinct one-character alias

### Requirement: Uppercase variants resolve in-command collisions
When two option names in one command collide, the second SHALL take an uppercase variant of the first's letter. These are `--parent`/`-P` beside `--priority`/`-p`, `--blocked-by`/`-B` beside `--blocks`/`-b`, `--state`/`-S` beside `--stale`/`-i` and `--scope`/`-s`, `--status`/`-S` on `fact list`, and `--title`/`-T` beside `--type`/`-t`.

#### Scenario: Parent alias
- **WHEN** `corvee task list -P TASK-1` runs
- **THEN** it filters to direct children of `TASK-1`

### Requirement: `export -o` names a file
On `export`, `-o`/`--output` SHALL name the destination file path, since `export` always writes JSON. On every other command that has it, `-o`/`--output` SHALL select the output format.

#### Scenario: Export to a file
- **WHEN** `corvee export -o backup.json` runs
- **THEN** the dump is written to `backup.json`
