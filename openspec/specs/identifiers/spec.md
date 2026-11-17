# identifiers Specification

## Purpose

Defines how tasks and facts are referenced externally, the grammar every id must satisfy, and the guards that keep the task and fact id spaces from being confused.

## Requirements

### Requirement: Task and fact id forms
Tasks SHALL be referenced as `TASK-<n>` and facts as `FACT-<n>`, where `<n>` is the raw integer primary key. Commands SHALL accept either the prefixed form or the bare integer and normalize internally. Anywhere ids are sorted, the sort SHALL be on the integer, never the string. An id SHALL be unique within one database, not globally.

#### Scenario: Bare integer accepted
- **WHEN** `corvee task show 14` runs
- **THEN** it shows the same task as `corvee task show TASK-14`

#### Scenario: Numeric sort
- **WHEN** tasks 9 and 10 are listed by id
- **THEN** `TASK-9` sorts before `TASK-10`

### Requirement: Id grammar
`<n>` SHALL be one or more ASCII digits with a value no greater than 2**63-1, the largest value SQLite stores in an INTEGER column. A digit outside ASCII (Arabic-Indic, superscript) or a number past that bound SHALL be a usage error (exit 2). The same grammar SHALL apply to `FACT-<n>` and to both `-GLOBAL-` forms.

#### Scenario: Out-of-range id
- **WHEN** `corvee task show 9223372036854775808` runs
- **THEN** the exit code is 2

#### Scenario: Non-ASCII digit
- **WHEN** `corvee task show TASK-١٤` runs
- **THEN** the exit code is 2

### Requirement: Global ids
A task in the global database SHALL be referenced as `TASK-GLOBAL-<n>` and a fact as `FACT-GLOBAL-<n>`, each its own id space distinct from every project's local ids. A bare integer SHALL always resolve as local, so reaching a global row requires the full `-GLOBAL-` form.

#### Scenario: Bare integer stays local
- **WHEN** both `TASK-5` and `TASK-GLOBAL-5` exist and `corvee task show 5` runs
- **THEN** the local `TASK-5` is shown

### Requirement: JSON ids use the prefixed form
The `id` key in every JSON task or fact object SHALL be the `TASK-<n>`, `TASK-GLOBAL-<n>`, `FACT-<n>`, or `FACT-GLOBAL-<n>` string, which is the same form every command accepts as input.

#### Scenario: Round trip
- **WHEN** `corvee task add ... -o json` returns `"id": "TASK-14"`
- **THEN** passing `TASK-14` to the next command needs no reformatting

### Requirement: Task and fact namespaces are guarded
A `fact` command given a `TASK-<n>` or `TASK-GLOBAL-<n>` value SHALL reject it with a usage error (exit 2) pointing at `corvee task show`. A `task` command given a `FACT-<n>` or `FACT-GLOBAL-<n>` value SHALL reject it the same way, pointing at `corvee fact show`.

Both parsers otherwise accept a bare integer, so without this guard the two id spaces would be silently ambiguous.

#### Scenario: Task id to a fact command
- **WHEN** `corvee fact show TASK-3` runs
- **THEN** the exit code is 2 and the message points at `corvee task show`

#### Scenario: Fact id to a task command
- **WHEN** `corvee task show FACT-7` runs
- **THEN** the exit code is 2 and the message points at `corvee fact show`
