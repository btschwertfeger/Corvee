# AGENTS.md

Guidance for coding agents working on the corvee codebase itself, not the
pointer block `corvee init` prints for other projects to paste into their
own AGENTS.md.

## Source of truth

- `docs/spec.md` is the technical specification: schema, CLI contract, exit
  codes, concurrency model. Implementation must match it. If the two
  disagree, update `docs/spec.md` rather than letting it drift. Any new
  feature bumps the spec's own version and extends `docs/spec.md` first,
  independent of when it gets implemented. The spec documents intended
  design, not just shipped behavior.
- `pyproject.toml`'s `[tool.hatch.envs.default.scripts]` is the source of
  truth for available dev commands. The list below covers the ones used
  constantly. Run `hatch env show` for the full, current set.

## Stack

Python 3.11+, managed with Hatch (`uv` as the installer underneath). `src`
layout: the package lives at `src/corvee/`, tests at `tests/`. click for the
CLI, stdlib `sqlite3` for storage, no ORM. Every tool (pytest, ty, ruff,
black, coverage) is configured in `pyproject.toml`, not in separate config
files.

```bash
hatch run test                  # pytest, parallel via pytest-xdist
hatch run check                 # every prek hook + test.
                                 # Run this before considering a change done
hatch run lint                  # ruff check, via prek
hatch run format                # black, via prek
hatch run typecheck             # ty, via prek
hatch run +py=3.12 test:test    # run the suite against one Python version
                                 # from the test matrix (3.11-3.14)
```

`lint`/`format`/`typecheck` all delegate to `prek run <hook-id>` rather than
invoking ruff/black/ty directly, so hatch and CI can never drift apart on
what each one actually runs. `hatch run check` (or `prek run --all-files`
directly) is the mandatory quality gate before a change is considered
finished.

## Principles

KISS, YAGNI, DRY. A change should be minimal and focused on what was asked.
Do not use a bug fix or small feature as an excuse for a wider rework, a new
abstraction, or unrelated cleanup. Three similar lines beat a premature
abstraction.

## Architecture

Every CLI invocation flows through the same layers, in this order:

1. **`cli/main.py`**: the click group. `CorveeGroup.main()` is overridden so
   every failure, including click's own usage errors, is caught and
   re-emitted through one path: a `{"error": {...}}` JSON object on stderr
   plus the documented exit code (`errors.py`). This is what makes
   `CliRunner`-based tests exercise the exact same error path a real
   subprocess would.
2. **`cli/commands/{task,fact}/*.py`**: one thin click command per verb. The
   pattern is always: parse id(s) with `models.parse_task_refs`/
   `parse_fact_refs` (which also determines local vs global scope from the
   `TASK-GLOBAL-<n>`/`FACT-GLOBAL-<n>` prefix), open `corvee_context(...)`,
   call exactly one `db/*.py` function to do the actual mutation/query, then
   `output.emit_tasks`/`emit_facts` to print. Command files contain no SQL
   and no business logic themselves.
3. **`cli/context.py`** (`corvee_context`): resolves which SQLite file to
   open (local project via `config.resolve_project()`, or the global
   `~/.corvee/corvee.db` for `scope="global"`), opens it via
   `db/connection.open_connection` (which also bootstraps/migrates the
   schema), and wraps the command body in one transaction: `BEGIN IMMEDIATE`
   for writes, plain `BEGIN` for reads, commit on success, rollback on any
   exception. This is what gives multi-id commands like `task update 4 7 9`
   their all-or-nothing property for free.
4. **`db/*.py`**: raw `sqlite3` against the schema in `db/schema.py` (no
   ORM). Each module owns one area: `tasks.py`, `facts.py`, `labels.py`,
   `links.py`, `events.py`, `export_import.py`, `stats.py`. Mutating
   functions here call into `guards/*.py` before writing (transition table,
   parent/child cycle checks, claim conflicts, label patterns) and write the
   corresponding `task_events`/`fact_events` row in the same call, so the
   audit trail is not a separate step a caller can forget.
5. **`guards/*.py`**: pure validation functions that raise
   `errors.GuardViolationError`/`ClaimConflictError`/etc. Consult
   `constants.py` for the data-driven rules (e.g. `TRANSITIONS`, a
   `dict[State, frozenset[State]]`) rather than branching in code, so policy
   changes are edits to one table.
6. **`output.py`**: JSON array (or single object for `doctor`/`export`) vs.
   fixed-width table rendering, `--fields` projection (`filter_fields`),
   shared by every command group.

Cross-cutting modules: `actor.py` resolves `$CORVEE_ACTOR`/
`$CORVEE_SESSION_ID`. `config.py` walks up from cwd to find
`.corvee/config.toml` (git-style) and resolves `db_path`. `timeutil.py` is
the one place that formats the fixed-width UTC-with-milliseconds timestamps
used everywhere on disk.

**Scope.** Every task/fact lives in exactly one of two independent SQLite
databases: the local project one (`.corvee/corvee.db`, pointed to by
`.corvee/config.toml`) or one global database shared across the machine
(`~/.corvee/corvee.db`, created lazily on first `--global` write). Scope is
fixed at creation and encoded in the id itself (`TASK-14` vs
`TASK-GLOBAL-14`), never passed as a separate flag on mutating commands. A
merged read (`--scope all`, the default for listing) opens and closes one
ordinary connection per database in turn, never a cross-database
transaction.

**Concurrency.** No daemon. Every invocation opens, does its transaction, and
closes. WAL mode + `busy_timeout=5000` handle contention. Claims are a single
conditional `UPDATE` checked by rows-affected. Full reasoning in
`docs/concurrency.md` and spec §3.2/§3.3. Read that before touching
`cli/context.py` or `db/connection.py`.

**Exit codes.** `errors.py` defines one exception subclass per documented
exit code (0 success, 1 internal, 2 usage, 3 not found, 4 claim conflict, 5
guard violation, 6 project/config problem). Raise the matching subclass
rather than a bare exception. `CorveeGroup.main()` is what turns it into the
JSON-on-stderr shape and the process exit code.

## Working here

- TDD: write the failing test before the code that makes it pass.
- No mocking SQLite. Tests run against a real database in `tmp_path`.
- Every CLI command needs a `--help` epilog with at least three runnable
  examples (enforced by a test).
- Full type hints throughout. `ty` has zero tolerance for untyped public
  signatures or unjustified `Any`.
- Never use `typing.cast()`. It tells the type checker to trust an
  annotation and does nothing at runtime, so an assumption that turns out
  wrong propagates a bad value silently instead of failing loudly. Where a
  value's real type is narrower than what the checker can infer on its own
  (a DB column value narrowed to a `Literal`, a `click.Choice(...)`-checked
  option), write a small function that checks the value against its known
  set of valid members and raises if it is not one of them, then returns it
  -- see `constants.py`'s `narrow_*` functions for the pattern, and
  `mcp/dispatch.py::run_tool`'s docstring for the one place a genuine
  external-library expressiveness gap (not a value narrowing) still needs a
  single, well-documented `# ty: ignore[...]` instead.
- Tests are classified by directory, not per-test decorators: `tests/unit`
  (pure functions, no filesystem/db), `tests/acceptance` (through the CLI or
  db layer against a real `tmp_path` SQLite database), `tests/e2e` (a real
  `python -m corvee` subprocess). `conftest.py` applies the
  `unit`/`acceptance`/`e2e` pytest marker automatically from
  `item.path.parts`. Key shared fixtures: `project` (initialized project, cwd
  inside it, `CORVEE_ACTOR` set), `runner` (`CliRunner`), `conn` (direct
  connection to the project db), `add_task`/`add_fact` (create via CLI,
  return the id).
- Never run `corvee ... --global` directly in a shell against this
  machine's real `~/.corvee/corvee.db` while manually poking at --global
  behavior. Set `CORVEE_GLOBAL_DB=/some/scratch/path` first. The pytest
  suite already isolates `$HOME` for you. This is only for ad hoc shell
  commands outside it.
- Tests run on Linux, macOS and Windows, so none may assume POSIX filesystem
  rules. Where a platform genuinely differs, branch on `sys.platform` inside
  one test rather than skipping it, or assert the value against a pure
  function in `tests/unit` instead of through a file whose name the platform
  will not accept.
- Commit one completed corvee task per commit, not a batch of several
  tasks squashed into one. Finish the task (code, tests, docs, `hatch run
  check` green, `corvee task comment`/`update --state done`), then commit
  before starting the next one, so each commit maps onto one reviewable
  unit of work and one task's audit trail.
- When opening a PR, try to set the correct labels from the repo's existing
  label set (`gh label list`), matching what the change actually is (bug,
  enhancement, documentation, dependencies, github_actions, ...).
