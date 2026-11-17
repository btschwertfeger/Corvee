# project-health Specification

## Purpose

`corvee doctor` answers "how big is this backlog, how much of it is stuck, and is the database sound" in one call. It reports counts and integrity findings that no count could reveal, so a broken database cannot report as healthy.

## Requirements

### Requirement: `doctor` reports one document
`corvee doctor [--stale <duration>] [-o table|json]` SHALL emit one JSON object with a top-level `schema_version` and a `local` and a `global` key. Each of those SHALL hold `db_path`, `tasks` (`total`, `by_state`, `claimed`, `stale`), `facts` (`total`, `by_status`), `labels` (a count), and `findings`.

#### Scenario: Shape
- **WHEN** `corvee doctor -o json` runs in a project
- **THEN** stdout is an object whose `local` entry has `db_path`, `tasks`, `facts`, `labels`, and `findings`

### Requirement: `doctor --stale` sets the stale window
`--stale` SHALL set the duration behind the `stale` count, defaulting to `4h` with the same format as `task list --stale`.

#### Scenario: Custom window
- **WHEN** a claim is 2 hours old and `corvee doctor --stale 1h -o json` runs
- **THEN** `local.tasks.stale` is 1

### Requirement: Table output uses prefixed lines
Table output SHALL print the same fields as plain `local.` and `global.` prefixed `key: value` lines, since there is one row per database and not many.

#### Scenario: Prefixes
- **WHEN** `corvee doctor` runs in a project
- **THEN** lines such as `local.tasks.total: 3` appear

### Requirement: `doctor` never hard-fails outside a project
`local` SHALL be `null` when no project resolves from the current directory, and `global` SHALL be `null` when `~/.corvee/corvee.db` does not exist. `doctor` SHALL be read-only, using a plain `BEGIN`, and SHALL NOT create the global database.

#### Scenario: No project, no global database
- **WHEN** `corvee doctor -o json` runs in an uninitialized directory on a machine without a global database
- **THEN** the exit code is 0, `local` and `global` are null, and no file is created

### Requirement: Findings are a list of integrity problems
`findings` SHALL be a list of objects, empty on a healthy project. Three kinds exist, `cycle`, `dangling_foreign_key`, and `shared_actor_sessions`, because no count can reveal them.

#### Scenario: Healthy project
- **WHEN** `corvee doctor -o json` runs against a sound database
- **THEN** `local.findings` is `[]`

### Requirement: Cycle findings
A `blocks` or `parent_of` cycle SHALL be reported as `{"kind": "cycle", "relation": "blocks"|"parent_of", "task_ids": [...]}`, giving the cycle in edge order as a closed loop that repeats the first id last. `link` is cycle-checked on insert, so only a hand-edited database can hold one.

#### Scenario: Hand-edited cycle
- **WHEN** a database holds `A blocks B` and `B blocks A` and `corvee doctor -o json` runs
- **THEN** `findings` has a `cycle` entry with relation `blocks` and task ids `[A, B, A]`

### Requirement: Dangling foreign key findings
Each `PRAGMA foreign_key_check` hit SHALL be reported as `{"kind": "dangling_foreign_key", "table": <name>, "rowid": <n>, "references": <parent table>}`, since `PRAGMA foreign_keys` is only set on connections corvee itself opens.

#### Scenario: Orphan row
- **WHEN** a `task_events` row references a task deleted outside corvee
- **THEN** `findings` has a `dangling_foreign_key` entry for `task_events` referencing `tasks`

### Requirement: Shared-actor collisions are detected
A currently-claimed task whose claimant's own events within the `--stale` window (default `4h`) carry more than one distinct session id SHALL be reported as `{"kind": "shared_actor_sessions", "task_id": <id>, "actor": <actor>, "session_ids": [...]}`. This is the detectable signature of two live sessions sharing one unconfigured actor string.

#### Scenario: Two sessions, one actor
- **WHEN** `human:ada` holds `TASK-1` and has written events under sessions `s1` and `s2` within the window
- **THEN** a `shared_actor_sessions` finding names `TASK-1`, `human:ada`, and both sessions

### Requirement: Cycle detection is per relation and read-only
Cycles SHALL be detected with a white, gray, black depth-first search over `task_links`, one relation at a time, so a `blocks` cycle and a `parent_of` cycle are reported separately. Every integrity check SHALL be read-only and run inside `doctor`'s plain `BEGIN`.

#### Scenario: Separate reports
- **WHEN** a database holds one `blocks` cycle and one `parent_of` cycle
- **THEN** `findings` holds two `cycle` entries, one per relation
