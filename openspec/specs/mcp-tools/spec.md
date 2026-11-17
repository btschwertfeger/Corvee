# mcp-tools Specification

## Purpose

Defines the MCP tool surface. MCP access control works at tool-name granularity, so every tool is a fixed, individually named verb with its own closed set of named parameters. A host's permission system can then reason about one call at a time.

## Requirements

### Requirement: Fixed tool inventory
The server SHALL expose exactly these 27 tools: `task_show`, `fact_show`, `brief`, `task_claim`, `task_unclaim`, `task_comment`, `task_start`, `task_done`, `task_cancel`, `task_review`, `task_reopen`, `task_block`, `task_add`, `task_search`, `fact_search`, `fact_add`, `fact_verify`, `task_update`, `task_label`, `task_unlabel`, `task_link`, `task_unlink`, `task_assign`, `task_unassign`, `fact_revise`, `fact_retract`, and `fact_unverify`.

#### Scenario: Tool count
- **WHEN** a client lists the server's tools
- **THEN** it receives these 27 names and no others

### Requirement: No generic or destructive tools
The surface SHALL NOT include `purge`, `delete`, `import`, or `export`, and SHALL NOT include any tool taking a field name and value as arguments. `purge` and `delete` are irreversible and `import` and `export` act on a whole database, a different trust question from correcting one task or fact.

#### Scenario: Purge absent
- **WHEN** a client lists tools
- **THEN** no name contains `purge`, `delete`, `import`, or `export`

### Requirement: Parameters are described and closed-choice ones carry enums
Every parameter on every tool SHALL carry a JSON schema `description`. Every closed-choice argument (`scope`, `task_type`, `priority`, `state`, `relation`) SHALL also carry an `enum`. The `enum` SHALL be advisory, so a bad value still reaches the handler and returns the usage-error shape instead of a protocol-level validation error.

#### Scenario: Bad enum value
- **WHEN** `task_add` is called with `priority` `urgent`
- **THEN** the result is the usage-error shape with exit code 2

### Requirement: Refs follow CLI forms and scope rules
Every ref-taking tool SHALL accept the `TASK-<n>`, `TASK-GLOBAL-<n>`, `FACT-<n>`, and `FACT-GLOBAL-<n>` forms and resolve scope as the CLI does. The project root SHALL fix which local database is in play without removing the global one.

#### Scenario: Global ref
- **WHEN** `task_show` is called with `TASK-GLOBAL-2`
- **THEN** it reads the global database

### Requirement: Writers accept `session_id`, readers do not
The 22 tools that write an event SHALL accept an optional `session_id`. `brief`, `fact_search`, `task_search`, `task_show`, and `fact_show` write nothing and SHALL NOT accept it.

#### Scenario: Read tool with session id
- **WHEN** `task_show` is called with `session_id`
- **THEN** the result is an `unknown_argument` error

### Requirement: `task_show` and `fact_show` read one record
`task_show` SHALL take one task ref and an optional `since` duration such as `"7d"`, and SHALL return the full event timeline with no default size cap. An invalid duration SHALL be a usage error (exit 2, `invalid_duration`). `fact_show` SHALL take one fact ref and return claim, status, proof, and the revision timeline. Neither SHALL perform the CLI's cross-scope `referenced` resolution.

Without them a subagent handed "work on TASK-14" can read it only if `brief` happens to list it.

#### Scenario: Trim by duration
- **WHEN** `task_show` is called with `since` `"1h"`
- **THEN** only events from the last hour are returned

### Requirement: `brief` takes only a scope
`brief` SHALL accept an optional `scope` and nothing else, and SHALL behave as `corvee brief` (see `session-brief`), including its cap of 5 `ready` rows.

#### Scenario: No arguments
- **WHEN** `brief` is called with no arguments
- **THEN** it returns the `mine`, `ready`, `stale`, and `labels` sections

### Requirement: Search tools default to 20 results after merging
`task_search` and `fact_search` SHALL take a `scope` (default `all`) and a `limit` (default 20, validated `>= 1`), applied to the merged and sorted result and never per database, so a row that belongs in the merged top 20 is never dropped. The default cap keeps a broad query from dumping an unbounded list into the caller's context.

#### Scenario: Merged limit
- **WHEN** both databases hold matches and `fact_search` runs with `limit` 1
- **THEN** the single returned fact is the top row of the merged order

### Requirement: Search tool options
`task_search` SHALL accept `include_all` and `include_comments`. `fact_search` SHALL accept `include_retracted`, `include_proof`, and `verified_by`. Neither SHALL offer `--after` paging or field projection.

#### Scenario: Retracted facts
- **WHEN** `fact_search` is called with `include_retracted` true
- **THEN** retracted facts matching the text are included

### Requirement: Claim tools carry `force` explicitly
`task_claim` SHALL take one ref and an optional `force`, and `task_unclaim` SHALL take one ref and an optional `force`. `task_comment` SHALL take one ref and text and SHALL NOT be claim-gated.

#### Scenario: Steal a stale claim
- **WHEN** `task_claim` is called with `force` true on a task held by another actor
- **THEN** the claim moves to the caller

### Requirement: Single-transition tools have no `force`
`task_start`, `task_done`, `task_cancel`, `task_review`, `task_reopen`, and `task_block` SHALL each perform one guarded transition and SHALL NOT expose `force`. A caller needing to take over a claim SHALL call `task_claim` with `force` first, as a separately visible step.

A hidden `force` inside a tool named like a harmless state move would let a caller steal a claim through a name that suggests nothing of the kind.

#### Scenario: Foreign claim
- **WHEN** `task_start` targets a task claimed by another actor
- **THEN** the result is a claim-conflict error and the hint names `task_claim(force=true)`

### Requirement: Terminal and review tools keep the transition table
`task_done` and `task_cancel` SHALL transition to `done` and `cancelled`. `task_review` SHALL transition to `review` and keep the task's existing claim. `task_reopen` SHALL transition to `open`, and from `review` SHALL fail with `invalid_transition`, since `open` is not directly reachable there.

#### Scenario: Reopen from review
- **WHEN** `task_reopen` is called on a `review` task
- **THEN** the result is an error with code `invalid_transition` and exit code 5

### Requirement: `task_block` requires a comment
`task_block` SHALL require a `comment` that is non-empty after stripping whitespace, and an empty one SHALL be a usage error (exit 2, `comment_required`). The comment SHALL be written first and the transition attempted second, in one transaction, so a rejected transition rolls the comment back. On an already-`blocked` task it SHALL still write the comment. The rule applies only to this tool, leaving `task update --state blocked` unchanged.

#### Scenario: Rejected transition leaves no comment
- **WHEN** `task_block` is called on a `done` task with a comment
- **THEN** the result is a guard error (exit 5) and no comment was written

#### Scenario: Already blocked
- **WHEN** `task_block` is called with a comment on a task that is already `blocked`
- **THEN** the call succeeds, the comment is written, and no second state event exists

#### Scenario: Missing comment
- **WHEN** `task_block` is called with `comment` `"  "`
- **THEN** the result is an error with code `comment_required` and exit code 2

### Requirement: `task_add` files a task
`task_add` SHALL take `title` and `description` (both required, non-empty, validated as the CLI does), optional `task_type` and `priority`, and `is_global` (default `false`). It SHALL NOT offer `label`, `parent`, or batch input, and SHALL NOT claim the task it creates.

Without it an MCP-only caller can work a task but never file one before starting.

#### Scenario: Blank description
- **WHEN** `task_add` is called with an empty `description`
- **THEN** the result is an error with code `invalid_description` and exit code 2

### Requirement: `fact_add` and fact tools
`fact_add` SHALL take a claim, an optional `proof` that verifies immediately, and `is_global` (default `false`, never inferred from the server mode). `fact_verify` SHALL take a ref and a non-empty `proof`. `fact_revise` SHALL take a ref and a non-empty `new_claim`. `fact_retract` SHALL take a ref and an optional `reason`. `fact_unverify` SHALL take a ref and an optional `note`. Each SHALL behave as the matching CLI command (see `facts`).

#### Scenario: Global-only mode default
- **WHEN** the server has no project and `fact_add` is called without `is_global`
- **THEN** the result is an error with code `no_project`

### Requirement: `task_update` has full CLI parity
`task_update` SHALL take `refs` (one or more ids in one transaction), `title`, `description`, `task_type`, `priority`, `state`, `force`, and `cascade`, and SHALL pass them through the same guarded update the CLI uses. A caller wanting only a plain state change SHOULD use the narrower state tools.

An approved caller can set exactly the fields the schema declares, never an arbitrary one chosen at call time.

#### Scenario: Cascade cancel
- **WHEN** `task_update` is called with `state` `cancelled` and `cascade` true on a parent with open children
- **THEN** the parent and its non-done descendants are cancelled and all are in `result`

### Requirement: Label, link, and assignment tools are paired verbs
`task_label` SHALL attach one `label` to `refs` and `task_unlabel` SHALL remove one, each a no-op success when nothing changes. `task_link` SHALL take `source_ref`, `target_ref`, and `relation`, with `source_ref` the parent for `parent_of`, and `task_unlink` SHALL remove it. `task_assign` SHALL take `refs` and a non-empty `target` actor, and `task_unassign` SHALL take `refs`. Self-links and cross-scope links SHALL be rejected as on the CLI.

#### Scenario: Relink order
- **WHEN** `task_link` is called with `source_ref` `TASK-1`, `target_ref` `TASK-2`, and `relation` `parent_of`
- **THEN** `TASK-1` is the parent of `TASK-2`
