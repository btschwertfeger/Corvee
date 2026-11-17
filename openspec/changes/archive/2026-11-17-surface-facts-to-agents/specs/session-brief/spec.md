# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: `brief` composes four sections`
- TO: `### Requirement: `brief` composes five sections`

## MODIFIED Requirements

### Requirement: `brief` composes five sections
`corvee brief [--scope local|global|all] [-o table|wide|json]` SHALL combine `task mine`, `task ready`, `task list --stale`, `fact list`, and `task labels` in one read-only call, with no query logic of its own. With `-o json` it SHALL return one object with the keys `mine`, `ready`, `stale`, `facts`, and `labels`, each holding the same row shape as its source command.

#### Scenario: JSON keys
- **WHEN** `corvee brief -o json` runs
- **THEN** stdout is an object with `mine`, `ready`, `stale`, `facts`, and `labels` arrays

### Requirement: `brief --scope` follows `task list`
`--scope` SHALL default to `all` and behave exactly as on `task list`, applied identically to `mine`, `ready`, `stale`, and `facts`, including dropping a missing local project so that a purely global `brief` runs from any directory.

#### Scenario: Global brief from anywhere
- **WHEN** `corvee brief --scope global` runs in an uninitialized directory
- **THEN** the exit code is 0

### Requirement: Plain-text output omits empty sections
Plain-text output SHALL render labeled `mine:`, `ready:`, `stale:`, `facts:`, and `labels:` sections, each as the same fixed-width table its source command uses. A section with zero rows SHALL be omitted entirely instead of printing a header over an empty table.

#### Scenario: Clean backlog
- **WHEN** nothing is claimed, ready, or stale and no facts or labels exist
- **THEN** `corvee brief` prints no section headers

#### Scenario: Fact columns
- **WHEN** a fact exists and `corvee brief` runs
- **THEN** the `facts:` table has the columns `ID`, `CLAIM`, and `STATUS`

#### Scenario: Long claim cut
- **WHEN** a fact with a 100-character claim exists and `corvee brief` runs
- **THEN** the claim cell in the `facts:` table is 60 cells wide and ends in `...`

#### Scenario: Wide fact columns
- **WHEN** a fact exists and `corvee brief -o wide` runs
- **THEN** the `facts:` table has the columns `fact list -o wide` shows and carries the full claim

## ADDED Requirements

### Requirement: `facts` is the newest five
The `facts` section SHALL hold at most 5 rows, the first five of `fact list` (retracted facts excluded, newest `created_at` first, ties broken on `id` descending), and SHALL NOT be configurable through a flag. A caller wanting more uses `fact list --limit`.

The section keeps unverified facts so an agent sees what is still unchecked. The `status` column tells them apart from verified ones.

#### Scenario: Cap
- **WHEN** ten facts exist and `corvee brief -o json` runs
- **THEN** `facts` holds the five newest

#### Scenario: Retracted fact excluded
- **WHEN** the newest fact is retracted and `corvee brief -o json` runs
- **THEN** `facts` does not contain it

#### Scenario: Merged across scope
- **WHEN** one local and one global fact exist and `corvee brief -o json` runs
- **THEN** `facts` holds both, ordered by `created_at` descending
