# Commands

Every command below accepts `--json` (except `explain`) and prints a JSON
array of objects on success. `corvee <command> --help` shows runnable
examples for any of them. This page covers usage and flags only. Standalone,
checked-true (or not-yet-checked, or retracted) facts are not linked to
tasks by the schema (see [Specification](spec.md#46-facts)).

::: mkdocs-click
    :module: corvee.cli.main
    :command: cli
    :prog_name: corvee
    :depth: 1

## Reading an id

Tasks are referenced externally as `TASK-<n>` (e.g. `TASK-14`) and facts
as `FACT-<n>` (e.g. `FACT-7`). Commands accept either the prefixed form or a
bare integer and normalize internally. A `task` command given a `FACT-<n>`
value (or a `fact` command given a `TASK-<n>` value) is rejected rather
than silently misread.

A task or fact filed with `--global` gets the `TASK-GLOBAL-<n>` /
`FACT-GLOBAL-<n>` form instead, its own id space in the shared global
database (`~/.corvee/corvee.db`) rather than the local project (see
[Specification §3.3](spec.md#33-local-and-global-scope)). Every command
that takes an id infers local vs. global from the id itself. Only `add`
needs the explicit `--global` flag, since there's no existing id to read
it from.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unexpected/internal error |
| 2 | Usage or validation error |
| 3 | Task or fact not found |
| 4 | Claim conflict: the task is held by another actor |
| 5 | Guard violation: open children, a `parent_of` cycle, a rejected state transition, claiming an already-terminal task, `fact delete` on a non-retracted fact, linking across the local/global scope split |
| 6 | Project/config problem: no `.corvee/config.toml`, or the schema is newer than this binary supports |

For the exact JSON shapes, filter semantics, and every edge case, see the
[Specification](spec.md). This page is a summary, not the contract.
