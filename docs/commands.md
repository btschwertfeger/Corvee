# Commands

Every command below accepts `-o`/`--output table|wide|json` and, with
`json`, prints a JSON array of objects on success, except `explain`,
`completion`, and `mcp serve`, which have no `-o`/`--output` flag, and
`export`, which always writes JSON without needing one. `wide` only
applies to the row-listing commands (`task list`/`ready`/`search`/`mine`,
`fact list`/`search`, `brief`); every other command rejects it. `brief`,
`doctor`, `init`, and `task tree` print one object rather than an array
under `-o json`, since each returns a document rather than query results.
`corvee <command> --help` shows runnable examples for any of them. This
page covers usage and flags only. Standalone, checked-true (or
not-yet-checked, or retracted) facts are not linked to tasks by the schema
(see [Specification](spec.md#46-facts)).

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
| 5 | Guard violation: open children, a `parent_of` or `blocks` cycle, a self-link, a second parent on a task that has one, a rejected state transition, claiming an already-terminal task, `fact delete` on a non-retracted fact, `task purge` on a non-cancelled or still-linked task, linking across the local/global scope split |
| 6 | Project/config problem: no or unreadable `.corvee/config.toml`, a database file that cannot be opened or written, a `.corvee/` or database directory that cannot be created, a schema newer than this binary, or a `corvee import` of a dump whose schema_version doesn't match this binary's |

For the exact JSON shapes, filter semantics, and every edge case, see the
[Specification](spec.md). This page is a summary, not the contract.
