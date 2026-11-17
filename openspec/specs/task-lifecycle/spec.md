# task-lifecycle Specification

## Purpose

Defines the task states, the permitted transitions between them, the derived `blocked*` display, and the one deliberate way to remove a task for good. The transition policy is data, so changing it means editing one table.

## Requirements

### Requirement: Transitions are a single table
Task transitions SHALL be restricted to the table below, held as one `dict[State, frozenset[State]]` in the constants module and consulted by one guard function.

| From | May move to |
|---|---|
| `open` | `in_progress`, `blocked`, `done`, `cancelled` |
| `in_progress` | `open`, `blocked`, `review`, `done`, `cancelled` |
| `blocked` | `open`, `in_progress`, `cancelled` |
| `review` | `in_progress`, `blocked`, `done`, `cancelled` |
| `done` | `open`, `in_progress` |
| `cancelled` | `open` |

#### Scenario: Permitted move
- **WHEN** `corvee task update TASK-1 --state review` runs on an `in_progress` task
- **THEN** the task becomes `review`

#### Scenario: Blocked cannot jump to done
- **WHEN** `corvee task update TASK-1 --state done` runs on a `blocked` task
- **THEN** the exit code is 5

#### Scenario: Cancelled revives only to open
- **WHEN** `corvee task update TASK-1 --state in_progress` runs on a `cancelled` task
- **THEN** the exit code is 5 and the message names `open` as reachable

### Requirement: Rejected transitions name what is reachable
A rejected transition SHALL exit 5 and name the states reachable from the current one, so an agent can correct itself without reading docs.

#### Scenario: Done to cancelled
- **WHEN** `corvee task update TASK-1 --state cancelled` runs on a `done` task
- **THEN** the exit code is 5 and the message lists `open` and `in_progress`

### Requirement: Same-state updates succeed
Setting a task to the state it already holds SHALL be a no-op success, so a retrying agent is never punished for being unsure.

#### Scenario: Repeat state
- **WHEN** `corvee task update TASK-1 --state open` runs on an `open` task
- **THEN** the exit code is 0 and no event is written

### Requirement: Parent and child rules layer on the table
A transition SHALL be permitted by the table and SHALL also satisfy the parent and child guards (see `task-hierarchy-links`).

#### Scenario: Permitted by table, blocked by child
- **WHEN** `corvee task update TASK-1 --state done` runs on an `in_progress` parent with an open child
- **THEN** the exit code is 5

### Requirement: Open tasks with open blockers display as `blocked*`
A task whose stored state is `open` and that has at least one open `blocks` predecessor (a source task whose state is neither `done` nor `cancelled`) SHALL display as `blocked*` in the plain-text `task list`, `ready`, `search`, `mine`, and `brief` tables and on the `state:` line of `task show`. `task tree` SHALL print the stored state. A manually set `blocked` state SHALL display as plain `blocked`, and a task carrying both SHALL show plain `blocked`.

#### Scenario: Blocker open
- **WHEN** `A blocks B`, `A` is `open`, and `corvee task list` runs
- **THEN** `B` shows as `blocked*`

### Requirement: Derived blocked is never stored
The `state` column, the transition table, `task_events`, and `corvee export` SHALL see only the stored state. A blocker finishing or being cancelled SHALL release its successors with no write and no event. Only `open` tasks SHALL be affected. An `in_progress` or `review` task SHALL keep its stored state in every view, a `done` or `cancelled` task SHALL never display as blocked, and a parent's state SHALL NOT roll up from its children.

#### Scenario: Blocker cancelled
- **WHEN** blocker `A` is cancelled
- **THEN** `B` shows as `open` with no new `task_events` row

### Requirement: JSON carries `blocked_by`
Every JSON task object SHALL carry a `blocked_by` array of the ids of the task's open `blocks` predecessors, empty when there are none. `state` in JSON SHALL stay the stored value.

#### Scenario: Derived-blocked task in JSON
- **WHEN** `TASK-1 blocks TASK-2`, `TASK-1` is `open`, and `corvee task show TASK-2 -o json` runs
- **THEN** `state` is `open` and `blocked_by` is `["TASK-1"]`

### Requirement: `--state` filters match the displayed state
`task list --state blocked` SHALL return stored-`blocked` and derived-blocked tasks. `task list --state open` SHALL exclude derived-blocked tasks. Every other `--state` value SHALL match the stored value.

#### Scenario: Open filter
- **WHEN** `B` is derived-blocked and `corvee task list --state open` runs
- **THEN** `B` is not returned

### Requirement: Cancelling is the default way to abandon a task
corvee SHALL NOT provide a `delete` command for tasks. Abandoning a task SHALL be a transition to `cancelled`, and the row and its history SHALL stay queryable.

#### Scenario: No delete command
- **WHEN** `corvee task delete TASK-1` runs
- **THEN** the exit code is 2 because the command does not exist

### Requirement: `task purge` removes a cancelled, unlinked task
`corvee task purge <id> [<id> ...]` SHALL permanently remove a task and its entire `task_events` history, and SHALL work only when the task's state is `cancelled` and it carries no `task_links` in either direction. A task that is not `cancelled` SHALL fail with a guard violation (exit 5, `task_not_cancelled`) naming `corvee task update --state cancelled`. A task with links SHALL fail with exit 5 and `task_has_links`, pointing at `corvee task unlink`.

#### Scenario: Purge a cancelled task
- **WHEN** `corvee task purge TASK-9` runs on a `cancelled` task with no links
- **THEN** the task and its events no longer exist

#### Scenario: Purge an open task
- **WHEN** `corvee task purge TASK-9` runs on an `open` task
- **THEN** the exit code is 5 with error code `task_not_cancelled`

#### Scenario: Purge a linked task
- **WHEN** `corvee task purge TASK-9` runs on a `cancelled` task that is the target of a `blocks` link
- **THEN** the exit code is 5 with error code `task_has_links`

### Requirement: Purge is atomic and reports last state
Multiple ids to `task purge` SHALL apply in one transaction, all-or-nothing. The response SHALL be each purged task's last state, since no row remains to show afterward. `doctor` totals and every listing and export SHALL reflect the removal immediately.

#### Scenario: One bad id
- **WHEN** `corvee task purge TASK-9 TASK-10` runs and `TASK-10` is `open`
- **THEN** the exit code is 5 and `TASK-9` still exists
