# task-commands Specification

## Purpose

Defines the commands that create and change tasks, labels, links, and subtrees. Claim, assignment, state, and purge rules live in `claims-and-assignment`, `task-lifecycle`, and `task-hierarchy-links`, and read commands live in `task-queries`.

## Requirements

### Requirement: Task value sets
A task's `type` SHALL be one of `task`, `bug`, `feature`, `epic`, `chore`, or `spike`, defaulting to `task`. Its `priority` SHALL be one of `low`, `medium`, `high`, or `critical`, defaulting to `medium`. Its `state` SHALL be one of `open`, `in_progress`, `blocked`, `review`, `done`, or `cancelled`, and a new task SHALL start `open`. A link `relation` SHALL be `blocks`, `relates_to`, `duplicates`, or `parent_of`. Any other value SHALL be a usage error (exit 2).

#### Scenario: Defaults
- **WHEN** `corvee task add "t" --description "d" -o json` runs
- **THEN** the task has `type` `task`, `priority` `medium`, and `state` `open`

#### Scenario: Unknown type
- **WHEN** `corvee task add "t" --description "d" --type story` runs
- **THEN** the exit code is 2

### Requirement: `task add` requires a description
`corvee task add <title> --description <text>` SHALL require `--description`. An empty or whitespace-only value SHALL be rejected the same as a missing one, with exit 2 and error code `invalid_description`. `task update --description` SHALL stay optional.

A title alone rarely lets another session resume the work without re-deriving context.

#### Scenario: Missing description
- **WHEN** `corvee task add "t"` runs
- **THEN** the exit code is 2 with error code `invalid_description`

#### Scenario: Whitespace description
- **WHEN** `corvee task add "t" --description " "` runs
- **THEN** the exit code is 2 with error code `invalid_description`

### Requirement: `task add` rejects a blank title
`task add` SHALL reject an empty or whitespace-only title with exit 2 and error code `invalid_title`, since a blank title is unidentifiable in `task list` and `task ready`.

#### Scenario: Blank title
- **WHEN** `corvee task add "  " --description "d"` runs
- **THEN** the exit code is 2 with error code `invalid_title`

### Requirement: `task add` options
`task add` SHALL accept `--type`, `--priority`, repeatable `--label`, `--parent <id>`, and `--global`. `--global` SHALL file the task in the global database.

#### Scenario: Add under a parent
- **WHEN** `corvee task add "child" --description "d" --parent TASK-1` runs
- **THEN** the new task is a child of `TASK-1`

### Requirement: Batch creation from a file
`corvee task add --from-file <path>` SHALL create every task in a JSON array in one transaction, all-or-nothing. Each object SHALL accept `title` and `description` (both required, non-empty), `type`, `priority`, `label` (a list of strings), and `parent` (an existing task ref, not another item in the file).

#### Scenario: Valid batch
- **WHEN** a file holds three valid task objects and `corvee task add --from-file tasks.json` runs
- **THEN** three tasks exist afterward

#### Scenario: One bad item
- **WHEN** the third of five items has an empty title
- **THEN** no task is created and the exit code is 2

### Requirement: Batch creation excludes single-task arguments
`--from-file` SHALL NOT combine with the `title` argument or `--description`. Doing so SHALL be a usage error (exit 2) telling the caller to pick one form. `--global` SHALL apply to the whole file, with no per-item scope.

#### Scenario: Mixed forms
- **WHEN** `corvee task add "t" --from-file tasks.json` runs
- **THEN** the exit code is 2

### Requirement: `task update` fields
`corvee task update <id> [<id> ...]` SHALL accept `--state`, `--type`, `--priority`, `--title`, `--description`, `--force`, and `--cascade`, and write a `task_events` row per change. It SHALL enforce the transition table, the parent and child guards, and the claim gate.

#### Scenario: Retitle
- **WHEN** `corvee task update TASK-1 --title "new"` runs
- **THEN** the title is `new` and a `field_change` event for `title` exists

### Requirement: Label names are normalized and validated
Label names SHALL be lowercased and trimmed on the way in, and SHALL match `[a-z0-9][a-z0-9._/-]{0,49}`. Anything else SHALL exit 2 with the pattern in the message.

#### Scenario: Normalization
- **WHEN** `corvee task label TASK-1 --add " API "` runs
- **THEN** the task carries the label `api`

#### Scenario: Invalid label
- **WHEN** `corvee task label TASK-1 --add "has space"` runs
- **THEN** the exit code is 2 and the message shows the pattern

### Requirement: Label changes
`corvee task label <id> [<id> ...] --add <name> --remove <name>` SHALL accept both flags repeatably in one call, applying removals before additions. Adding a label a task already has, or removing one it lacks, SHALL be a no-op success.

#### Scenario: Remove then add
- **WHEN** `corvee task label TASK-1 --remove x --add x` runs
- **THEN** `x` is attached to the task

### Requirement: Label filters are normalized
`--label` filter values on `task list` and `task ready` SHALL pass through the same normalization as `--add`. A value that fails the pattern SHALL exit 2 instead of silently matching nothing.

#### Scenario: Case-insensitive filter
- **WHEN** a task is labeled `api` and `corvee task list --label API` runs
- **THEN** the task is listed

### Requirement: `task labels` lists local labels
`corvee task labels` SHALL list every label in the local project with its task count. Labels SHALL NOT merge across scope, so a global task's labels are not visible here.

#### Scenario: Count
- **WHEN** two local tasks carry `api` and `corvee task labels -o json` runs
- **THEN** the entry for `api` has `task_count` 2

### Requirement: `task comment` appends a note
`corvee task comment <id> <text>` SHALL append a `comment` event, stamped with the session id, and return the task.

#### Scenario: Comment recorded
- **WHEN** `corvee --session-id s1 task comment TASK-1 "found it"` runs
- **THEN** a `comment` event with body `found it` and session `s1` exists

### Requirement: `task link` relates two tasks
`corvee task link <source-id> <target-id> --relation blocks|relates_to|duplicates|parent_of` SHALL create the link and return both endpoints. For `parent_of`, `<source-id>` SHALL be the parent and `<target-id>` the child.

#### Scenario: Link parent to child
- **WHEN** `corvee task link TASK-1 TASK-2 --relation parent_of` runs
- **THEN** `TASK-2` is a subtask of `TASK-1`

### Requirement: `task claims` shows who holds what
`corvee task claims [--scope local|global|all]` SHALL list actors currently holding a live claim with a count and the oldest `claimed_at`, as multi-agent visibility distinct from `doctor`'s single aggregate `claimed` count.

#### Scenario: Two claimants
- **WHEN** `agent:a` holds two tasks and `agent:b` holds one, and `corvee task claims -o json` runs
- **THEN** the array has an entry for each actor with counts 2 and 1

### Requirement: `task tree` shows a subtree
`corvee task tree <id>` SHALL take exactly one id and walk the `parent_of` subtree under it, including descendants in every state. `-o json` SHALL return one nested object of `id`, `state`, `title`, and `children`. Plain text SHALL print one `id [state] title` line per task with two spaces of indent per depth, children in `parent_of` insertion order, the same order `task show` uses for `subtasks`. `-o wide` SHALL be a usage error.

#### Scenario: Nested output
- **WHEN** `TASK-1` has child `TASK-2` which has child `TASK-3` and `corvee task tree TASK-1` runs
- **THEN** `TASK-3` is printed with four spaces of indent

### Requirement: `task tree` survives cycles
The traversal SHALL keep a visited set seeded with the root, so a branch looping back to a visited id stops there instead of hanging or duplicating a subtree. It SHALL be read-only.

#### Scenario: Hand-edited cycle
- **WHEN** a database holds `A parent_of B` and `B parent_of A` and `corvee task tree A` runs
- **THEN** the command finishes and prints each task once
