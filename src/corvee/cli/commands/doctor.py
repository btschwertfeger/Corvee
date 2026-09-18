#
# Copyright (C) 2026 Benjamin Thomas Schwertfeger
# SPDX-License-Identifier: Apache-2.0
# https://github.com/btschwertfeger
#

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from corvee.cli.context import corvee_context
from corvee.config import global_db_path, project_exists
from corvee.constants import DEFAULT_STALE_DURATION, Scope
from corvee.db.connection import open_connection
from corvee.db.schema import CURRENT_SCHEMA_VERSION
from corvee.db.stats import integrity_findings, project_stats
from corvee.timeutil import parse_duration, timestamp

EPILOG = """\
\b
Examples:
Check the project's overall health at a glance:
  corvee doctor
Get the same report as machine-readable output:
  corvee doctor --json
Flag claims idle for over an hour as stale:
  corvee doctor --stale 1h --json
"""


def _stats_lines(stats: dict[str, Any], *, prefix: str = "") -> list[str]:
    return [
        f"{prefix}tasks.total: {stats['tasks']['total']}",
        *(
            f"{prefix}tasks.by_state.{state}: {count}"
            for state, count in stats["tasks"]["by_state"].items()
        ),
        f"{prefix}tasks.claimed: {stats['tasks']['claimed']}",
        f"{prefix}tasks.stale: {stats['tasks']['stale']}",
        f"{prefix}facts.total: {stats['facts']['total']}",
        *(
            f"{prefix}facts.by_status.{status}: {count}"
            for status, count in stats["facts"]["by_status"].items()
        ),
        f"{prefix}labels: {stats['labels']}",
    ]


def _findings_lines(findings: list[dict[str, Any]], *, prefix: str = "") -> list[str]:
    if not findings:
        return [f"{prefix}findings: none"]
    lines = [f"{prefix}findings:"]
    for finding in findings:
        if finding["kind"] == "cycle":
            lines.append(f"  {finding['relation']} cycle: {' -> '.join(finding['task_ids'])}")
        else:
            lines.append(
                f"  dangling foreign key: {finding['table']}.rowid={finding['rowid']}"
                f" -> {finding['references']}"
            )
    return lines


def _render_text(payload: dict[str, Any]) -> str:
    lines = [f"schema_version: {payload['schema_version']}"]

    local_payload = payload["local"]
    if local_payload is None:
        lines.append("local: not initialized in this directory (no .corvee/config.toml found)")
    else:
        lines.append(f"local.db_path: {local_payload['db_path']}")
        lines.extend(_stats_lines(local_payload, prefix="local."))
        lines.extend(_findings_lines(local_payload["findings"], prefix="local."))

    global_payload = payload["global"]
    if global_payload is None:
        lines.append("global: not created yet (no --global task or fact filed)")
    else:
        lines.append(f"global.db_path: {global_payload['db_path']}")
        lines.extend(_stats_lines(global_payload, prefix="global."))
        lines.extend(_findings_lines(global_payload["findings"], prefix="global."))
    return "\n".join(lines)


def _db_stats(path: Path, *, stale_before: str, scope: Scope) -> dict[str, Any]:
    conn = open_connection(path)
    try:
        conn.execute("BEGIN")
        stats = project_stats(conn, stale_before=stale_before)
        findings = integrity_findings(conn, scope=scope, stale_before=stale_before)
        conn.execute("COMMIT")
    finally:
        conn.close()
    return {"db_path": str(path), **stats, "findings": findings}


def _local_stats(*, stale_before: str) -> dict[str, Any] | None:
    """The local project's own stats, or None if no project resolves from cwd.

    Checking existence rather than always resolving is what lets `doctor`
    run from any directory (§3.3, mirroring the global side below) instead
    of hard-failing outside a project.
    """
    if not project_exists():
        return None
    with corvee_context(write=False) as ctx:
        return _db_stats(ctx.db_path, stale_before=stale_before, scope="local")


def _global_stats(*, stale_before: str) -> dict[str, Any] | None:
    """The global database's own stats, or None if it does not exist yet.

    Checking existence rather than always opening it is what keeps `doctor`
    read-only for a project that has never used `--global`: nothing about
    running this command creates the file.
    """
    path = global_db_path()
    if not path.is_file():
        return None
    return _db_stats(path, stale_before=stale_before, scope="global")


@click.command(epilog=EPILOG)
@click.option("--stale", "-i", "stale_duration", default=DEFAULT_STALE_DURATION, show_default=True)
@click.option("--json", "-j", "as_json", is_flag=True)
def doctor(stale_duration: str, as_json: bool) -> None:
    """Project health: task/fact counts, staleness, and schema version."""
    cutoff = datetime.now(UTC) - parse_duration(stale_duration)
    stale_before = timestamp(cutoff)
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "local": _local_stats(stale_before=stale_before),
        "global": _global_stats(stale_before=stale_before),
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(_render_text(payload))
