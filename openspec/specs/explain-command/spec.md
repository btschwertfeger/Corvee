# explain-command Specification

## Purpose

An agent should not need every subcommand's `--help` or the README to learn that corvee exists and how to use it minimally. `corvee explain` prints one short, fixed orientation block that an agent reads once per session.

## Requirements

### Requirement: `explain` is static and cheap
`corvee explain` SHALL print a fixed plain-text block, with no database access and no `-o`/`--output` flag, small enough to read once per session without consuming meaningful context.

The static output also means `explain` never surfaces live data such as label names, which `brief` provides instead.

#### Scenario: Works anywhere
- **WHEN** `corvee explain` runs in a directory with no project and no global database
- **THEN** the exit code is 0 and no file is created

#### Scenario: No output flag
- **WHEN** `corvee explain -o json` runs
- **THEN** the exit code is 2

### Requirement: Output is grouped under three headers
The block SHALL be grouped under the plain headers `TASKS`, `FACTS`, and a closing `GENERAL`, so a task-only agent can skip `FACTS`. Content that applies to both (`--global`, `--actor` and `--session-id`, the `-o json` convention, the `--help` pointer) SHALL stay in `GENERAL` without duplication.

#### Scenario: Headers present
- **WHEN** `corvee explain` runs
- **THEN** the lines `TASKS`, `FACTS`, and `GENERAL` appear in that order

### Requirement: Purpose statement
The block SHALL open with corvee's purpose, including that claims support multiple concurrent agents and that a separate store holds checked-true facts.

#### Scenario: Purpose present
- **WHEN** `corvee explain` runs
- **THEN** the first paragraph mentions multiple agents and a store of checked-true facts

### Requirement: Core commands with one example each
The block SHALL list the commands needed most of the time with one example each, covering `brief`, `task mine`, `task ready`, `task search`, `task list`, `task add`, `task claim`, `task start`, `task update`, `task comment`, `task show`, `task link`, `task claims`, and `task assign`. `brief` and `task mine` SHALL come first and `task search` SHALL precede `task add`, since resuming beats starting something new and checking for an existing task stops duplicate filing.

#### Scenario: Order
- **WHEN** `corvee explain` runs
- **THEN** the `brief` example appears before the `task add` example, and `task search` appears before `task add`

### Requirement: Track work as it happens
The block SHALL state as a rule, separate from the example flow, that nontrivial work is tracked as it happens and never after the fact. It SHALL say to `task add` with a description and `task claim` before starting, and to record a fact when it is established. It SHALL state that `task claim` alone leaves the task `open` and that `task start` moves it to `in_progress`, claiming first if needed.

#### Scenario: Rule present
- **WHEN** `corvee explain` runs
- **THEN** the text says to file and claim a task before starting work and names `task start` as the step that sets `in_progress`

### Requirement: One task per independent item
Immediately after that rule, the block SHALL state that a request breaking into several independently resolvable items gets one task per item, not one task bundling them.

#### Scenario: Batch guidance
- **WHEN** `corvee explain` runs
- **THEN** the text tells the reader to file one task per item for a batch of distinct pieces

### Requirement: Nudge away from default type and priority
After the add, claim, and start example flow, the block SHALL warn against leaving every task at the `task` and `medium` defaults when a more specific value is true, and SHALL recommend recording a real dependency as `task link ... --relation blocks`. It SHALL end with two sentences on the `blocked*` marker in tables and `task show` and on `blocked_by` as the JSON and MCP signal while `state` stays `open`.

#### Scenario: Blocks guidance
- **WHEN** `corvee explain` runs
- **THEN** the text mentions `--relation blocks`, `blocked*`, and `blocked_by`

### Requirement: Facts and scope
The block SHALL show a `fact add` and `fact verify` example and say facts are not linked to tasks by the schema. It SHALL say `--global` on `task add` and `fact add` files into the shared database and is needed only on `add`.

#### Scenario: Global note
- **WHEN** `corvee explain` runs
- **THEN** the text states that `--global` is needed only on `add`

### Requirement: Claims and output conventions
The block SHALL say a claim goes stale after 4h of silence and that re-running `task claim` refreshes it. It SHALL state that `-o json` is always passed and yields an array on stdout or an `{"error": {"code": ...}}` object on stderr, and SHALL point to `corvee <command> --help` for flags.

#### Scenario: Staleness note
- **WHEN** `corvee explain` runs
- **THEN** the text mentions the 4h stale window and the `--help` pointer
