# Spec Delta

## MODIFIED Requirements

### Requirement: `doctor` reports one document
`corvee doctor [--stale <duration>] [-o table|json]` SHALL emit one JSON object with a top-level `schema_version` and a `local` and a `global` key. Each of those SHALL hold `db_path`, `tasks` (`total`, `by_state`, `claimed`, `stale`), `facts` (`total`, `by_status`, `stale`), `labels` (a count), and `findings`.

#### Scenario: Shape
- **WHEN** `corvee doctor -o json` runs in a project
- **THEN** stdout is an object whose `local` entry has `db_path`, `tasks`, `facts`, `labels`, and `findings`, and whose `facts` has `total`, `by_status`, and `stale`

### Requirement: `doctor --stale` sets the stale window
`--stale` SHALL set the duration behind both `stale` counts, defaulting to `4h` with the same format as `task list --stale`. `tasks.stale` counts claims older than the window. `facts.stale` counts the facts `fact list --stale` returns for that window, which are `verified` facts whose `verified_at` is older than it and never `unverified` or `retracted` ones.

#### Scenario: Custom window
- **WHEN** a claim is 2 hours old and `corvee doctor --stale 1h -o json` runs
- **THEN** `local.tasks.stale` is 1

#### Scenario: Stale fact
- **WHEN** a fact was verified 2 hours ago and `corvee doctor --stale 1h -o json` runs
- **THEN** `local.facts.stale` is 1

#### Scenario: Unverified fact never stale
- **WHEN** an `unverified` fact exists and `corvee doctor --stale 1h -o json` runs
- **THEN** `local.facts.stale` is 0

### Requirement: Table output uses prefixed lines
Table output SHALL print the same fields as plain `local.` and `global.` prefixed `key: value` lines, since there is one row per database and not many.

#### Scenario: Prefixes
- **WHEN** `corvee doctor` runs in a project
- **THEN** lines such as `local.tasks.total: 3` appear

#### Scenario: Stale facts line
- **WHEN** `corvee doctor` runs in a project
- **THEN** a `local.facts.stale:` line appears
