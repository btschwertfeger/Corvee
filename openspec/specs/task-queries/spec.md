# task-queries Specification

## Purpose

Defines how tasks are listed, filtered, ordered, paged, searched, and shown. The fixed ordering makes a repeated query return the same array, which is what makes `--limit` meaningful.

## Requirements

### Requirement: Fixed, total ordering
`task list`, `task ready`, and `task search` SHALL sort by priority descending (`critical`, `high`, `medium`, `low`), then `created_at` descending, then `id` descending. `task show` SHALL return tasks in the order the ids were given. `created_at` rather than `id` SHALL order merged local and global results, since an id is comparable only within one database.

#### Scenario: Priority first
- **WHEN** a `low` task is filed after a `high` task and `corvee task list` runs
- **THEN** the `high` task is listed first

#### Scenario: Newest within a priority
- **WHEN** two `medium` tasks exist
- **THEN** the later-created one is listed first

### Requirement: `task list` options
`corvee task list` (alias `ls`) SHALL accept `--state`, `--type`, `--priority`, `--label`, `--parent`, `--blocks`, `--blocked-by`, `--relates-to`, `--claimed-by`, `--unclaimed`, `--assigned-to`, `--stale [<duration>]`, `--since <duration>`, `--all`, `--scope`, `--after`, `--limit`, and `--fields`. By default it SHALL exclude `done` and `cancelled` tasks, and `--all` SHALL include them.

#### Scenario: Default hides closed tasks
- **WHEN** a `done` task exists and `corvee task list` runs
- **THEN** the `done` task is not listed

### Requirement: Filters combine with AND
Filters SHALL combine with AND, and a repeated filter SHALL also mean AND, so `task list --label api --label urgent` returns tasks carrying both labels.

#### Scenario: Two labels
- **WHEN** one task has `api` only and another has `api` and `urgent`, and `corvee task list --label api --label urgent` runs
- **THEN** only the second task is returned

### Requirement: "Open" excludes done and cancelled
"Open" SHALL mean any state other than `done` and `cancelled`. It SHALL be the default filter for `task list`, `task search`, and `task mine`, and part of the eligibility rule for `task ready`.

#### Scenario: Review is open
- **WHEN** a task is in `review` and `corvee task list` runs
- **THEN** the task is listed

### Requirement: Keyset paging with `--after`
`--after <id>` on `task list`, `ready`, and `search` SHALL drop everything up to and including `<id>`'s position in the fixed order, then apply `--limit` to the rest. `<id>` need not satisfy the call's own filters, and only its priority, `created_at`, and id place it. An `--after` naming a task that does not exist SHALL exit 3 with error code `task_not_found`.

#### Scenario: Walk the backlog
- **WHEN** `corvee task list --limit 50` runs, then again with `--after <last-id-seen>` until a page is shorter than the limit
- **THEN** every task appears exactly once across the pages

#### Scenario: Unknown cursor
- **WHEN** `corvee task list --after TASK-99999` runs
- **THEN** the exit code is 3 with error code `task_not_found`

### Requirement: `task ready` lists startable work
`corvee task ready` SHALL return open tasks that are unclaimed, not in state `blocked`, and have no open `blocks` predecessor. It SHALL NOT have an `--unclaimed` flag, since the behavior is unconditional. It SHALL accept `--label`, `--scope`, `--after`, `--limit`, and `--fields`.

#### Scenario: Claimed task excluded
- **WHEN** an open task is claimed by another actor and `corvee task ready` runs
- **THEN** that task is not returned

#### Scenario: Open blocker excludes
- **WHEN** `A blocks B` with `A` open and `corvee task ready` runs
- **THEN** `B` is not returned and `A` is

### Requirement: `task mine` answers what was I doing
`corvee task mine` SHALL return open tasks claimed by the actor, plus open unclaimed tasks assigned to the actor, each with its `last_comment`. Claimed tasks SHALL sort by `claimed_at` descending then `id`, and assigned-unclaimed tasks SHALL sort after every claimed one. It SHALL accept `--scope`, `--limit`, and `--fields`.

#### Scenario: Assignment appended
- **WHEN** the actor claimed `TASK-1` and has `TASK-2` assigned and unclaimed
- **THEN** `corvee task mine` returns `TASK-1` first and `TASK-2` second

### Requirement: `--parent` matches direct children
`--parent <id>` SHALL match only tasks one `parent_of` edge below `<id>`, not the whole subtree.

#### Scenario: Grandchild excluded
- **WHEN** `TASK-3` is a child of `TASK-2` which is a child of `TASK-1` and `corvee task list --parent TASK-1` runs
- **THEN** only `TASK-2` is returned

### Requirement: Link filters have two directions
`--blocks <id>` SHALL match tasks that `<id>` blocks, where `<id>` is the edge's source. `--blocked-by <id>` SHALL match tasks that block `<id>`, where `<id>` is the target. `--relates-to <id>` SHALL match `<id>`'s `relates_to` links from either side of the normalized row.

#### Scenario: Both directions
- **WHEN** `TASK-1 blocks TASK-2`
- **THEN** `task list --blocks TASK-1` returns `TASK-2` and `task list --blocked-by TASK-2` returns `TASK-1`

### Requirement: Link filters stay in the id's database
`--parent`, `--blocks`, `--blocked-by`, and `--relates-to` SHALL query only the scope `<id>` was parsed from under `--scope all`, contributing nothing from the other database, so a same-numbered row in the other database never matches.

#### Scenario: Same number in the other scope
- **WHEN** a global `TASK-GLOBAL-1` has a child and `corvee task list --parent TASK-1` runs
- **THEN** the global child is not returned

### Requirement: `--since` matches recent updates
`--since <duration>` on `task list` and `fact list` SHALL match `updated_at >= now - <duration>`, using the same duration syntax as `--stale`. On `task list` it SHALL compose with the open-only default, and `--all` SHALL also catch tasks closed in that window.

#### Scenario: Recently closed
- **WHEN** a task was closed an hour ago and `corvee task list --since 7d --all` runs
- **THEN** the task is listed

### Requirement: `task search` is a substring match
`corvee task search <text>` SHALL return tasks whose `title` or `description` contains `<text>`, case-insensitive, with `%` and `_` in the text matching literally. It SHALL use no ranking, returning matches in the standard order, and accept `--all`, `--scope`, `--after`, `--limit`, and `--fields`.

An FTS index would add a second copy of the data that can drift, for latency nobody can perceive at this scale.

#### Scenario: Case-insensitive
- **WHEN** a task is titled `Fix Auth Token` and `corvee task search "auth token"` runs
- **THEN** the task is returned

### Requirement: `--include-comments` extends search
`--include-comments` SHALL also match comment bodies (`task_events` rows of kind `comment`). It SHALL be off by default.

#### Scenario: Match in a comment
- **WHEN** only a comment on `TASK-1` mentions `rate limit` and `corvee task search "rate limit" --include-comments` runs
- **THEN** `TASK-1` is returned, and it is not without the flag

### Requirement: `task show` returns the full timeline by default
`corvee task show <id> [<id> ...]` SHALL return the description, labels, links, subtasks, and the full event timeline. `--since <duration>` SHALL keep only newer events, and `--no-events` SHALL drop the timeline. A trimmed response SHALL report `events_omitted`, so a long history never silently disappears.

#### Scenario: Trimmed timeline
- **WHEN** a task has 150 events and `corvee task show TASK-1 --since 1h -o json` matches 7 of them
- **THEN** `events` has 7 entries and `events_omitted` is 143

### Requirement: Task field projection
`--fields` on task listings SHALL accept only `id`, `title`, `description`, `type`, `priority`, `state`, `claimed_by`, `claimed_at`, `assigned_to`, `created_at`, `updated_at`, `scope`, and `blocked_by`, and reject any other name with the valid list. Labels, links, events, and `last_comment` SHALL NOT be projectable. `blocked_by` SHALL render comma-joined in a table.

#### Scenario: Cheap overview
- **WHEN** `corvee task list --fields id,title,state,blocked_by -o json` runs
- **THEN** each object has exactly those four keys
