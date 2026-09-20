#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from corvee.actor import resolve_actor, resolve_session_id
from corvee.config import global_db_path, resolve_project
from corvee.constants import Scope
from corvee.db.connection import open_connection, unusable_database_error


@dataclass(frozen=True)
class CorveeContext:
    db_path: Path
    scope: Scope
    conn: sqlite3.Connection
    actor: str
    session_id: str | None


@contextmanager
def corvee_context(
    *,
    write: bool = True,
    scope: Scope = "local",
    actor: str | None = None,
    session_id: str | None = None,
    project_db_path: Path | None = None,
) -> Iterator[CorveeContext]:
    """Resolve the database for `scope`, open it (already-migrated), and run the
    command body in one transaction: committed on success, rolled back on any
    exception. This is what gives every mutating command the "batch update
    is one transaction, all or nothing" property for free, not just `update`.

    `scope="local"` (the default) resolves the project database.
    `scope="global"` resolves the one shared global database, creating
    `~/.corvee/` if this is the first command to write to it —
    `open_connection` itself creates and migrates the database *file*, the
    same way it does for a fresh local project, but it cannot create a
    missing parent directory. A read (`write=False`) against a global
    database that does not exist yet never creates one: it opens a
    throwaway in-memory database instead, migrated the same way, so every
    query on it comes back empty exactly as an unpopulated real one would,
    with nothing left behind on disk.

    Mutating commands (the default) open with `BEGIN IMMEDIATE`, taking the
    write lock up front. A plain `BEGIN` would let this transaction's first
    read pin a WAL snapshot before its later write requests the lock, and a
    concurrent writer committing in between then makes that write fail with
    SQLITE_BUSY_SNAPSHOT — a variant `busy_timeout` does not retry, unlike
    ordinary lock contention. Taking the lock immediately serializes
    concurrent writers on this transaction instead, the same principle the
    migration path already relies on. Read-only commands pass `write=False`
    to keep a plain `BEGIN`, so they never block a writer.

    `actor`/`session_id` are explicit overrides, passed straight to
    `resolve_actor`/`resolve_session_id` instead of letting those fall
    back to click's (thread-local) current context. The CLI itself never
    passes them — its global `--actor`/`--session-id` flags already work
    through that fallback path. They exist for a caller running outside a
    click command on its own thread (the MCP server, §10 of the spec),
    where relying on ambient click state would silently resolve to the
    wrong actor.

    `project_db_path`, given, is used verbatim instead of calling
    `resolve_project()` (cwd-based) at all -- spec §10.1 already claims
    the MCP server resolves and caches its project once at startup
    (`ServerConfig.project`, a full `ProjectConfig` including `db_path`);
    without this, every single tool call re-derived it anyway (a fresh
    filesystem walk up to `.corvee/config.toml` plus a TOML re-parse),
    making that cache accidentally-correct-by-re-derivation rather than
    real (TASK-37).
    """
    if scope == "global":
        db_path = global_db_path()
        if write or db_path.is_file():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = open_connection(db_path)
        else:
            conn = open_connection(Path(":memory:"))
    else:
        db_path = project_db_path if project_db_path is not None else resolve_project().db_path
        conn = open_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield CorveeContext(
            db_path=db_path,
            scope=scope,
            conn=conn,
            actor=resolve_actor(actor),
            session_id=resolve_session_id(session_id),
        )
        conn.execute("COMMIT")
    except BaseException as error:
        # `BEGIN ...` above can fail before any transaction exists (lock
        # contention past busy_timeout). Rolling back then would raise
        # "cannot rollback - no transaction is active" and replace the real
        # cause; in_transaction is False in exactly that case.
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        # sqlite reports a database it cannot write to (a read-only file or
        # filesystem, most often) only once a statement actually writes, well
        # past the point `open_connection` can see it, so an unusable file has
        # to be translated here too.
        if isinstance(error, sqlite3.Error):
            config_error = unusable_database_error(error, db_path)
            if config_error is not None:
                raise config_error from error
        raise
    finally:
        conn.close()
