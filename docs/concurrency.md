# Concurrency model

corvee runs no daemon. Each invocation opens the SQLite database named by
`.corvee/config.toml`, does its work, and closes it. This is enough at the
stated scope: one machine, a handful of agents and/or humans, not a swarm.

## What makes it safe

- **WAL mode.** Readers never block writers or each other.
- **`PRAGMA busy_timeout = 5000`** on every connection, so a writer waits
  briefly for another writer to finish instead of failing immediately.
- **Mutating commands open with `BEGIN IMMEDIATE`**, taking the write lock
  up front, for the whole command's transaction. A plain `BEGIN` would let
  the command's first read pin a WAL snapshot before its later write
  requests the lock. A concurrent writer committing in between then makes
  that write fail with `SQLITE_BUSY_SNAPSHOT`, a variant that `busy_timeout`
  does not retry, unlike ordinary lock contention. Taking the lock
  immediately serializes concurrent writers on that transaction instead.
  Read-only commands (`task list`, `task show`, `task ready`, `task
  search`, `task mine`, `task labels`, `fact list`, `fact search`, `fact
  show`, `export`, `doctor`) use a plain `BEGIN`, so they never block a writer.
- **Claims are a single conditional `UPDATE`** (`claimed_by = ? WHERE
  claimed_by IS NULL`), checked by rows-affected. SQLite executes this
  atomically. That conditional update is the entire concurrency-safety
  mechanism for claiming, no extra locking needed on top of it. Facts have
  no claim mechanism at all: two actors revising the same fact both
  succeed, and the second write simply wins, with `fact_events` recording
  both attempts.
- **Schema migrations** are applied under their own `BEGIN IMMEDIATE`,
  after a version check that itself takes no lock, so two processes racing
  to migrate a fresh database serialize on that transaction instead of
  double-applying one.

## Local and global are two independent databases

A task or fact filed with `--global` lives in a second SQLite database,
`~/.corvee/corvee.db`, shared across every project on the machine, next to
the local project database `.corvee/config.toml` points at. Each is its
own connection, transaction, and migration lifecycle. Everything above
applies per database, never across both at once. A command that merges
scopes (`task list --scope all`, the default) opens and closes one
ordinary read-only connection per database in turn. A command that
mutates always touches exactly one database, since a row's scope is fixed
at creation. See [Specification §3.3](spec.md#33-local-and-global-scope).

## What a claim means

A claim means "an actor is working on this right now," not an assignment
and not a reservation. `corvee task add` never claims the task it creates. An
actor that stops work without finishing calls `corvee task unclaim`. Claims
never expire on their own (no TTL, no heartbeat, since a
connect-do-work-close CLI has no notion of liveness), but staleness is
surfaced: `corvee task
list --stale [<duration>]` (default `4h`) lists tasks whose claim has gone
quiet, which is the input to a deliberate `corvee task claim --force`.

See the [Specification](spec.md) for the full, exact rules.
