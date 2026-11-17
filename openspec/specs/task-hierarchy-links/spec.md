# task-hierarchy-links Specification

## Purpose

Defines the four task relations (`blocks`, `relates_to`, `duplicates`, `parent_of`) and the guards on them. A `parent_of` link forms a forest of subtasks with one traversal path shared by all four relations.

## Requirements

### Requirement: Self-links are rejected
`corvee task link` SHALL reject a link from a task to itself as a guard violation (exit 5).

#### Scenario: Link to self
- **WHEN** `corvee task link TASK-3 TASK-3 --relation relates_to` runs
- **THEN** the exit code is 5 and no link is written

### Requirement: A parent cannot finish with open children
A task SHALL NOT transition to `done` while any child (a `parent_of` link with this task as `source_id`) is in a state other than `done` or `cancelled`. `task update` SHALL reject the transition with a guard violation (exit 5) listing the blocking subtask ids in `blocking_ids`.

#### Scenario: Open child blocks done
- **WHEN** `TASK-1` has an `open` child `TASK-2` and `corvee task update TASK-1 --state done` runs
- **THEN** the exit code is 5 and the error lists `TASK-2` in `blocking_ids`

### Requirement: Reopening under a done parent warns
Reopening a child of a `done` parent SHALL succeed without changing the parent, and the child's JSON object SHALL carry a `warnings` list, whether the reopen came from `task update --state open` or from MCP `task_reopen`. Linking a non-terminal child to an already-`done` parent with `task link --relation parent_of` SHALL succeed and carry the same warning on the parent's object.

#### Scenario: Reopened child
- **WHEN** a child of a `done` parent is moved to `open`
- **THEN** the call succeeds and the child's object has a non-empty `warnings` list

### Requirement: At most one direct parent
A task SHALL have at most one direct parent. `corvee task link <parent> <child> --relation parent_of` SHALL fail with a guard violation (exit 5) when `<child>` already has a parent, naming the current parent and pointing at `corvee task unlink`. The `idx_one_parent` partial unique index SHALL enforce this in the database too, because two agents linking one child to different parents concurrently would both pass a read-then-write check.

#### Scenario: Second parent
- **WHEN** `TASK-3` is already a child of `TASK-1` and `corvee task link TASK-2 TASK-3 --relation parent_of` runs
- **THEN** the exit code is 5 and the message names `TASK-1` and `corvee task unlink`

### Requirement: Parent cancellation is rejected while children are open
`corvee task update <parent> --state cancelled` SHALL be rejected with a guard violation (exit 5) while any child is still open, listing those children, the same way `done` is.

#### Scenario: Cancel with open child
- **WHEN** `corvee task update TASK-1 --state cancelled` runs while child `TASK-2` is `in_progress`
- **THEN** the exit code is 5 and the error lists `TASK-2`

### Requirement: Cancel cascade
With `--cascade`, `task update <parent> --state cancelled` SHALL cancel the parent and every descendant that is not already `done`, walking the subtree. It SHALL write a `field_change` event per affected task, clear their claims under the terminal-state rule, and list every id it touched in the output. Children already `done` SHALL keep that state.

#### Scenario: Cascade over a subtree
- **WHEN** `TASK-1` has an `open` child `TASK-2` and a `done` child `TASK-3`, and `corvee task update TASK-1 --state cancelled --cascade` runs
- **THEN** `TASK-1` and `TASK-2` are `cancelled`, `TASK-3` stays `done`, and the output lists `TASK-1` and `TASK-2`

### Requirement: Cascade does not steal claims
A descendant claimed by another actor SHALL block the whole cascade with the same claim conflict (exit 4) a named task would raise. `--cascade` authorizes touching unclaimed descendants and SHALL NOT override a live foreign claim.

#### Scenario: Foreign claim on a descendant
- **WHEN** a descendant is claimed by `agent:other` and `agent:claude` runs `task update <parent> --state cancelled --cascade`
- **THEN** the exit code is 4 and no task changed

### Requirement: `--cascade` and `--force` are independent flags
`--force` SHALL override another actor's claim on a named task or a descendant. `--cascade` SHALL authorize writes to tasks the caller never named. A call blocked by both a foreign claim and open children SHALL need both flags.

Bundling the two would let an agent that reaches for `--force` after a claim conflict cancel a subtree nobody looked at.

#### Scenario: Both blockers
- **WHEN** a parent is claimed by another actor and has open children, and `task update <parent> --state cancelled --force` runs
- **THEN** the call is rejected for the open children

### Requirement: `parent_of` and `blocks` links are cycle-checked
A new `parent_of` or `blocks` link SHALL be rejected with a guard violation (exit 5) if it would form a cycle. The check SHALL walk the new parent's (or source's) ancestor chain over edges of that relation and reject if the new child appears on it. The walk SHALL run iteratively with a `visited` set so that a cycle already present in a hand-edited database ends the loop.

A `blocks` cycle would drop both tasks out of `task ready` forever while every command reports success.

#### Scenario: Cycle through two edges
- **WHEN** `A parent_of B` and `B parent_of C` exist and `corvee task link C A --relation parent_of` runs
- **THEN** the exit code is 5 because ancestors of `C` are `B` and `A`

#### Scenario: Blocks cycle
- **WHEN** `A blocks B` exists and `corvee task link B A --relation blocks` runs
- **THEN** the exit code is 5

### Requirement: `blocks` carries no state guard
A `blocks` link SHALL be advisory input to `task ready` and to the derived `blocked*` display (see `task-lifecycle`). `task update` SHALL NOT refuse a transition because of an open `blocks` predecessor.

#### Scenario: Blocked task can start
- **WHEN** `A blocks B` with `A` open and `corvee task update B --state in_progress` runs
- **THEN** the update succeeds

### Requirement: `relates_to` is stored once and shown on both ends
`relates_to` SHALL be stored as a single row normalized to `source_id < target_id` and displayed on both ends in `task show`. `blocks`, `duplicates`, and `parent_of` SHALL be directional and stored as given.

#### Scenario: Reverse argument order
- **WHEN** `corvee task link 5 3 --relation relates_to` runs after `corvee task link 3 5 --relation relates_to`
- **THEN** one `task_links` row exists with `source_id` 3 and `target_id` 5

### Requirement: Links can be removed
`corvee task unlink <source-id> <target-id> --relation <r>` SHALL remove that link, so a mistyped `parent_of` does not permanently block a parent from reaching `done`.

#### Scenario: Fix a mistyped parent
- **WHEN** `corvee task unlink TASK-1 TASK-2 --relation parent_of` runs
- **THEN** `TASK-1` no longer lists `TASK-2` as a subtask
