# mcp-results-and-errors Specification

## Purpose

Defines the shape of every MCP tool result and error so a host or subagent parses one vocabulary regardless of which tool it called, and so the same error codes mean the same on the CLI and over MCP.

## Requirements

### Requirement: Stdout carries only protocol frames
No MCP handler SHALL write to stdout, and nothing else in the server process SHALL, since a stray byte corrupts JSON-RPC framing on a stdio transport. Handlers SHALL build results from the row objects' dict form and SHALL NOT call the CLI's output emitters.

#### Scenario: Handler output
- **WHEN** any tool handler runs
- **THEN** it writes nothing to stdout, and every byte the server writes to stdout parses as JSON-RPC framing

### Requirement: Structured output on every tool
Every tool SHALL be registered with structured output enabled. A dict result SHALL appear verbatim as `structuredContent` and also as JSON text in `content`, so a host reading either field gets the same data.

#### Scenario: Both fields
- **WHEN** `task_show` returns
- **THEN** `structuredContent` equals the JSON parsed from `content[0].text`

### Requirement: Single-ref tools return one object
A tool taking a single ref, such as `task_claim`, `task_start`, `task_done`, `task_block`, `fact_revise`, `fact_retract`, and `fact_unverify`, SHALL return that row's dict, including a `warnings` key where one applies. Task results SHALL carry `blocked_by`. The derived `blocked*` marker is plain-text only and SHALL NOT appear.

#### Scenario: Claim result
- **WHEN** `task_claim` succeeds
- **THEN** the result is one task object with `claimed_by` set and `blocked_by` present

### Requirement: Batch tools return a result list
A tool taking `refs` (`task_update`, `task_label`, `task_unlabel`, `task_assign`, `task_unassign`) SHALL accept one or more ids sharing one scope and return `{"result": [<object>, ...]}`, whatever the number of ids. `task_update`'s cascade list SHALL appear in that same list in the order produced. `task_link` and `task_unlink` SHALL return `{"result": [...]}` with the two endpoints.

#### Scenario: One id, still a list
- **WHEN** `task_label` is called with one ref
- **THEN** the result is `{"result": [<one task>]}`

### Requirement: State tools never return a cascade
`task_done` and `task_block` SHALL return a single object and never a cascade array. Neither tool exposes `cascade` and neither targets `cancelled`.

#### Scenario: Done with children
- **WHEN** `task_done` succeeds on a task with `done` children
- **THEN** the result is one task object

### Requirement: Search tools report omissions
`task_search` and `fact_search` SHALL return `{"result": [...], "omitted": <int>}`, where `result` holds the matched rows already limited and `omitted` counts further matches the `limit` cut off, `0` when none were cut. A caller SHALL be able to tell a capped result from "no more matches exist".

#### Scenario: Capped
- **WHEN** 25 facts match and `fact_search` runs with the default limit
- **THEN** `result` has 20 entries and `omitted` is 5

### Requirement: Inputs are validated like the CLI
Tools SHALL validate ids, durations, and enum arguments by the same rules as the CLI, and SHALL check a bounded integer such as `limit` is `>= 1`. A failure SHALL be a usage error (exit 2). No tool SHALL offer a `--fields` projection, since every result is already a small structured object.

#### Scenario: Bad limit
- **WHEN** `fact_search` is called with `limit` 0
- **THEN** the result is an error with exit code 2

### Requirement: Undeclared arguments are usage errors
A call carrying a key the tool's input schema does not declare SHALL return an `isError` result with error code `unknown_argument` and `exit_code` 2, naming every offending key and the tool's valid argument names. The tool SHALL NOT run and nothing SHALL be written. `force` on `task_start`, `task_done`, `task_cancel`, `task_review`, `task_reopen`, and `task_block` is the one exception, accepted and ignored.

#### Scenario: Typo
- **WHEN** `task_claim` is called with `forc=true`
- **THEN** the result is an error with code `unknown_argument` naming `forc`, and no claim is taken

### Requirement: Errors map to `isError` results
Every `CorveeError` raised in a handler SHALL map to an `isError` result carrying the CLI's error JSON plus `exit_code`, giving `{"error": {"code", "message", "exit_code", ...}}`, so a caller tells a claim conflict (4) from a guard violation (5) without matching `code`. Any other exception SHALL be caught at the handler boundary and returned in the internal-error shape with `exit_code` 1, never as a raw traceback.

#### Scenario: Claim conflict
- **WHEN** `task_update` targets a task claimed by another actor
- **THEN** the result is an error with code `claim_conflict` and `exit_code` 4

### Requirement: Claim conflicts carry an MCP-phrased hint
A `claim_conflict` error SHALL carry a `hint` in addition to the unchanged `message`. The default hint SHALL be to call `task_claim(force=true)` on the ref and retry. `task_unclaim` SHALL instead hint `task_unclaim(force=true)`, since stealing a claim there would reassign it instead of releasing it.

#### Scenario: Unclaim hint
- **WHEN** `task_unclaim` hits a claim conflict
- **THEN** `hint` names `task_unclaim(force=true)`
