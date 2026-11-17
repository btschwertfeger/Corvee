# record-references Specification

## Purpose

`task show` and `fact show` surface mentions of other tasks and facts found in a record's own text. This connects tasks and facts by convention without any schema link, because the lookup is computed when the record is shown.

## Requirements

### Requirement: `show` lists mentions as `referenced`
`task show` and `fact show` SHALL add a `referenced` key, printed as a `referenced:` line in plain text. It SHALL list every `TASK-<n>`, `TASK-GLOBAL-<n>`, `FACT-<n>`, and `FACT-GLOBAL-<n>` mention in the record's own free text that resolves to a real row. That text SHALL include `description`, `claim`, `proof`, and every event's `body`, `old_value`, `new_value`, `proof`, and `note`. The list SHALL hold distinct ids in order of first appearance and SHALL exclude the record's own id.

#### Scenario: Fact mentioned in a comment
- **WHEN** a comment on `TASK-1` mentions `FACT-7` and `FACT-7` exists, then `corvee task show TASK-1 -o json` runs
- **THEN** `referenced` contains `FACT-7`

#### Scenario: Unresolved mention
- **WHEN** a comment mentions `TASK-9999`, which does not exist
- **THEN** `referenced` does not contain it

### Requirement: References are computed, never stored
The `referenced` key SHALL be computed on every `show` over strings already stored. It SHALL NOT add a column or schema change.

#### Scenario: Mention removed by revision
- **WHEN** a fact's claim is revised so it no longer mentions `FACT-2`
- **THEN** the next `fact show` no longer lists `FACT-2` in `referenced`

### Requirement: Mentions resolve against the database their prefix names
A mention SHALL be checked against the database its own prefix names. The connection already open SHALL serve a matching scope, and the other scope's database SHALL be opened once and lazily, only if a mention actually names it. That open SHALL NOT create a global database that does not exist, and such a mention SHALL be dropped silently.

#### Scenario: Global mention from a local task
- **WHEN** a local task's comment mentions `TASK-GLOBAL-2` and that task exists
- **THEN** `referenced` contains `TASK-GLOBAL-2`

#### Scenario: Global database absent
- **WHEN** a comment mentions `TASK-GLOBAL-2` and `~/.corvee/corvee.db` does not exist
- **THEN** the mention is omitted and the file is still not created

### Requirement: Bare mentions in global records are dropped
A bare `TASK-<n>` or `FACT-<n>` mention in a global record's text SHALL be dropped unconditionally, never checked against the reader's local project. The global database belongs to no one project, so a bare mention has no fixed target. A `TASK-GLOBAL-<n>` or `FACT-GLOBAL-<n>` mention names the global database unambiguously and SHALL keep resolving from either scope's records.

#### Scenario: Bare mention in a global record
- **WHEN** a global fact's claim mentions `TASK-5` and a local `TASK-5` exists in the current project
- **THEN** the global fact's `referenced` does not contain `TASK-5`
